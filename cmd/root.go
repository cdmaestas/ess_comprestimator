package cmd

import (
    "os"
    "fmt"
    "math/rand"
    "sync"
    "math"
    "syscall"
    "github.com/spf13/cobra"
    "github.com/minio/minlz"
    wr "github.com/mroth/weightedrand"
    "io/fs"
    "path/filepath"
    "time"
    "runtime"
    "log"
    "errors"
)



// rootCmd represents the base command when called without any subcommands
var rootCmd = &cobra.Command{
    Use:   "ess_comprestimator",
    Short: "Estimates compression ratios for IBM Storage Scale Systems with FCM4 drives",
    Long: `   IBM ESS Comprestimator analyzes files in a directory and estimates
    the compression ratio that would be achieved using FCM4 drives on an ESS system.
    
    It works by sampling files proportionally to their size and compressing the samples
    using a similar compression algorithm to FCMs, providing an accurate estimate of space savings.`,
    // Uncomment the following line if your bare application
    // has an action associated with it:
    Run: func(cmd *cobra.Command, args []string) {
        runComprestimator(cmd)
    },
}

// Execute adds all child commands to the root command and sets flags appropriately.
// This is called by main.main(). It only needs to happen once to the rootCmd.
func Execute() {
    err := rootCmd.Execute()
    if err != nil {
        os.Exit(1)
    }
}

func init() {
    // Here you will define your flags and configuration settings.
    // Cobra supports persistent flags, which, if defined here,
    // will be global for your application.

    // Path
    rootCmd.Flags().StringP("path", "p", "", "Path to run ess_comprestimator on")
    rootCmd.MarkFlagRequired("path")

    rootCmd.Flags().StringP("error-log", "l", "comprestimator_errors.log", "Log file path for errors (files that couldn't be read or compressed)")

    // Sampling flags
    rootCmd.Flags().Int16("sampling-percentage", 10, "What percentage of data should be sampled")
    rootCmd.Flags().Bool("exhaustive-sample", false, "Sample entire directory (slow, but maximal accuracy)")
    rootCmd.MarkFlagsMutuallyExclusive("sampling-percentage", "exhaustive-sample")

    // Performance flags
    rootCmd.Flags().Int("threads", max(1, runtime.GOMAXPROCS(0)), "How many threads to use for processing. Uses # of logical CPUs by default")


    // Exclusion flags
    rootCmd.Flags().StringSlice("exclude", []string{}, "Glob patterns to exclude files/directories (can be specified multiple times)")
    rootCmd.Flags().Bool("exclude-hidden", false, "Exclude hidden files and directories (those starting with '.')")

}

type fileInfo struct {
    path string
    size  int64
    count int64
}

type compressResult struct {
    preCompress int64
    postCompress int64
    samplesProcessed int64
}

const SAMPLE_LEN = 16384
const DEFAULT_SAMPLES_PER_BUFFER = 16384
const DEFAULT_SAMPLE_RATIO = .1
const PROGRESS_UPDATE_INTERVAL = 100_000
const FCM4_MAX_COMPRESSION_RATIO = 4.0


// Given a number of bytes, return a string converting them to a human readable
// format (e.g. 1024124 -> 1.02 MB)
func prettyBytes(sizeInBytes int64) string {
    units := [6]string{"bytes", "KB", "MB", "GB", "TB", "PB"}
    for unit := 1; unit < len(units); unit++ {
        if sizeInBytes < intPow(1024, unit+1) {
            return fmt.Sprintf("%.2f %v", float64(sizeInBytes/intPow(1024, unit)), units[unit])
        }
    }
    return fmt.Sprintf("%.2f %v", float32(sizeInBytes/intPow(1024, len(units))), units[len(units)-1])
}

