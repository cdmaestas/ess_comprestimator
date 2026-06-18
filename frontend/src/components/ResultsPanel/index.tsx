/**
 * ResultsPanel — full results view for a completed job.
 *
 * Layout:
 *   ┌─────────────────────────────────┐
 *   │  RatioTile (headline metric)    │
 *   ├─────────────────────────────────┤
 *   │  BlockDistChart (zero vs data)  │
 *   ├─────────────────────────────────┤
 *   │  SizeComparisonChart (pre/post) │
 *   ├─────────────────────────────────┤
 *   │  Run metadata StructuredList    │
 *   ├─────────────────────────────────┤
 *   │  [↓ Download CSV]               │
 *   └─────────────────────────────────┘
 */

import { Button } from '@carbon/react'
import { Download } from '@carbon/icons-react'
import type { CompressionResult } from '../../api/types'
import RatioTile from './RatioTile'
import BlockDistChart from './BlockDistChart'
import SizeComparisonChart from './SizeComparisonChart'

const C_TEXT_SEC = '#c6c6c6'
const C_DIVIDER  = '#393939'

// initial_size / compressed_size from the C binary are already in MB
function fmtMB(mb: number): string {
  if (mb >= 1_024)  return `${(mb / 1_024).toFixed(2)} GB`
  if (mb >= 1)      return `${mb.toFixed(3)} MB`
  if (mb >= 0.001)  return `${(mb * 1_024).toFixed(1)} KB`
  return `${(mb * 1_048_576).toFixed(0)} B`
}

function fmtSecs(s: number | null | undefined): string {
  if (s == null) return '—'
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`
}

interface Props {
  result: CompressionResult
  jobId: string
}

export default function ResultsPanel({ result, jobId }: Props) {
  const csvHref = `/api/jobs/${jobId}/results.csv`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

      {/* ── Headline ratio ───────────────────────────────────────────── */}
      <RatioTile result={result} />

      {/* ── Block distribution ───────────────────────────────────────── */}
      {(result.num_zero_blocks != null || result.num_non_zero_blocks != null) && (
        <>
          <hr style={{ border: 'none', borderTop: `1px solid ${C_DIVIDER}`, margin: 0 }} />
          <BlockDistChart result={result} />
        </>
      )}

      {/* ── Size comparison ──────────────────────────────────────────── */}
      {result.initial_size > 0 && result.compressed_size > 0 && (
        <>
          <hr style={{ border: 'none', borderTop: `1px solid ${C_DIVIDER}`, margin: 0 }} />
          <SizeComparisonChart result={result} />
        </>
      )}

      {/* ── Run metadata ─────────────────────────────────────────────── */}
      <hr style={{ border: 'none', borderTop: `1px solid ${C_DIVIDER}`, margin: 0 }} />

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
        <tbody>
          {([
            ['Sample size (pre)',  fmtMB(result.initial_size)],
            ['Sample size (post)', fmtMB(result.compressed_size)],
            ['Reduction',
              result.initial_size > 0
                ? `${((1 - result.compressed_size / result.initial_size) * 100).toFixed(1)}%`
                : '—'],
            result.skipped_bytes_mb != null && result.skipped_bytes_mb > 0
              ? ['Skipped (incompressible)', (() => {
                  const total = result.initial_size + result.skipped_bytes_mb
                  const pct = total > 0 ? (result.skipped_bytes_mb / total * 100).toFixed(1) : '0.0'
                  return `${fmtMB(result.skipped_bytes_mb)} (${pct}% of sample) — likely .zip, .jpg, .mp4 or encrypted files`
                })()] : null,
            result.total_blocks_read != null
              ? ['Blocks read', result.total_blocks_read.toLocaleString()] : null,
            result.conf_comp != null
              ? ['Statistical confidence',
                  `≥${((1 - result.conf_comp) * 100).toFixed(1)}%` +
                  (result.conf_zeros != null
                    ? ` (zero-block: ≥${((1 - result.conf_zeros) * 100).toFixed(1)}%)`
                    : '')] : null,
            result.tot_time != null
              ? ['Run time', fmtSecs(result.tot_time)] : null,
          ] as ([string, string] | null)[])
            .filter((row): row is [string, string] => row !== null)
            .map(([label, value]) => (
              <tr key={label} style={{ borderBottom: `1px solid ${C_DIVIDER}` }}>
                <td style={{ padding: '0.5rem 0', color: C_TEXT_SEC, width: '50%' }}>{label}</td>
                <td style={{ padding: '0.5rem 0', color: '#f4f4f4' }}>{value}</td>
              </tr>
            ))}
        </tbody>
      </table>

      {/* ── CSV download ─────────────────────────────────────────────── */}
      <Button
        kind="ghost"
        size="sm"
        renderIcon={Download}
        href={csvHref}
        // 'download' is valid on <a> but not typed on Button — cast to any
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        {...({ download: `comprestimator_${jobId.slice(0, 8)}.csv` } as any)}
      >
        Download CSV
      </Button>
    </div>
  )
}
