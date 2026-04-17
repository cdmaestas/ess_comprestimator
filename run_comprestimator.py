from queue import Queue
from threading import Thread
from enum import Enum
import argparse
import os
import random
import time
from typing import Generator
import zlib
from fnmatch import fnmatch
from pathlib import Path
from collections import Counter


FCM_BLOCKSIZE = 512
LOG_INTERVAL = 100
DEFAULT_SAMPLING_PERCENTAGE = 1
KNOWN_COMPRESSED_FILE_SUFFIXES = [".png", ".jpg", ".jpeg", ".gif", ".mp3", ".mp4", ".docx", ".xlsx", ".zip", ".rar", ".bz", ".gz"]


def is_excluded(root, file_name, excluded_patterns, skip_hidden, verbose):
    full_path = os.path.join(root,file_name)
    should_hide = (skip_hidden and file_name.startswith(".")) or \
        any((fnmatch(full_path, pattern) or \
             fnmatch(file_name, pattern)) for pattern in excluded_patterns)
    if should_hide and verbose:
        print(full_path, "is excluded, won't evaluate")
    return should_hide


def try_adding_file(file_path, files_with_sizes):
    if not os.path.isfile(file_path):
        return 0
    try:
        file_size = os.lstat(file_path).st_size
        files_with_sizes.append((file_path, file_size))
        return file_size
    except OSError:
        print(f"OSError when adding file {file_path} for consideration")
        return 0
    except Exception as e:
        print(f"Error when adding file {file_path} for consideration: {e}")
        return 0


def pretty_units(size_in_bytes):
    """
    Convert a size in bytes to a human-readable format
    """
    
    units = ['bytes', 'KB', 'MB', 'GB', 'TB']
    for unit in range(1, len(units)):
        if size_in_bytes < 1024 ** (unit + 1):
            return f"{size_in_bytes / 1024 ** unit:.2f} {units[unit]}"
    return f"{size_in_bytes / 1024 ** len(units):.2f} {units[-1]}"


class BlockAbstraction():
    """
        Abstracts a directory (or a file) into a single block object that 
        can be indexed into and read from as if it were a block device
    """

    def __build_dir_mapping__(self):
        files_with_sizes: list[tuple[str, int]] = []
        total_size = 0
        print("\rMapping directory... ",
          end="", flush=True)

        # Walk directory, collecting files and their sizes
        i = 0
        for root, dirs, files in os.walk(self.path):
            # exclude paths we dont want
            dirs[:] = [d for d in dirs if not is_excluded(root, d, self.flags.exclude, self.flags.skip_hidden, self.flags.verbose)]
            files[:] = [f for f in files if not is_excluded(root, f, self.flags.exclude, self.flags.skip_hidden, self.flags.verbose)]

            if self.flags.skip_nested_directories:
                print(" Skipping nested directories")
                dirs = []

            # for remaining files, consider them for sampling
            for file_name in files:
                file_path = os.path.join(root, file_name)
                total_size += try_adding_file(file_path, files_with_sizes)
            i += 1
            if i % 1000 == 0:
                print(f"\rMapping directory... {pretty_units(total_size)} found across {len(files_with_sizes)} files", end="", flush=True)
        print(f"\rMapping directory... {pretty_units(total_size)} found across {len(files_with_sizes)} files", flush=True)


        if len(files_with_sizes) == 0 or total_size == 0:
            raise Exception("Target directory is empty or all files are empty!")
        
        if total_size < 1_000_000:
            print("Warning: Target directory is < 1 MB in size. For accurate results, more data is required")

        return files_with_sizes, total_size

    def __init__(self, path: str, args):
        self.path = path
        self.flags = args
        self.files_processed = []
        self.messages = []

        if os.path.isdir(path):
            mapping, size = self.__build_dir_mapping__()
            self.__dir_mapping__ = mapping
            self.size = size
        else:
            self.size = os.lstat(path).st_size
            self.__dir_mapping__ = [(path, self.size)]
            print(f"Found 1 file totalling {pretty_units(self.size)}")

    def repeated_random_read(self, file, size, read_count, read_size) -> Generator[bytes, None]:
        positions: list[int] = []
        if read_size > size:
            positions = [0] * read_count
        else:
            positions = sorted([random.randint(0, size-read_size) for _ in range(read_count)])

        try:
            with open(file, 'rb') as f:
                for pos in positions:
                    f.seek(pos)
                    data_segment = f.read(read_size)
                    yield data_segment
        except Exception as e:
            print(f"\n\nError reading file {file}: {e} ... Skipping\n")
            return None
        return

    def sample(self, num_samples):
        _, weights = zip(*self.__dir_mapping__)
        pre_sample_time = time.perf_counter()
        sample = list(random.choices(self.__dir_mapping__, weights=weights, k=num_samples))
        counted_samples = Counter(sample).items()
        post_sample_time = time.perf_counter()

        self.messages.append(f"\tTime building sample: {post_sample_time - pre_sample_time}")
        return counted_samples


