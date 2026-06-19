/**
 * SizeComparisonChart — grouped bar chart comparing pre vs post compression sizes.
 *
 * Renders only when both initial_size and compressed_size are non-zero.
 * If the after_zero_* and after_rtc_* fields are populated (from the real binary)
 * it shows the full three-stage breakdown; otherwise just pre/post.
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
import { fmtMB } from '../../utils/format'

// Carbon g100
const C_PRE    = '#6f6f6f'   // text-placeholder
const C_MID    = '#4589ff'   // support-info  (after zero removal)
const C_POST   = '#24a148'   // support-success (final compressed)
const C_GRID   = '#393939'
const C_TEXT   = '#c6c6c6'

interface Props {
  result: CompressionResult
}

export default function SizeComparisonChart({ result }: Props) {
  const {
    initial_size,
    compressed_size,
    after_zero_size,
    after_rtc_size,
  } = result

  if (!initial_size || !compressed_size) return null

  const hasStages = after_zero_size != null && after_rtc_size != null

  // Build dataset
  const data = hasStages
    ? [
        { label: 'Original',       size: initial_size,      fill: C_PRE  },
        { label: 'After zero rem.', size: after_zero_size!,  fill: C_MID  },
        { label: 'Compressed',      size: after_rtc_size!,   fill: C_POST },
      ]
    : [
        { label: 'Pre-compression',  size: initial_size,     fill: C_PRE  },
        { label: 'Post-compression', size: compressed_size,  fill: C_POST },
      ]

  const reduction = ((1 - compressed_size / initial_size) * 100).toFixed(1)

  return (
    <div>
      <p style={{ fontSize: '0.75rem', color: C_TEXT, marginBottom: '0.75rem' }}>
        Size reduction &mdash; <strong style={{ color: '#f4f4f4' }}>{reduction}%</strong> smaller after compression
      </p>

      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={C_GRID} />
          <XAxis
            dataKey="label"
            tick={{ fill: C_TEXT, fontSize: 11 }}
            axisLine={{ stroke: C_GRID }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={fmtMB}
            tick={{ fill: C_TEXT, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={72}
          />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.04)' }}
            contentStyle={{ background: '#161616', border: '1px solid #393939', borderRadius: 2 }}
            labelStyle={{ color: C_TEXT }}
            formatter={(value: number) => [`${fmtMB(value)}`, 'Size']}
          />
          <Bar dataKey="size" radius={[2, 2, 0, 0]} maxBarSize={80}>
            {data.map((entry) => (
              <Cell key={entry.label} fill={entry.fill} />
            ))}
            <LabelList
              dataKey="size"
              position="top"
              formatter={fmtMB}
              style={{ fill: C_TEXT, fontSize: '0.6875rem' }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
