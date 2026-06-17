import axios from 'axios'
import type {
  CompressionResult,
  JobRequest,
  JobState,
  JobSummary,
  LogsResponse,
} from './types'

const api = axios.create({ baseURL: '/api' })

export const jobsApi = {
  /** POST /api/jobs — create and enqueue a job */
  create: (req: JobRequest) =>
    api.post<JobSummary>('/jobs', req).then((r) => r.data),

  /** GET /api/jobs — list all jobs, newest first */
  list: () => api.get<JobSummary[]>('/jobs').then((r) => r.data),

  /** GET /api/jobs/{id} — full job state */
  get: (jobId: string) =>
    api.get<JobState>(`/jobs/${jobId}`).then((r) => r.data),

  /** GET /api/jobs/{id}/results — compression result (complete jobs only) */
  results: (jobId: string) =>
    api.get<CompressionResult>(`/jobs/${jobId}/results`).then((r) => r.data),

  /** GET /api/jobs/{id}/logs?since=N — polling fallback */
  logs: (jobId: string, since = 0) =>
    api
      .get<LogsResponse>(`/jobs/${jobId}/logs`, { params: { since } })
      .then((r) => r.data),

  /** DELETE /api/jobs/{id} — cancel a running job */
  cancel: (jobId: string) =>
    api.delete(`/jobs/${jobId}`).then((r) => r.data),
}