def parse_arguments():
    """Parse and validate command line arguments."""

    # type validation for argparsing --path 
    def validate_path(path: str) -> str:
        """
        Checks if a given path is a valid directory or file
        """
        if not os.path.isdir(path) and not os.path.isfile(path):
            raise argparse.ArgumentTypeError(f"'{path}' does not exist as a file or directory")
        return path


    # type validation for argparsing --sampling-percentage
    def percent_type(value):
        if not value.endswith('%'):
            raise argparse.ArgumentTypeError("Percentage must end with '%'")
        try:
            percentage = float(value[:-1])
            if not (0 <= percentage <= 100):
                raise argparse.ArgumentTypeError("Percentage must be between 0 and 100")
            return percentage/100
        except ValueError:
            raise argparse.ArgumentTypeError("Invalid percentage value")

    parser = argparse.ArgumentParser(description="Estimates FCM Compression on GPFS for a given input file/directory")
    parser.add_argument('-p', '--path', type=validate_path, required=True, help="Path to input file/directory")

    sampling_args = parser.add_mutually_exclusive_group()
    sampling_args.add_argument('--exhaustive-sampling', action="store_true",
                              help="Samples entire input directory for greatest accuracy. Note this will be slow on large directories")
    sampling_args.add_argument('--sampling-percentage', type=percent_type, default=DEFAULT_SAMPLING_PERCENTAGE,
                              help="Percentage of input directory size to sample (e.g. 10%%). Increasing this percentage will increase accuracy but slow down the tool.")
    
    parser.add_argument('--threads', type=int, default=0, help="Number of threads to use for sampling (Defaults to # of CPU Cores)")
    parser.add_argument(
        '--exclude',
        metavar='FILE',
        type=str,
        nargs='*',
        default=[],
        help='File/Directory names to exclude (can be used multiple times to exclude multiple files)'
    )
    parser.add_argument('--verbose', action="store_true", help="Will output detailed logging information")
    parser.add_argument('--skip-nested-directories', action="store_true",
                       help="Will not sample directories nested within target directory, only files")
    parser.add_argument('--skip-hidden', action="store_true",
                       help="Will not sample hidden directories and files within the target directory")
    return parser.parse_args()


def _print_compression_progress(pre_compression, post_compression, samples_taken, num_samples, time_elapsed):
    """Print real-time compression progress."""
    ratio = pre_compression / post_compression
    progress = samples_taken / num_samples * 100
    compressor_rate = int(pre_compression / time_elapsed)
    print(f"\rEstimated Compression Ratio: {ratio:.3f}x | {progress:.2f}% ({pretty_units(compressor_rate)}/s)",
          end="", flush=True)


