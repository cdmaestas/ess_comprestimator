/**
 * HomePage — two-column layout: config form (left) + job list (right).
 *
 * Flow:
 *   1. User fills JobConfigForm and clicks Run.
 *   2. onJobCreated records the new job_id and navigates to /jobs/:jobId.
 *   3. JobList polls GET /api/jobs and highlights the new row.
 */

import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Grid, Column } from '@carbon/react'
import type { JobSummary } from '../api/types'
import JobConfigForm from '../components/JobConfigForm'
import JobList from '../components/JobList'

export default function HomePage() {
  const navigate = useNavigate()
  const [newJobIds, setNewJobIds] = useState<string[]>([])

  const handleJobCreated = (job: JobSummary) => {
    setNewJobIds((prev) => [job.job_id, ...prev])
    navigate(`/jobs/${job.job_id}`)
  }

  const colStyle: React.CSSProperties = {
    height: '100%',
    overflowY: 'auto',
    paddingBottom: '2rem',
  }

  return (
    <Grid style={{ height: '100%' }}>
      {/* ── Config form ─────────────────────────────────────────────── */}
      <Column sm={4} md={4} lg={6} xlg={5} style={colStyle}>
        <h2
          style={{
            fontSize: '1.25rem',
            fontWeight: 400,
            marginBottom: '1.5rem',
            color: 'var(--cds-text-primary)',
          }}
        >
          New estimation job
        </h2>
        <JobConfigForm onJobCreated={handleJobCreated} />
      </Column>

      {/* ── Job list ────────────────────────────────────────────────── */}
      <Column sm={4} md={8} lg={10} xlg={11} style={colStyle}>
        <h2
          style={{
            fontSize: '1.25rem',
            fontWeight: 400,
            marginBottom: '1.5rem',
            color: 'var(--cds-text-primary)',
          }}
        >
          Job history
        </h2>
        <JobList newJobIds={newJobIds} />
      </Column>
    </Grid>
  )
}
