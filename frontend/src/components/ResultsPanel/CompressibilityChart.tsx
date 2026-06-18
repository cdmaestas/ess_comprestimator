/**
 * CompressibilityChart — shows compressible vs non-compressible data breakdown
 */

import type { CompressionResult } from '../../api/types'

const C_COMPRESSIBLE = '#42be65'     // IBM green
const C_INCOMPRESSIBLE = '#da1e28'   // IBM red
const C_TEXT_PRIMARY = '#f4f4f4'
const C_TEXT_SEC = '#c6c6c6'

function fmtMB(mb: number): string {
  if (mb >= 1_024) return `${(mb / 1_024).toFixed(2)} GB`
  if (mb >= 1) return `${mb.toFixed(2)} MB`
  if (mb >= 0.001) return `${(mb * 1_024).toFixed(1)} KB`
  return `${(mb * 1_048_576).toFixed(0)} B`
}

interface Props {
  result: CompressionResult
}

export default function CompressibilityChart({ result }: Props) {
  const compressible = result.initial_size
  const incompressible = result.skipped_bytes_mb || 0
  const total = compressible + incompressible

  if (total === 0 || incompressible === 0) {
    return null // Don't show chart if no incompressible data
  }

  const compressiblePct = (compressible / total) * 100
  const incompressiblePct = (incompressible / total) * 100

  return (
    <div>
      <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: C_TEXT_PRIMARY, marginBottom: '1rem' }}>
        Data Compressibility
      </h3>

      {/* Stacked bar */}
      <div style={{ display: 'flex', height: '3rem', borderRadius: '4px', overflow: 'hidden', marginBottom: '1rem' }}>
        <div
          style={{
            width: `${compressiblePct}%`,
            backgroundColor: C_COMPRESSIBLE,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#161616',
            fontSize: '0.875rem',
            fontWeight: 600,
          }}
        >
          {compressiblePct > 15 && `${compressiblePct.toFixed(1)}%`}
        </div>
        <div
          style={{
            width: `${incompressiblePct}%`,
            backgroundColor: C_INCOMPRESSIBLE,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#ffffff',
            fontSize: '0.875rem',
            fontWeight: 600,
          }}
        >
          {incompressiblePct > 15 && `${incompressiblePct.toFixed(1)}%`}
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: '2rem', fontSize: '0.875rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{ width: '12px', height: '12px', backgroundColor: C_COMPRESSIBLE, borderRadius: '2px' }} />
          <span style={{ color: C_TEXT_SEC }}>Compressible:</span>
          <span style={{ color: C_TEXT_PRIMARY, fontWeight: 600 }}>{fmtMB(compressible)}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{ width: '12px', height: '12px', backgroundColor: C_INCOMPRESSIBLE, borderRadius: '2px' }} />
          <span style={{ color: C_TEXT_SEC }}>Incompressible:</span>
          <span style={{ color: C_TEXT_PRIMARY, fontWeight: 600 }}>{fmtMB(incompressible)}</span>
        </div>
      </div>

      <p style={{ fontSize: '0.75rem', color: C_TEXT_SEC, marginTop: '0.75rem', fontStyle: 'italic' }}>
        Incompressible data includes already-compressed files (.zip, .jpg, .mp4) or encrypted files
      </p>
    </div>
  )
}