// Given a root path, recursively walk the path and build a weighted random
// sampler, enabling files to be sampled from a directory with weighted 
// preference based on their size
func buildSampler(root string, errorLogger *log.Logger, excludePatterns []string, excludeHidden bool) (*wr.Chooser, int64, error) {
    var population []wr.Choice
    var totalSize int64

    var filesProcessed int64
    var filesSkipped int64
    
    err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
        if err != nil {
            filesSkipped++
            if errorLogger != nil {
                errorLogger.Printf("Failed to read during scan: %s: %v", path, err)
            }
            return nil
        }

        // Check if hidden file/directory should be excluded
        if excludeHidden && len(d.Name()) > 1 && d.Name()[0] == '.' {
            filesSkipped++
            if errorLogger != nil {
                errorLogger.Printf("Skipping: %s/%s", path, d.Name())
            }
            if d.IsDir() {
                return filepath.SkipDir
            }
            return nil
        }

        // Check if path matches any exclude patterns
        for _, pattern := range excludePatterns {
            matched, err := filepath.Match(pattern, d.Name())
            if err == nil && matched {
                filesSkipped++
                if errorLogger != nil {
                    errorLogger.Printf("Skipping: %s", d.Name())
                }
                if d.IsDir() {
                    return filepath.SkipDir
                }
                return nil
            }
        }

        if d.IsDir() {
            return nil
        }

        info, err := d.Info()
        if err != nil {
            filesSkipped++
            if errorLogger != nil {
                errorLogger.Printf("Failed to get file info: %s: %v", path, err)
            }
            return nil
        }

        size := info.Size()
        totalSize += size
        filesProcessed++
        population = append(population,
            wr.NewChoice(fileInfo{path, size, 1}, uint(info.Size())),
        )

        if filesProcessed % PROGRESS_UPDATE_INTERVAL == 0 {
            fmt.Printf("\r%-80s\rMapping directory | %v found so far (%v files were not read)", "", prettyBytes(totalSize), filesSkipped)
        }
        return nil
    })
    fmt.Printf("\r%-80s\rMapping directory | %v found so far (%v files were not read)", "", prettyBytes(totalSize), filesSkipped)
    
    filesSkippedRatio := float64(filesSkipped) / float64(filesProcessed+filesSkipped)
    if filesSkippedRatio >= 1 {
        fmt.Fprintf(os.Stderr, "\nWarning: %.2f%% of the files in the directory were not read. See error log for details.", filesSkippedRatio*100)
    }
    if err != nil {
        fmt.Fprintf(os.Stderr, "Error walking the path %q: %v\n", root, err)
    }

    chooser, err := wr.NewChooser(population...)
    return chooser, totalSize, err
}

// Given a file_info object, take file_info.read_count random samples from
// the file (of size SAMPLE_LEN) and compress them, returning the pre and post
// compressed sizes
func compressSample(sample fileInfo) (int64, int64, int64, error) {
    file, err := os.Open(sample.path)
    if err != nil {
        return 0, 0, 0, err
    }
    defer file.Close()

    var pre int64
    var post int64
    var successfulSamples int64
    var failedSamples int64
    const maxConsecutiveFailures = 10
    
    for range sample.count {
        var offset int64
        if sample.size - SAMPLE_LEN > 0 {
            offset = rand.Int63n(max(0,sample.size-SAMPLE_LEN))
        } else {
            offset = 0
        }

        // Seek to a random point
        _, err = file.Seek(offset, 0)
        if err != nil {
            continue
        }

        // Read a sample from the random point
        buffer := make([]byte, SAMPLE_LEN)
        n, err := file.Read(buffer)
        if err != nil {
            continue
        }

        // Compress the sample (use only bytes actually read)
        // Suppress stderr at file descriptor level (minlz writes directly to fd 2)
        devNull, _ := os.OpenFile(os.DevNull, os.O_WRONLY, 0)
        oldStderr, _ := syscall.Dup(2)
        syscall.Dup2(int(devNull.Fd()), 2)
        
        compressed, err := minlz.Encode(nil, buffer[:n], minlz.LevelBalanced)
        
        syscall.Dup2(oldStderr, 2)
        syscall.Close(oldStderr)
        devNull.Close()
        
        if err != nil {
            // Skip this sample if compression fails
            failedSamples++
            if failedSamples >= maxConsecutiveFailures {
                break
            }
            continue
        }
        
        pre += int64(n)
        post += int64(len(compressed))
        successfulSamples++
        failedSamples = 0
    }
    
    // Return results if we successfully compressed at least one sample
    if successfulSamples > 0 {
        return pre, post, successfulSamples, nil
    }
    
    return 0, 0, 0, errors.New("no samples could be compressed")
}


