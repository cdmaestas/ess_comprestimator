/**
 * RatioTile — headline compression ratio with colour-coded interpretation.
 *
 * Ratio bands (Carbon g100 layer colours):
 *   ≥ 4.0×  excellent  — green tint
 *   ≥ 2.0×  good       — teal tint
 *   ≥ 1.3×  moderate   — yellow tint
 *   < 1.3×  low        — default layer
 */

import type { CompressionResult } from '../../api/types'

// Carbon g100 semantic colours (can't use CSS vars in inline style backgrounds)
const BAND_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  excellent: { bg: '#0d3a1a', text: '#42be65', label: 'Excellent' },
  good:      { bg: '#012749', text: '#4589ff', label: 'Good' },
  moderate:  { bg: '#302408', text: '#f1c21b', label: 'Moderate' },
  low:       { bg: '#262626', text: '#c6c6c6', label: 'Low benefit' },
}

function band(ratio: number) {
  if (ratio >= 4.0) return BAND_COLORS.excellent
  if (ratio >= 2.0) return BAND_COLORS.good
  if (ratio >= 1.3) return BAND_COLORS.moderate
  return BAND_COLORS.low
}

interface Props {
  result: CompressionResult
}

export default function RatioTile({ result }: Props) {
  const { compression_ratio: ratio, interpretation, conf_comp } = result
  const b = band(ratio)

  return (
    <div
      style={{
        background: b.bg,
        borderRadius: 4,
        padding: '1.5rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
      }}
    >
      {/* Band label */}
      <p style={{ fontSize: '0.6875rem', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: b.text, margin: 0 }}>
        {b.label} compression candidate
      </p>

      {/* Big number */}
      <p style={{ fontSize: '4rem', fontWeight: 200, lineHeight: 1, color: '#f4f4f4', margin: 0 }}>
        {ratio.toFixed(2)}
        <span style={{ fontSize: '1.5rem', fontWeight: 300, color: '#c6c6c6', marginLeft: '0.25rem' }}>×</span>
      </p>

      {/* Interpretation */}
      <p style={{ fontSize: '0.875rem', color: '#c6c6c6', margin: 0 }}>
        {interpretation.replace(/^\d+\.\d+x\s*[—–-]\s*/i, '')}
      </p>

      {/* Confidence annotation */}
      {conf_comp != null && (
        <p style={{ fontSize: '0.75rem', color: '#8d8d8d', margin: 0 }}>
          Confidence: ≥{((1 - conf_comp) * 100).toFixed(1)}%
        </p>
      )}
    </div>
  )
}
