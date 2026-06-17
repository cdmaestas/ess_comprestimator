/**
 * JobProgress — live log stream panel for a running job.
 *
 * Phase 3: component exists and renders correctly.
 * Phase 4: the useJobStream hook is fully wired in and the cancel button works.
 */

import { useEffect, useRef } from 'react'
import {
  Button,
  InlineLoading,
  InlineNotification,
  Tag,
} from '@carbon/react'
import { StopFilled } from '@carbon/icons-react'
import type { JobStatus } from '../../api/types'

interface Props {
  jobId: string
  status: JobStatus
  lines: string[]
  warnings?: string[]
  onCancel?: () => void
}

export default function JobProgress({
  jobId,
  status,
  lines,
  warnings = [],
  onCancel,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to the bottom as new lines arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  const isRunning = status === 'running' || status === 'queued'

  return (
    <div>
      {/* ── Header row ─────────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          marginBottom: '0.75rem',
        }}
      >
        <span style={{ fontSize: '0.875rem', color: 'var(--cds-text-secondary)' }}>
          Job&nbsp;
          <code style={{ fontSize: '0.75rem' }}>{jobId.slice(0, 8)}…</code>
        </span>

        {isRunning ? (
          <InlineLoading description={status === 'queued' ? 'Queued…' : 'Running…'} status="active" />
        ) : (
          <Tag
            type={status === 'complete' ? 'green' : 'red'}
            size="sm"
          >
            {status === 'complete' ? 'Complete' : 'Failed'}
          </Tag>
        )}

        {isRunning && onCancel && (
          <Button
            kind="danger--ghost"
            size="sm"
            renderIcon={StopFilled}
            iconDescription="Cancel job"
            onClick={onCancel}
            style={{ marginLeft: 'auto' }}
          >
            Cancel
          </Button>
        )}
      </div>

      {/* ── Warnings ───────────────────────────────────────────────── */}
      {warnings.map((w) => (
        <InlineNotification
          key={w}
          kind="warning"
          title="Accuracy notice"
          subtitle={w.replace(/^Note:\s*/i, '')}
          lowContrast
          style={{ marginBottom: '0.5rem' }}
        />
      ))}

      {/* ── Log panel ──────────────────────────────────────────────── */}
      <div className="log-panel" role="log" aria-live="polite" aria-label="Job output">
        {lines.length === 0 ? (
          <span style={{ color: 'var(--cds-text-placeholder)' }}>
            Waiting for output…
          </span>
        ) : (
          (() => {
            // Group lines: replace consecutive progress lines with only the last one
            const displayLines: string[] = []
            for (let i = 0; i < lines.length; i++) {
              const line = lines[i]
              const isProgress = line.includes('Ratio:') || line.includes('Progress')
              
              if (isProgress) {
                // Look ahead to see if there are more progress lines
                let j = i + 1
                while (j < lines.length && (lines[j].includes('Ratio:') || lines[j].includes('Progress'))) {
                  j++
                }
                // Only show the last progress line in this sequence
                displayLines.push(lines[j - 1])
                i = j - 1 // Skip to the last progress line
              } else {
                displayLines.push(line)
              }
            }
            
            return displayLines.map((line, i) => (
              <div key={i}>{line}</div>
            ))
          })()
        )}
        <div ref={bottomRef} className="log-panel__bottom" />
      </div>
    </div>
  )
}
