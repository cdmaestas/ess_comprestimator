# ESS Comprestimator v2.0.0 Guide

The ESS Comprestimator tool estimates the compression ratio that can be achieved on an IBM Storage Scale System with Flash Core Modules (FCM) for a given file or directory. Given an input path, the tool provides an estimate of the compression ratio that an FCM-based ESS system will achieve for that input.

## Requirements

- **Operating System**: Linux, macOS, or Windows

## Installation

1. Download the appropriate pre-compiled binary for your platform from the releases page:
   - `ess_comprestimator-linux-amd64` for Linux (x86_64)
   - `ess_comprestimator-darwin-amd64` for macOS (Intel)
   - `ess_comprestimator-darwin-arm64` for macOS (Apple Silicon)
   - `ess_comprestimator-windows-amd64.exe` for Windows

2. Make the binary executable (Linux/macOS only):
   ```bash
   chmod +x ess_comprestimator
   ```

3. Optionally, move it to a directory in your PATH for easier access:
   ```bash
   sudo mv ess_comprestimator /usr/local/bin/
   ```

## Usage

### Basic Usage

Run the tool by providing an input path:

```bash
./ess_comprestimator --path /INPUT_PATH
```

The tool will output the estimated compression ratio for the given path.

### Command-Line Options

#### Required Flags

- `--path, -p`: Path to the file or directory to analyze

#### Optional Flags

- `--sampling-percentage`: Percentage of data to sample (default: 10)
  - Higher values provide more accurate results but take longer
  - Lower values are faster but less accurate
  - Must be between 1 and 100

- `--exhaustive-sample`: Sample the entire directory for maximum accuracy
  - Mutually exclusive with `--sampling-percentage`
  - Significantly increases runtime for large directories
  - Recommended for directories where maximum accuracy is required

- `--threads`: Number of threads to use for processing (default: number of logical CPUs)
  - Adjust based on your system's capabilities

- `--error-log`: Path to log file for errors (default: comprestimator_errors.log)
  - Logs files that couldn't be read or compressed
  - Useful for troubleshooting and understanding which files were skipped

- `--exclude`: Glob patterns to exclude files/directories (can be specified multiple times)
  - Example: `--exclude "*.log" --exclude "*.tmp"`
  - Supports standard glob patterns (*, ?, [])
  - Matches against file/directory names, not full paths

- `--exclude-hidden`: Exclude hidden files and directories
  - Excludes files and directories starting with '.'
  - Useful for skipping system files and hidden directories

### Examples

**Standard Analysis (10% sampling)**
```bash
./ess_comprestimator --path /data/myfiles
```

**Maximum Accuracy (exhaustive sampling)**
```bash
./ess_comprestimator --path /data/myfiles --exhaustive-sample
```

**Custom Sampling Percentage**
```bash
./ess_comprestimator --path /data/myfiles --sampling-percentage 50
```

**Logging errors to a custom file**
```bash
./ess_comprestimator --path /data/myfiles --error-log errors.log
```

**Custom Thread Count**
```bash
./ess_comprestimator --path /data/myfiles --threads 8
```
**Excluding Files by Pattern**
```bash
# Exclude log files and temporary files
./ess_comprestimator --path /data/myfiles --exclude "*.log" --exclude "*.tmp"

# Exclude specific directories
./ess_comprestimator --path /data/myfiles --exclude "cache" --exclude "temp"
```

**Excluding Hidden Files**
```bash
./ess_comprestimator --path /data/myfiles --exclude-hidden
```

**Combined Exclusions**
```bash
./ess_comprestimator --path /data/myfiles \
  --exclude-hidden \
  --exclude "*.log" \
  --exclude "*.tmp" \
  --exclude "node_modules" \
  --error-log errors.log
```


## Understanding the Results

The tool outputs:
- **Estimated Compression Ratio**: The ratio of original size to compressed size (e.g., 3.5x means data compresses to ~28% of original size)
- **Pre-compression size**: Total size of sampled data before compression
- **Post-compression size**: Total size of sampled data after compression

### Important Notes

- **FCM4 Drive Limitation**: FCM4 drives are limited to 4x physical space. If your estimated ratio exceeds 4x, use 4x when provisioning vdisksets.

- **Sampling Accuracy**: By default, the tool samples 10% of files from directories for speed. This provides good accuracy for most use cases, especially for:
  - Individual files
  - Directories less than 10GB
  - Directories with uniform file types

- **Large Directories**: For directories larger than 10GB with varied file types, consider:
  - Using `--exhaustive-sample` for maximum accuracy (slower)
  - Increasing `--sampling-percentage` for better accuracy without full exhaustive sampling
  - Using error log (comprestimator_errors.log by default) to identify any files that couldn't be processed

- **Performance Tuning**:
  - Adjust `--threads` based on your system's CPU cores
  - Lower `--sampling-percentage` for faster results on very large directories
  - Higher `--sampling-percentage` for more accurate results

- **File Exclusions**:
  - Use `--exclude` to skip files that shouldn't be included in compression estimates (logs, temp files, etc.)
  - Use `--exclude-hidden` to skip hidden files and directories (common on Unix-like systems)
  - Exclusions can significantly speed up processing and improve accuracy by focusing on relevant files


## Troubleshooting

### Files Couldn't Be Read

If you see warnings about files that couldn't be read:
- Examine error logs to see which specific files had issues
- Check file permissions
- Verify the path is accessible

### Slow Performance

For very large directories:
- Reduce `--sampling-percentage` (e.g., `--sampling-percentage 5`)
- Adjust `--threads` to match your system's capabilities
- Avoid `--exhaustive-sample` unless maximum accuracy is required

## Building from Source

If you need to build from source:

```bash
# Clone the repository
git clone https://github.com/IBM/ess_comprestimator.git
cd ess_comprestimator

# Build
go build -o ess_comprestimator

# Run
./ess_comprestimator --path /your/path
```

## Support

For issues, questions, or contributions, please visit the project repository
or reach out to schez@ibm.com