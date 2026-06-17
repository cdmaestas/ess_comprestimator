/**
 * BlockDistChart — stacked horizontal bar showing zero vs non-zero block ratio.
 *
 * Zero blocks are pre-compressed (sparse data, free storage win).
 * Non-zero blocks are the payload that zlib compresses.
 *
 * Uses hard-coded Carbon g100 hex colours because SVG fill can't use CSS vars.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { CompressionResult } from '../../api/types'

// Carbon g100 colours
const C_ZERO    = '#24a148'   // support-success
const C_NONZERO = '#4589ff'   // support-info
const C_GRID    = '#393939'   // layer-02
const C_TEXT    = '#c6c6c6'   // text-secondary

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

interface Props {
  result: CompressionResult
}

export default function BlockDistChart({ result }: Props) {
  const { num_zero_blocks: z, num_non_zero_blocks: nz, total_blocks_read: total } = result

  if (z == null || nz == null || total == null || total === 0) return null

  const zeroPct  = ((z  / total) * 100).toFixed(1)
  const nzPct    = ((nz / total) * 100).toFixed(1)

  // Recharts expects an array of objects for stacked bars
  const data = [{ name: 'Blocks', zero: z, nonzero: nz }]

  return (
    <div>
      <p style={{ fontSize: '0.75rem', color: C_TEXT, marginBottom: '0.75rem' }}>
        Block composition &mdash; {fmt(total)} total blocks read
      </p>

      {/* Stacked horizontal bar */}
      <ResponsiveContainer width="100%" height={72}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
          <CartesianGrid horizontal={false} stroke={C_GRID} />
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" hide />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.04)' }}
            contentStyle={{ background: '#161616', border: '1px solid #393939', borderRadius: 2 }}
            labelStyle={{ color: C_TEXT }}
            formatter={(value: number, name: string) => {
              const pct = ((value / total) * 100).toFixed(1)
              return [`${fmt(value)} (${pct}%)`, name === 'zero' ? 'Zero blocks' : 'Non-zero blocks']
            }}
          />
          <Bar dataKey="zero" stackId="a" fill={C_ZERO} radius={[2, 0, 0, 2]}>
            <LabelList
              valueAccessor={() => `${zeroPct}% zero`}
              position="insideLeft"
              style={{ fill: '#161616', fontSize: '0.6875rem', fontWeight: 600 }}
            />
          </Bar>
          <Bar dataKey="nonzero" stackId="a" fill={C_NONZERO} radius={[0, 2, 2, 0]}>
            <LabelList
              valueAccessor={() => `${nzPct}% data`}
              position="insideRight"
              style={{ fill: '#161616', fontSize: '0.6875rem', fontWeight: 600 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
        {[
          { color: C_ZERO,    label: `Zero blocks — ${fmt(z)} (${zeroPct}%)` },
          { color: C_NONZERO, label: `Non-zero blocks — ${fmt(nz)} (${nzPct}%)` },
        ].map(({ color, label }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: color, flexShrink: 0 }} />
            <span style={{ fontSize: '0.6875rem', color: C_TEXT }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
