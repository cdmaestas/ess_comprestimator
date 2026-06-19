/** Format a size given in MB to a human-readable string. */
export function fmtMB(mb: number): string {
  if (mb >= 1_024) return `${(mb / 1_024).toFixed(2)} GB`
  if (mb >= 1) return `${mb.toFixed(3)} MB`
  if (mb >= 0.001) return `${(mb * 1_024).toFixed(1)} KB`
  return `${(mb * 1_048_576).toFixed(0)} B`
}

/** Format a wall-clock duration from two ISO timestamp strings. */
export function formatDuration(started: string | null, completed: string | null): string {
  if (!started) return '—'
  const end = completed ? new Date(completed) : new Date()
  const secs = Math.round((end.getTime() - new Date(started).getTime()) / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  return `${mins}m ${secs % 60}s`
}
