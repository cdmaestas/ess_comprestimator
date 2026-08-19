package cmd

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/minio/minlz"
)

func TestPrettyBytes(t *testing.T) {
	cases := []struct {
		in   int64
		want string
	}{
		{0, "0.00 bytes"},
		{512, "512.00 bytes"},
		{1024, "1.00 KB"},
		{1536, "1.50 KB"},
		{1048576, "1.00 MB"},
		{1572864, "1.50 MB"},    // integer division used to truncate this to 1.00 MB
		{2040109465, "1.90 GB"}, // used to truncate to 1.00 GB
		{1125899906842624, "1.00 PB"},
	}
	for _, c := range cases {
		if got := prettyBytes(c.in); got != c.want {
			t.Errorf("prettyBytes(%d) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestCalculateSampleCount(t *testing.T) {
	cfg := &config{samplingPercentage: 10}
	if got := calculateSampleCount(100*SAMPLE_LEN, cfg); got != 10 {
		t.Errorf("10%% of 100 partitions = %d, want 10", got)
	}
	cfg = &config{exhaustiveSample: true}
	if got := calculateSampleCount(100*SAMPLE_LEN, cfg); got != 100 {
		t.Errorf("exhaustive of 100 partitions = %d, want 100", got)
	}
}

// minlz.TryEncode must return non-nil for clearly compressible input at the
// level the tool uses — if this fails, every sample is misclassified as
// incompressible and the binary reports "No data was compressed successfully"
// for any input. minlz's fast levels (LevelSuperFast/LevelFastest) do exactly
// that on non-amd64 builds; see COMPRESSION_LEVEL in root.go.
func TestMinlzTryEncodeCompressibleText(t *testing.T) {
	sample := bytes.Repeat([]byte("compressible line of text\n"), 700)[:SAMPLE_LEN]
	got := minlz.TryEncode(nil, sample, COMPRESSION_LEVEL)
	if got == nil {
		t.Fatalf("TryEncode(level %d) returned nil for highly compressible %d-byte input", COMPRESSION_LEVEL, len(sample))
	}
	if len(got) >= len(sample) {
		t.Errorf("compressed size %d >= input size %d", len(got), len(sample))
	}
}

func TestCompressSampleOnTextFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "text.txt")
	data := bytes.Repeat([]byte("compressible line of text\n"), 4096) // ~104 KB
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}

	pre, post, samples, skipped, err := compressSample(fileInfo{path: path, size: int64(len(data)), count: 4})
	if err != nil {
		t.Fatalf("compressSample: %v", err)
	}
	if samples != 4 {
		t.Errorf("samples = %d, want 4", samples)
	}
	if pre == 0 || post == 0 {
		t.Errorf("compressible file produced pre=%d post=%d skipped=%d — samples were misclassified as incompressible", pre, post, skipped)
	}
	if post >= pre {
		t.Errorf("post %d >= pre %d for compressible data", post, pre)
	}
}

func TestBuildSamplerSkipsExcluded(t *testing.T) {
	dir := t.TempDir()
	must := func(err error) {
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.WriteFile(filepath.Join(dir, "keep.dat"), bytes.Repeat([]byte{1}, 2048), 0o644))
	must(os.WriteFile(filepath.Join(dir, "skip.log"), bytes.Repeat([]byte{2}, 4096), 0o644))

	_, totalSize, err := buildSampler(dir, nil, []string{"*.log"}, false)
	if err != nil {
		t.Fatalf("buildSampler: %v", err)
	}
	if totalSize != 2048 {
		t.Errorf("totalSize = %d, want 2048 (excluded file was counted)", totalSize)
	}
}

func TestParseResultsLineFormat(t *testing.T) {
	// The Python backend regex-parses these exact phrases; keep them stable.
	for _, phrase := range []string{
		"Estimated Compression Ratio",
		"Pre-compression size:",
		"Post-compression size:",
	} {
		if !strings.Contains(resultsFormatCanary, phrase) {
			t.Errorf("results output no longer contains %q — backend/models/results.py regexes will break", phrase)
		}
	}
}

// Canary mirroring the Printf formats in displayResults. If you change the
// output format there, update this AND backend/models/results.py together.
const resultsFormatCanary = `Estimated Compression Ratio %.3fx
Pre-compression size: %v
Post-compression size: %v`