def compress_sample(block_data, processing_queue, results_queue):
    """Compression thread to run in parallel with the main thread."""
    # thread_id = random.randint(1, 1000)
    while True:
        # Get the next sample
        task = processing_queue.get()
        # print(f"{thread_id} - got an item to process!")
        if task is None:
            processing_queue.task_done()
            results_queue.put(None)
            return

        # Compress the sample
        entry, count = task
        file, size = entry
        # pre_compression = 0
        # post_compression= 0
        for buffer in block_data.repeated_random_read(file, size, count, FCM_BLOCKSIZE):
            if buffer is None:
                continue

            compressor = zlib.compressobj(level=1, memLevel=1, wbits=-9)
            pre_compression = len(buffer)
            post_compression = (
                len(compressor.compress(buffer)) +
                len(compressor.flush())
            )
            results_queue.put((pre_compression, post_compression))

        processing_queue.task_done()


def compress_samples(block_data: BlockAbstraction, num_samples, num_threads=1):
    """
    Compress samples and track metrics.
    
    Returns:
        tuple: (pre_compression, post_compression, time_compressing)
    """
    pre_compression = 0
    post_compression = 0
    
    pre_compress_time = time.perf_counter()
    samples = block_data.sample(num_samples)
    
    # prepare samples for multi-threaded processing
    processing_queue = Queue()
    results_queue = Queue()
    for sample in samples:
        processing_queue.put(sample)
    for _ in range(num_threads):
        processing_queue.put(None)

    # start up compressor threads
    threads = []
    for _ in range(num_threads):
        thread = Thread(target=compress_sample, args=(block_data, processing_queue, results_queue))
        thread.start()
        threads.append(thread)
    print(f"Started {len(threads)} compressor threads")

    # accumulate results from the compressor threads
    threads_finished = 0
    i = 0
    while threads_finished < num_threads:
        result = results_queue.get()
        if result is None:
            threads_finished += 1
            continue
        # print("hello")
        i += 1
        pre_compression += result[0]
        post_compression += result[1]
        if i % LOG_INTERVAL == 0:
            time_elapsed = time.perf_counter() - pre_compress_time
            _print_compression_progress(pre_compression, post_compression, i, num_samples, time_elapsed)
    
    time_compressing = time.perf_counter() - pre_compress_time
    return pre_compression, post_compression, time_compressing


def print_results(pre_compression, post_compression, start_time, finish_tree_time,
                 finish_sample_time, time_compressing, messages):
    """Print final compression results and timing information."""
    print("\n")
    print("*" * 20)
    print("Comprestimator Results:")
    print(f"Pre-compression sample size  : {pre_compression} bytes ({pretty_units(pre_compression)})")
    print(f"Post-compression sample size : {post_compression} bytes ({pretty_units(post_compression)})")
    
    if post_compression == 0:
        print("Error! Post-compression size is 0; Cannot get compression ratio")
    else:
        ratio = pre_compression / post_compression
        print(f"Estimated Compression Ratio  : {ratio:.3f}x")
    
    print()
    print("Time Mapping Directory: ", finish_tree_time - start_time)
    print("Time Sampling: ", finish_sample_time - finish_tree_time)
    
    for message in messages:
        print(message)
    
    print("\tTime compressing: ", time_compressing)
    print("Total time: ", finish_sample_time - start_time)


def main():
    # Parse arguments
    args = parse_arguments()

    # Get the number of threads to use
    num_threads = 1
    if args.threads > 0:
        num_threads = args.threads
    else:
        cpu_count = os.cpu_count()
        if cpu_count is not None:
            num_threads = cpu_count
            num_threads = 1
    
    # Build block abstraction and calculate samples
    start = time.perf_counter()
    block_data = BlockAbstraction(args.path, args)
    finish_tree_time = time.perf_counter()
    
    partition_count = block_data.size // FCM_BLOCKSIZE
    num_samples = partition_count if args.exhaustive_sampling else int(partition_count * args.sampling_percentage)
    
    print(f"Sampling {num_samples/partition_count*100:.2f}% of target ({pretty_units(num_samples*FCM_BLOCKSIZE)})...", end=" ")
    

    pre_compression, post_compression, time_compressing = compress_samples(block_data, num_samples, num_threads)
    finish_sample_time = time.perf_counter()
    
    # Print results
    print_results(pre_compression, post_compression, start, finish_tree_time,
                 finish_sample_time, time_compressing, block_data.messages)


if __name__ == "__main__":
    main()