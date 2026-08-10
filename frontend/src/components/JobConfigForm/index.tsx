/**
 * JobConfigForm — maps ess_comprestimator v2 CLI flags to Carbon inputs.
 *
 * CLI flag → Carbon component
 * ─────────────────────────────────────────────────────────────────────────
 * --path                 TextInput (required)
 * --exhaustive-sample  } RadioButtonGroup — "auto" | "exhaustive" | "percentage"
 * --sampling-percentage}   + conditional Slider (1 – 100)
 * --exclude              Tag-pill input (TextInput + dismissible Tag)
 * --exclude-hidden       Toggle
 */

import { useState, type KeyboardEvent } from 'react'
import {
  Button,
  Form,
  FormGroup,
  InlineNotification,
  RadioButton,
  RadioButtonGroup,
  Slider,
  Tag,
  TextInput,
  Toggle,
  Stack,
  InlineLoading,
} from '@carbon/react'
import { FolderOpen, Play } from '@carbon/icons-react'
import type { JobRequest, JobSummary } from '../../api/types'
import { jobsApi } from '../../api/jobsApi'
import { isDirPickerAvailable, pickDirectory } from '../../api/dirPicker'

// ── Types ─────────────────────────────────────────────────────────────────────

type SamplingMode = 'auto' | 'exhaustive' | 'percentage'

interface FormState {
  path: string
  samplingMode: SamplingMode
  samplingPercentage: number
  excludeInput: string
  excludePatterns: string[]
  skipHidden: boolean
}

interface Props {
  /** Called after a job is successfully created so the parent can navigate/refresh */
  onJobCreated: (job: JobSummary) => void
}

