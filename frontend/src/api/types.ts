// ---------------------------------------------------------------------------
// Mirror of the backend Pydantic models (keep in sync with backend/models/).
// ---------------------------------------------------------------------------

export type JobStatus = 'queued' | 'running' | 'complete' | 'failed'

export interface JobRequest {
  path: string
  exhaustive_sampling?: boolean
  sampling_percentage?: number | null
  exclude?: string[]
  skip_hidden?: boolean
}

export interface JobSummary {
  job_id: string
  status: JobStatus
  path: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  compression_ratio: number | null
}

export interface JobState extends JobSummary {
  request: JobRequest
  log_lines: string[]
  warnings: string[]
  error: string | null
  pid: number | null
  result: CompressionResult | null
}

export interface CompressionResult {
  initial_size: number
  compressed_size: number
  compression_ratio: number
  num_zero_blocks: number | null
  num_non_zero_blocks: number | null
  total_blocks_read: number | null
  ratio_from_binary: number | null
  conf_comp: number | null
  dev_size_mb: number | null
  after_zero_size: number | null
  after_zero_perc: number | null
  conf_zeros: number | null
  after_rtc_size: number | null
  after_rtc_perc: number | null
  error: number | null
  tot_time: number | null
  skipped_bytes_mb: number | null
  interpretation: string
}

// WebSocket message shapes
export type WsMessage =
  | { type: 'log'; line: string }
  | { type: 'status'; status: JobStatus }
  | { type: 'ping' }

export interface LogsResponse {
  job_id: string
  status: JobStatus
  lines: string[]
  next_since: number
  done: boolean
  warnings: string[]
}
