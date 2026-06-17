"""
Pydantic model for a parsed comprestimator CSV result row.

The C binary appends two rows to results.csv per run:

  Row N-1 (header):  date, dev_name, size_mb, num_procs, exhaustive
  Row N   (data):    num_zero_blocks, num_non_zero_blocks, total_blocks_read,
                     compression_ratio, conf_comp, dev_size_mb,
                     after_zero_size, after_zero_perc, conf_zeros,
                     after_rtc_size, after_rtc_perc, error, tot_time
                     (13 fields, 0-indexed 0–12)

The Python wrapper extracts:
    initial_size    = data_row[12]   → after_rtc_size  (pre-compression effective size)
    compressed_size = data_row[15]   → after_rtc_perc  (post-compression size)

Wait — the original run_comprestimator.py reads the *last* row of the CSV
(which may accumulate across runs) using indices 12 and 15.  The header row
written at binary start has 5 fields; the data row appended at binary exit
starts at column 0 of a *new* row.  So indices 12 and 15 are within the
data-only row (0-indexed).

We preserve those exact indices here and expose additional fields as Optional
so future C binary updates can populate them without breaking the parser.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class CompressionResult(BaseModel):
    # Core metrics (always present)
    initial_size: float          # data_row[12] — effective pre-compression size
    compressed_size: float       # data_row[15] — post-compression size
    compression_ratio: float     # derived: initial_size / compressed_size

    # Block counts (indices 0–2)
    num_zero_blocks: Optional[int] = None
    num_non_zero_blocks: Optional[int] = None
    total_blocks_read: Optional[int] = None

    # Confidence / sizing fields (indices 3–11, 13–14)
    ratio_from_binary: Optional[float] = None   # index 3 — ratio reported by C binary
    conf_comp: Optional[float] = None           # index 4 — compression confidence
    dev_size_mb: Optional[float] = None         # index 5 — device size MB
    after_zero_size: Optional[float] = None     # index 6 — size after zero removal
    after_zero_perc: Optional[float] = None     # index 7 — % after zero removal
    conf_zeros: Optional[float] = None          # index 8 — zero-block confidence
    after_rtc_size: Optional[float] = None      # index 9 — size after RTC compression
    after_rtc_perc: Optional[float] = None      # index 10 — % after RTC compression
    error: Optional[float] = None               # index 11 — reported error value
    tot_time: Optional[float] = None            # index 12 in data row → raw index varies

    # Human-friendly interpretation
    interpretation: str = ""

    @classmethod
    def from_csv_row(cls, row: list[str]) -> "CompressionResult":
        """
        Parse a data row from results.csv into a CompressionResult.

        The CSV data row produced by the C binary has at least 16 fields
        (indices 0–15).  The Python wrapper uses indices 12 and 15.
        """

        def _float(idx: int) -> Optional[float]:
            try:
                return float(row[idx]) if idx < len(row) else None
            except (ValueError, TypeError):
                return None

        def _int(idx: int) -> Optional[int]:
            try:
                v = _float(idx)
                return int(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        initial_size = _float(12) or 0.0
        compressed_size = _float(15) or 0.0

        if compressed_size == 0:
            ratio = 0.0
            interpretation = "Error: post-compression size is 0; cannot compute ratio"
        else:
            ratio = initial_size / compressed_size
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
            num_zero_blocks=_int(0),
            num_non_zero_blocks=_int(1),
            total_blocks_read=_int(2),
            ratio_from_binary=_float(3),
            conf_comp=_float(4),
            dev_size_mb=_float(5),
            after_zero_size=_float(6),
            after_zero_perc=_float(7),
            conf_zeros=_float(8),
            after_rtc_size=_float(9),
            after_rtc_perc=_float(10),
            error=_float(11),
            tot_time=_float(13),
            interpretation=interpretation,
        )