const DEFAULT: FormState = {
  path: '',
  samplingMode: 'auto',
  samplingPercentage: 10,
  excludeInput: '',
  excludePatterns: [],
  skipHidden: false,
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function JobConfigForm({ onJobCreated }: Props) {
  const [form, setForm] = useState<FormState>(DEFAULT)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [browsing, setBrowsing] = useState(false)

  const pickerAvailable = isDirPickerAvailable()

  const handleBrowse = async () => {
    setBrowsing(true)
    try {
      const result = await pickDirectory()
      if (result) set('path', result.path)
    } finally {
      setBrowsing(false)
    }
  }

  // ── Field helpers ─────────────────────────────────────────────────────────

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const addExclude = () => {
    const val = form.excludeInput.trim()
    if (val && !form.excludePatterns.includes(val)) {
      set('excludePatterns', [...form.excludePatterns, val])
    }
    set('excludeInput', '')
  }

  const removeExclude = (pattern: string) =>
    set(
      'excludePatterns',
      form.excludePatterns.filter((p) => p !== pattern),
    )

  const handleExcludeKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addExclude()
    } else if (e.key === 'Backspace' && !form.excludeInput && form.excludePatterns.length) {
      removeExclude(form.excludePatterns[form.excludePatterns.length - 1])
    }
  }

  // ── Submit ────────────────────────────────────────────────────────────────

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!form.path.trim()) {
      setError('Path is required')
      return
    }

    const req: JobRequest = {
      path: form.path.trim(),
      exhaustive_sampling: form.samplingMode === 'exhaustive',
      sampling_percentage:
        form.samplingMode === 'percentage' ? form.samplingPercentage : null,
      exclude: form.excludePatterns,
      skip_hidden: form.skipHidden,
    }

    setSubmitting(true)
    try {
      const job = await jobsApi.create(req)
      onJobCreated(job)
      setForm(DEFAULT)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? 'Failed to create job. Check the server is running.'
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Form onSubmit={handleSubmit} aria-label="Comprestimator job configuration">
      <Stack gap={6}>

        {/* ── Error banner ──────────────────────────────────────────── */}
        {error && (
          <InlineNotification
            kind="error"
            title="Error"
            subtitle={error}
            lowContrast
            onClose={() => setError(null)}
          />
        )}

        {/* ── Path ──────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <TextInput
              id="path"
              labelText="Target path"
              helperText={
                pickerAvailable
                  ? 'Type a path or click Browse to pick a directory'
                  : 'Absolute path to the file or directory to analyse'
              }
              placeholder="/gpfs/myvolume/dataset"
              value={form.path}
              onChange={(e) => set('path', e.target.value)}
              invalid={!!error && !form.path.trim()}
              invalidText="Path is required"
              disabled={submitting || browsing}
            />
          </div>
          {pickerAvailable && (
            <Button
              kind="tertiary"
              size="md"
              renderIcon={FolderOpen}
              iconDescription="Browse for directory"
              hasIconOnly
              onClick={handleBrowse}
              disabled={submitting || browsing}
              style={{ flexShrink: 0, marginBottom: '1.5rem' }}
            />
          )}
        </div>

        {/* ── Sampling mode ─────────────────────────────────────────── */}
        <FormGroup legendText="Sampling mode">
          <RadioButtonGroup
            name="sampling-mode"
            valueSelected={form.samplingMode}
            onChange={(value) => set('samplingMode', value as SamplingMode)}
            orientation="vertical"
          >
            <RadioButton
              id="sampling-auto"
              labelText="Auto (10% sample)"
              value="auto"
              disabled={submitting}
            />
            <RadioButton
              id="sampling-exhaustive"
              labelText="Exhaustive — scan entire directory (most accurate, slowest)"
              value="exhaustive"
              disabled={submitting}
            />
            <RadioButton
              id="sampling-percentage"
              labelText="Custom percentage"
              value="percentage"
              disabled={submitting}
            />
          </RadioButtonGroup>

          {/* Slider only visible when percentage mode selected */}
          {form.samplingMode === 'percentage' && (
            <div style={{ marginTop: '1rem', paddingLeft: '1.5rem' }}>
              <Slider
                id="sampling-percentage-slider"
                labelText={`Sample size: ${form.samplingPercentage}% of directory`}
                min={1}
                max={100}
                step={1}
                value={form.samplingPercentage}
                onChange={({ value }) => set('samplingPercentage', value)}
                disabled={submitting}
              />
            </div>
          )}
        </FormGroup>

        {/* ── Exclude patterns ──────────────────────────────────────── */}
        <FormGroup legendText="Exclude patterns (optional)">
          <p
            className="cds--label-description"
            style={{ marginBottom: '0.5rem', fontSize: '0.75rem', color: 'var(--cds-text-secondary)' }}
          >
            Glob patterns or filenames to skip. Press Enter or comma to add.
          </p>

          <div className="tag-input" role="group" aria-label="Exclude patterns">
            {form.excludePatterns.map((pattern) => (
              <Tag
                key={pattern}
                type="cool-gray"
                filter
                onClose={() => removeExclude(pattern)}
                title={`Remove ${pattern}`}
              >
                {pattern}
              </Tag>
            ))}
            <input
              aria-label="Add exclude pattern"
              placeholder={form.excludePatterns.length ? '' : '.git, node_modules, *.log'}
              value={form.excludeInput}
              onChange={(e) => set('excludeInput', e.target.value)}
              onKeyDown={handleExcludeKey}
              onBlur={addExclude}
              disabled={submitting}
            />
          </div>
        </FormGroup>

        {/* ── Toggles ───────────────────────────────────────────────── */}
        <Toggle
          id="skip-hidden"
          labelText="Skip hidden files"
          labelA="Off"
          labelB="On"
          toggled={form.skipHidden}
          onToggle={(checked) => set('skipHidden', checked)}
          disabled={submitting}
        />

        {/* ── Submit ────────────────────────────────────────────────── */}
        {submitting ? (
          <InlineLoading description="Creating job…" status="active" />
        ) : (
          <Button
            type="submit"
            renderIcon={Play}
            iconDescription="Run"
            disabled={submitting}
          >
            Run Comprestimator
          </Button>
        )}
      </Stack>
    </Form>
  )
}