// Reimplementation of Math.Pow with int64 base and int power
func intPow(base int64, power int) int64 {
    return int64(math.Pow(float64(base), float64(power)))
}

// Compressor thread entrypoint. Takes a compression job from jobs, compresses
// it, and sends off the results to intermediate_results channel where they can
// be accumulated
func compressorWorker(jobs <-chan fileInfo, intermediateResults chan<- compressResult, errorLogger *log.Logger) {
    for {
        job, more := <-jobs
        if !more {
            return
        }
        pre, post, samplesProcessed, err := compressSample(job)
        if err != nil {
            if errorLogger != nil {
                errorLogger.Printf("Failed to compress: %s: %v", job.path, err)
            }
            continue
        }
        intermediateResults <- compressResult{pre, post, samplesProcessed}
    }
}

// Given intermediate (partial) compression results, accumulate them into a 
// running average compression ratio
func accumulateResults(intermediateResults <-chan compressResult, finalResult chan<- compressResult, sampleCount int64) {
    var totalPre int64
    var totalPost int64
    var totalSamples int64
    startTime := time.Now().UnixMilli()
    for {
        result, more := <-intermediateResults
        if !more {
            finalResult <- compressResult{totalPre, totalPost, totalSamples}
            return
        }

        totalPre += result.preCompress
        totalPost += result.postCompress
        totalSamples += result.samplesProcessed

        nowTime := time.Now().UnixMilli()

        // Calculate compression ratio safely
        var ratio float64
        if totalPost > 0 {
            ratio = float64(totalPre) / float64(totalPost)
        }

        fmt.Printf("\r%-80s\rRatio: %.3fx | Progress %.2f%% (%v/s)",
            "", // Clear the line first
            ratio, // Rolling Compression Ratio
            100*float64(totalSamples)/float64(sampleCount), // Percent Progress
            prettyBytes(int64(float64(totalPre)/(float64(nowTime-startTime)/1000))), // Units /s
        )
    }
}

// Configuration holds the runtime configuration from CLI flags
type config struct {
    path              string
    errorLog          string
    samplingPercentage int16
    exhaustiveSample  bool
    threads           int
    excludePatterns   []string
    excludeHidden     bool
}

// parseFlags extracts and validates CLI flags
func parseFlags(cmd *cobra.Command) (*config, error) {
    path, err := cmd.Flags().GetString("path")
    if err != nil {
        return nil, err
    }

    errorLog, _ := cmd.Flags().GetString("error-log")
    samplingPercentage, _ := cmd.Flags().GetInt16("sampling-percentage")
    if samplingPercentage < 1 {
        return nil, errors.New("ERROR: Sampling percentage must be greater than 0")
    }
    if samplingPercentage > 100 {
        return nil, errors.New("ERROR: Sampling percentage must be less than 100")
    }
    
    exhaustiveSample, _ := cmd.Flags().GetBool("exhaustive-sample")
    threads, _ := cmd.Flags().GetInt("threads")
    excludePatterns, _ := cmd.Flags().GetStringSlice("exclude")
    excludeHidden, _ := cmd.Flags().GetBool("exclude-hidden")

    return &config{
        path:              path,
        errorLog:          errorLog,
        samplingPercentage: samplingPercentage,
        exhaustiveSample:  exhaustiveSample,
        threads:           threads,
        excludePatterns:   excludePatterns,
        excludeHidden:     excludeHidden,
    }, nil
}

