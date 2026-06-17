/**
 * JobList — Carbon DataTable showing all jobs, polling every 3 s.
 *
 * Columns: status badge | path | started | duration | ratio | actions
 * Clicking a row navigates to /jobs/:jobId (JobDetailPage).
 */

import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  DataTable,
  DataTableSkeleton,
  InlineNotification,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  TableToolbar,
  TableToolbarContent,
  TableToolbarSearch,
  Tag,
  Button,
} from '@carbon/react'
import { View, TrashCan } from '@carbon/icons-react'
import type { JobStatus, JobSummary } from '../../api/types'
import { jobsApi } from '../../api/jobsApi'

// ── Helpers ───────────────────────────────────────────────────────────────────

// Carbon v11 Tag 'type' values relevant here
type CarbonTagType = 'cool-gray' | 'blue' | 'green' | 'red'

function statusTag(status: JobStatus) {
  const map: Record<JobStatus, { type: CarbonTagType; label: string }> = {
    queued:   { type: 'cool-gray', label: 'Queued' },
    running:  { type: 'blue',      label: 'Running' },
    complete: { type: 'green',     label: 'Complete' },
    failed:   { type: 'red',       label: 'Failed' },
  }
  const { type, label } = map[status] ?? { type: 'cool-gray' as CarbonTagType, label: status }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return <Tag type={type as any} size="sm">{label}</Tag>
}

function formatDuration(started: string | null, completed: string | null): string {
  if (!started) return '—'
  const end = completed ? new Date(completed) : new Date()
  const secs = Math.round((end.getTime() - new Date(started).getTime()) / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  return `${mins}m ${secs % 60}s`
}

function formatRatio(ratio: number | null): string {
  return ratio != null ? `${ratio.toFixed(2)}×` : '—'
}

function truncatePath(path: string, maxLen = 48): string {
  if (path.length <= maxLen) return path
  return '…' + path.slice(-(maxLen - 1))
}

const HEADERS = [
  { key: 'status',   header: 'Status' },
  { key: 'path',     header: 'Path' },
  { key: 'started',  header: 'Started' },
  { key: 'duration', header: 'Duration' },
  { key: 'ratio',    header: 'Est. ratio' },
  { key: 'actions',  header: '' },
]

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  /** job_ids that were just created — used to highlight new rows */
  newJobIds?: string[]
}

export default function JobList({ newJobIds = [] }: Props) {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchJobs = useCallback(async () => {
    try {
      const data = await jobsApi.list()
      setJobs(data)
      setError(null)
    } catch {
      setError('Could not load jobs — is the backend running?')
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load + polling every 3 s
  useEffect(() => {
    fetchJobs()
    const id = setInterval(fetchJobs, 3000)
    return () => clearInterval(id)
  }, [fetchJobs])

  // ── Render helpers ────────────────────────────────────────────────────────

  if (loading) {
    return <DataTableSkeleton columnCount={6} rowCount={4} headers={HEADERS} />
  }

  if (error) {
    return (
      <InlineNotification kind="error" title="Load error" subtitle={error} lowContrast />
    )
  }

  if (jobs.length === 0) {
    return (
      <div
        style={{
          padding: '3rem',
          textAlign: 'center',
          border: '1px dashed var(--cds-border-subtle-01)',
          borderRadius: 4,
          color: 'var(--cds-text-secondary)',
        }}
      >
        <p style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>No jobs yet</p>
        <p style={{ fontSize: '0.875rem' }}>
          Configure a path and click <strong>Run Comprestimator</strong> to start.
        </p>
      </div>
    )
  }

  // Build DataTable rows
  const rows = jobs.map((job) => ({
    id: job.job_id,
    status:   statusTag(job.status),
    path:     truncatePath(job.path),
    started:  job.started_at
      ? new Date(job.started_at).toLocaleTimeString()
      : '—',
    duration: formatDuration(job.started_at, job.completed_at),
    ratio:    formatRatio(job.compression_ratio),
    actions:  job.job_id,   // raw id; rendered specially below
  }))

  return (
    <DataTable rows={rows} headers={HEADERS} isSortable>
      {({ rows: tableRows, headers, getHeaderProps, getRowProps, getTableProps, onInputChange }) => (
        <TableContainer title="Jobs" description="All compression estimation jobs">
          <TableToolbar>
            <TableToolbarContent>
              <TableToolbarSearch
                // Carbon's onChange can fire with a SyntheticEvent or a string;
                // cast to any so the DataTable's onInputChange handler is satisfied.
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                onChange={onInputChange as any}
                placeholder="Filter by path…"
                persistent
              />
            </TableToolbarContent>
          </TableToolbar>

          <Table {...getTableProps()} size="lg" useZebraStyles>
            <TableHead>
              <TableRow>
                {headers.map((header) => (
                  // getHeaderProps already spreads `key` — don't add it again
                  <TableHeader {...getHeaderProps({ header })}>
                    {header.header}
                  </TableHeader>
                ))}
              </TableRow>
            </TableHead>

            <TableBody>
              {tableRows.map((row) => {
                const isNew = newJobIds.includes(row.id)
                return (
                  // getRowProps already spreads `key` — don't add it again
                  <TableRow
                    {...getRowProps({ row })}
                    style={
                      isNew
                        ? { background: 'var(--cds-layer-selected-01)' }
                        : undefined
                    }
                  >
                    {row.cells.map((cell) => {
                      if (cell.info.header === 'actions') {
                        return (
                          <TableCell key={cell.id} style={{ display: 'flex', gap: '0.25rem' }}>
                            <Button
                              kind="ghost"
                              size="sm"
                              renderIcon={View}
                              iconDescription="View job"
                              hasIconOnly
                              tooltipPosition="left"
                              onClick={() => navigate(`/jobs/${row.id}`)}
                            />
                          </TableCell>
                        )
                      }
                      return (
                        <TableCell key={cell.id}>
                          {cell.value}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </DataTable>
  )
}
