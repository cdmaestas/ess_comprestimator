"""
Pydantic model for a parsed ess_comprestimator v2 result.

The Go binary (v2) writes results to stdout in this format:

    -- Comprestimator Results ---------------
    Estimated Compression Ratio 2.400x
    Pre-compression size: 128.00 MB
    Post-compression size: 53.33 MB

    Note: FCM4 drives are limited to 4x physical space...

from_stdout() parses that text and returns a CompressionResult with sizes in MB.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

_UNITS_TO_MB = {
    "bytes": 1 / 1_048_576,
    "kb":    1 / 1_024,
    "mb":    1.0,
    "gb":    1_024.0,
    "tb":    1_048_576.0,
    "pb":    1_073_741_824.0,
}

_RE_RATIO  = re.compile(r"Estimated Compression Ratio\s+([\d.]+)x", re.IGNORECASE)
_RE_PRE    = re.compile(r"Pre-compression size:\s+([\d.]+)\s*(\w+)", re.IGNORECASE)
_RE_POST   = re.compile(r"Post-compression size:\s+([\d.]+)\s*(\w+)", re.IGNORECASE)


def _parse_size_mb(value: str, unit: str) -> float:
    factor = _UNITS_TO_MB.get(unit.lower(), 1.0)
    return float(value) * factor


class CompressionResult(BaseModel):
    # Sizes in MB (matches the Go binary's prettyBytes output unit)
    initial_size: float
    compressed_size: float
    compression_ratio: float

    # Optional extended fields (not produced by v2 binary; kept for API stability)
    num_zero_blocks: Optional[int] = None
    num_non_zero_blocks: Optional[int] = None
    total_blocks_read: Optional[int] = None
    conf_comp: Optional[float] = None
    conf_zeros: Optional[float] = None
    tot_time: Optional[float] = None

    interpretation: str = ""

    @classmethod
    def from_stdout(cls, stdout: str) -> "CompressionResult":
        """Parse the Go binary's stdout and return a CompressionResult."""
        ratio_m  = _RE_RATIO.search(stdout)
        pre_m    = _RE_PRE.search(stdout)
        post_m   = _RE_POST.search(stdout)

        if not (ratio_m and pre_m and post_m):
            raise ValueError(
                "Could not find compression results in binary output. "
                "Check the job log for errors."
            )

        ratio          = float(ratio_m.group(1))
        initial_size   = _parse_size_mb(pre_m.group(1),  pre_m.group(2))
        compressed_size = _parse_size_mb(post_m.group(1), post_m.group(2))

        if ratio >= 4.0:
            interpretation = f"{ratio:.2f}x — Excellent compression candidate"
        elif ratio >= 2.0:
            interpretation = f"{ratio:.2f}x — Good compression candidate"
        elif ratio >= 1.3:
            interpretation = f"{ratio:.2f}x — Moderate compression benefit"
        else:
            interpretation = f"{ratio:.2f}x — Low compression benefit"

        return cls(
            initial_size=initial_size,
            compressed_size=compressed_size,
            compression_ratio=ratio,
            interpretation=interpretation,
        )