// calculateSampleCount determines how many samples to take based on configuration
func calculateSampleCount(totalSize int64, cfg *config) int64 {
    partitionCount := totalSize / SAMPLE_LEN
    if cfg.exhaustiveSample {
        return partitionCount
    }
    sampleRatio := float64(cfg.samplingPercentage) / 100.0
    return int64(float64(partitionCount) * sampleRatio)
}

// submitCompressionJobs generates and submits compression work to the job channel
func submitCompressionJobs(sampler *wr.Chooser, sampleCount int64, jobs chan<- fileInfo) {
    samplesPerBuffer := int64(DEFAULT_SAMPLES_PER_BUFFER)
    bufferCount := (sampleCount / samplesPerBuffer) + 1

    for i := range bufferCount {
        if i == bufferCount-1 {
            samplesPerBuffer = sampleCount % samplesPerBuffer
        }

        buffer := make(map[string]fileInfo)
        for range samplesPerBuffer {
            sample := sampler.Pick().(fileInfo)
            currentValue := buffer[sample.path].count
            buffer[sample.path] = fileInfo{sample.path, sample.size, currentValue + 1}
        }

        for _, val := range buffer {
            jobs <- val
        }
    }
}

// displayResults prints the final compression results
func displayResults(res compressResult) {
    var ratio float64
    if res.postCompress > 0 {
        ratio = float64(res.preCompress) / float64(res.postCompress)
    } else {
        fmt.Println("\n\nError: No data was compressed successfully")
        os.Exit(1)
    }

    fmt.Println("\n\n-- Comprestimator Results ---------------")
    fmt.Printf("Estimated Compression Ratio %.3fx\n", ratio)
    fmt.Printf("Pre-compression size: %v\nPost-compression size: %v\n\n",
        prettyBytes(res.preCompress), prettyBytes(res.postCompress))

    if ratio > FCM4_MAX_COMPRESSION_RATIO {
        fmt.Println("Note: FCM4 drives are limited to 4x physical space. Use a compression ratio of 4x when provisioning vdisksets")
    }
}

// Comprestimator tool entry point
func runComprestimator(cmd *cobra.Command) {
    fmt.Println("-- IBM ESS Comprestimator v2.0.0 --------")

    cfg, err := parseFlags(cmd)
    if err != nil {
        fmt.Println(err)
        os.Exit(1)
    }

    // Set up error logging
    var errorLogger *log.Logger
    var errorFile *os.File
    if cfg.errorLog != "" {
        errorFile, err = os.Create(cfg.errorLog)
        if err != nil {
            // Try temp directory as fallback
            tempLog := filepath.Join(os.TempDir(), "comprestimator_errors.log")
            errorFile, err = os.Create(tempLog)
            if err != nil {
                fmt.Fprintf(os.Stderr, "Note: Error logging disabled (filesystem is read-only)\n")
            } else {
                defer errorFile.Close()
                errorLogger = log.New(errorFile, "", log.LstdFlags)
                fmt.Fprintf(os.Stderr, "Note: Error log created at %s\n", tempLog)
            }
        } else {
            defer errorFile.Close()
            errorLogger = log.New(errorFile, "", log.LstdFlags)
        }
    }

    sampler, totalSize, err := buildSampler(cfg.path, errorLogger, cfg.excludePatterns, cfg.excludeHidden)
    if err != nil {
        fmt.Println(err)
        os.Exit(1)
    }

    fmt.Println()
    jobs := make(chan fileInfo, 1)
    intermediateResults := make(chan compressResult, 1)

    var compressorsGroup sync.WaitGroup
    for i := 0; i < cfg.threads; i++ {
        compressorsGroup.Go(func() {
            compressorWorker(jobs, intermediateResults, errorLogger)
        })
    }

    sampleCount := calculateSampleCount(totalSize, cfg)
    finalResult := make(chan compressResult, 1)
    go accumulateResults(intermediateResults, finalResult, sampleCount)

    submitCompressionJobs(sampler, sampleCount, jobs)
    close(jobs)

    compressorsGroup.Wait()
    close(intermediateResults)

    res := <-finalResult
    displayResults(res)
}
