/**
 * useJobStream — React hook that streams live log lines for a running job.
 *
 * Strategy (in priority order):
 *   1. WebSocket  WS /api/jobs/{id}/stream  (real-time, preferred)
 *   2. Polling    GET /api/jobs/{id}/logs   (fallback if WS fails or is blocked)
 *
 * Returns:
 *   lines    — log lines received since the hook connected (NOT historical lines)
 *   status   — current job status as reported by the stream
 *   done     — true once the job reached a terminal state via the stream
 *
 * NOTE: `lines` contains only lines received after this hook instance connected.
 * Historical lines (from before navigation to this page) live in JobState.log_lines
 * and must be combined by the caller:
 *   const allLines = [...jobState.log_lines, ...lines]
 *
 * Pass jobId=null to disable streaming (e.g. for already-terminal jobs).
 */

import { useEffect, useRef, useState } from 'react'
import type { JobStatus, WsMessage } from './types'
import { jobsApi } from './jobsApi'

const WS_BASE =
  window.location.protocol === 'https:'
    ? `wss://${window.location.host}`
    : `ws://${window.location.host}`

const POLL_INTERVAL_MS = 1500
const WS_TIMEOUT_MS = 4000

interface StreamState {
  lines: string[]
  status: JobStatus | null
  done: boolean
  error: string | null
}

export function useJobStream(jobId: string | null): StreamState {
  const [state, setState] = useState<StreamState>({
    lines: [],
    status: null,
    done: false,
    error: null,
  })

  const wsRef = useRef<WebSocket | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const sinceRef = useRef(0)

  useEffect(() => {
    if (!jobId) return

    let cancelled = false

    // ── Helpers ────────────────────────────────────────────────────────────

    const appendLine = (line: string) => {
      setState((prev) => ({ ...prev, lines: [...prev.lines, line] }))
      sinceRef.current += 1
    }

    const setStatus = (status: JobStatus) => {
      const terminal = status === 'complete' || status === 'failed'
      setState((prev) => ({ ...prev, status, done: terminal }))
    }

    const setError = (msg: string) => {
      setState((prev) => ({ ...prev, error: msg, done: true }))
    }

    const stopPoll = () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }

    // ── Polling fallback ────────────────────────────────────────────────────

    const startPolling = () => {
      if (pollRef.current !== null) return
      pollRef.current = setInterval(async () => {
        if (cancelled) { stopPoll(); return }
        try {
          const resp = await jobsApi.logs(jobId, sinceRef.current)
          for (const line of resp.lines) appendLine(line)
          setStatus(resp.status)
          if (resp.done) stopPoll()
        } catch (err: unknown) {
          // Stop retrying on 404 — job doesn't exist
          const status = (err as { response?: { status?: number } })?.response?.status
          if (status === 404) {
            stopPoll()
            setError('Job not found')
          }
          // Ignore other transient errors — keep polling
        }
      }, POLL_INTERVAL_MS)
    }

    // ── WebSocket primary transport ─────────────────────────────────────────

    const ws = new WebSocket(`${WS_BASE}/api/jobs/${jobId}/stream`)
    wsRef.current = ws

    // Fall back to polling if WS doesn't open within WS_TIMEOUT_MS
    const wsTimeout = setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        ws.close()
        if (!cancelled) startPolling()
      }
    }, WS_TIMEOUT_MS)

    ws.onopen = () => clearTimeout(wsTimeout)

    ws.onmessage = (event: MessageEvent<string>) => {
      if (cancelled) return
      try {
        const msg = JSON.parse(event.data) as WsMessage
        if (msg.type === 'log') {
          appendLine(msg.line)
        } else if (msg.type === 'status') {
          setStatus(msg.status)
        }
        // 'ping' intentionally ignored
      } catch {
        // ignore malformed frames
      }
    }

    ws.onerror = () => {
      clearTimeout(wsTimeout)
      if (!cancelled) startPolling()
    }

    ws.onclose = (ev) => {
      clearTimeout(wsTimeout)
      // Code 4004 = job not found — surface as error, don't poll
      if (ev.code === 4004) {
        if (!cancelled) setError('Job not found')
        return
      }
      // Unexpected close before terminal status — fall back to polling
      setState((prev) => {
        if (!prev.done && !cancelled) startPolling()
        return prev
      })
    }

    return () => {
      cancelled = true
      clearTimeout(wsTimeout)
      stopPoll()
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
      wsRef.current = null
    }
  }, [jobId])

  return state
}
