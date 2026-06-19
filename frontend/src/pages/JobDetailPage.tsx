/**
 * JobDetailPage — live progress + results for a single job.
 *
 * Log line strategy:
 *   - Terminal jobs (complete/failed): use jobState.log_lines from the REST fetch.
 *     We skip streaming to avoid replaying lines we already have.
 *   - Active jobs (queued/running): combine jobState.log_lines (historical, from
 *     initial REST fetch) with lines from useJobStream (new lines since connecting).
 *     This correctly handles navigating to a job that's been running for a while.
 *
 * Re-fetch strategy:
 *   - Only re-fetch jobState when streamDone goes false→true (stream just finished).
 *   - Does NOT re-fetch when loading an already-terminal job (avoids spurious call).
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Breadcrumb,
  BreadcrumbItem,
  Button,
  Column,
  Grid,
  InlineLoading,
  InlineNotification,
  Tag,
} from '@carbon/react'
import { ArrowLeft } from '@carbon/icons-react'
import type { JobState } from '../api/types'
import { isTerminal, STATUS_TAG } from '../api/types'
import { jobsApi } from '../api/jobsApi'
import { useJobStream } from '../api/useJobStream'
import { formatDuration } from '../utils/format'
import JobProgress from '../components/JobProgress'
import ResultsPanel from '../components/ResultsPanel'

// ── Duration ticker ──────────────────────────────────────────────────────────

function useDuration(startedAt: string | null, completedAt: string | null): string {
  const [, tick] = useState(0)
  useEffect(() => {
    if (!startedAt || completedAt) return
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [startedAt, completedAt])

  return formatDuration(startedAt, completedAt)
}

// ── Sampling summary ─────────────────────────────────────────────────────────

function samplingLabel(req: JobState['request']): string {
  if (req.exhaustive_sampling) return 'Exhaustive'
  if (req.sampling_percentage != null) return `${req.sampling_percentage}% sample`
  return 'Auto (10%)'
}

// ── Component ────────────────────────────────────────────────────────────────

export default function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()

  const [jobState, setJobState] = useState<JobState | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  // Scroll to top on mount so the breadcrumb is always visible
  useEffect(() => {
    document.querySelector('.cds--content')?.scrollTo(0, 0)
  }, [])

  // Initial REST fetch
  useEffect(() => {
    if (!jobId) return
    jobsApi.get(jobId).then(setJobState).catch(() => setLoadError('Job not found'))
  }, [jobId])

  // ── Streaming ─────────────────────────────────────────────────────────────

  // For already-terminal jobs we skip streaming (we already have all data from REST).
  const isTerminalFromRest = jobState != null && isTerminal(jobState.status)

  const { lines: streamLines, status: streamStatus, done: streamDone } =
    useJobStream(!isTerminalFromRest && jobId ? jobId : null)

  // Re-fetch jobState ONLY when the stream itself transitions to done.
  // Using a ref to track previous streamDone avoids firing on initial mount.
  const prevStreamDone = useRef(false)
  useEffect(() => {
    if (streamDone && !prevStreamDone.current && jobId) {
      jobsApi.get(jobId).then(setJobState).catch(() => {})
    }
    prevStreamDone.current = streamDone
  }, [streamDone, jobId])

  // ── Derived display values ────────────────────────────────────────────────

  const done = isTerminalFromRest || streamDone

  // currentStatus: live stream status for active jobs, stored status for terminal
  const currentStatus =
    (isTerminalFromRest ? jobState?.status : streamStatus ?? jobState?.status) ?? 'queued'

  // allLines: for terminal jobs use stored lines only (no stream replay needed);
  // for active jobs merge stored history + new lines from the stream.
  const allLines = useMemo(() => {
    if (!jobState) return streamLines
    if (isTerminalFromRest) return jobState.log_lines
    return [...jobState.log_lines, ...streamLines]
  }, [jobState, isTerminalFromRest, streamLines])

  // Warnings come from jobState (populated by backend), not the stream
  const warnings = jobState?.warnings ?? []

  // ── Cancel ────────────────────────────────────────────────────────────────

  async function handleCancel() {
    if (!jobId) return
    try {
      await jobsApi.cancel(jobId)
    } catch {
      // ignore — job may have already finished
    }
  }

  // Duration ticker
  const duration = useDuration(jobState?.started_at ?? null, jobState?.completed_at ?? null)

  // ── Render ────────────────────────────────────────────────────────────────

  if (loadError) {
    return (
      <Grid>
        <Column sm={4} md={8} lg={16}>
          <InlineNotification kind="error" title="Not found" subtitle={loadError} lowContrast />
          <Button kind="ghost" renderIcon={ArrowLeft} onClick={() => navigate('/')}>
            Back to home
          </Button>
        </Column>
      </Grid>
    )
  }

  if (!jobState) {
    return (
      <Grid>
        <Column sm={4} md={8} lg={16}>
          <InlineLoading description="Loading job…" status="active" />
        </Column>
      </Grid>
    )
  }

  return (
    <Grid>
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <Column sm={4} md={8} lg={16}>
        <Breadcrumb style={{ marginBottom: '1rem' }}>
          <BreadcrumbItem onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
            Home
          </BreadcrumbItem>
          <BreadcrumbItem isCurrentPage>
            Job {jobId?.slice(0, 8)}…
          </BreadcrumbItem>
        </Breadcrumb>

        <h2 style={{ fontSize: '1.25rem', fontWeight: 400, marginBottom: '0.25rem', color: 'var(--cds-text-primary)' }}>
          {jobState.request.path}
        </h2>
        <p style={{ fontSize: '0.75rem', color: 'var(--cds-text-secondary)', marginBottom: '1rem', fontFamily: 'IBM Plex Mono, monospace' }}>
          {jobId}
        </p>

        {/* ── Metadata chips ────────────────────────────────────────────── */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1.5rem', alignItems: 'center' }}>
          {/* Status */}
          {(() => {
            const { type, label } = STATUS_TAG[currentStatus] ?? { type: 'cool-gray' as const, label: currentStatus }
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return <Tag type={type as any} size="sm">{label}</Tag>
          })()}

          {/* Sampling mode */}
          <Tag type="outline" size="sm">{samplingLabel(jobState.request)}</Tag>

          {/* Optional flags */}
          {jobState.request.skip_hidden && <Tag type="outline" size="sm">Skip hidden</Tag>}
          {(jobState.request.exclude ?? []).length > 0 && (
            <Tag type="outline" size="sm">
              {jobState.request.exclude!.length} exclusion{jobState.request.exclude!.length !== 1 ? 's' : ''}
            </Tag>
          )}

          {/* Duration */}
          <span style={{ fontSize: '0.75rem', color: 'var(--cds-text-secondary)', marginLeft: 'auto' }}>
            {jobState.started_at
              ? `Started ${new Date(jobState.started_at).toLocaleTimeString()} · ${duration}`
              : `Created ${new Date(jobState.created_at).toLocaleTimeString()}`}
          </span>
        </div>
      </Column>

      {/* ── Live progress ─────────────────────────────────────────────────── */}
      <Column sm={4} md={8} lg={done && jobState.result ? 8 : 16}>
        <JobProgress
          jobId={jobId!}
          status={currentStatus}
          lines={allLines}
          warnings={warnings}
          onCancel={
            currentStatus === 'running' || currentStatus === 'queued'
              ? handleCancel
              : undefined
          }
        />
      </Column>

      {/* ── Results panel (complete jobs only) ──────────────────────────── */}
      {done && jobState.result && (
        <Column sm={4} md={8} lg={8}>
          <h3 style={{ fontSize: '1rem', fontWeight: 400, marginBottom: '1rem', color: 'var(--cds-text-primary)' }}>
            Results
          </h3>
          <ResultsPanel result={jobState.result} jobId={jobId!} />
        </Column>
      )}

      {/* ── Failed banner ─────────────────────────────────────────────────── */}
      {done && currentStatus === 'failed' && jobState.error && (
        <Column sm={4} md={8} lg={16}>
          <InlineNotification
            kind="error"
            title="Job failed"
            subtitle={jobState.error}
            lowContrast
          />
        </Column>
      )}
    </Grid>
  )
}
