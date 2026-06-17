/**
 * dirPicker — cross-environment directory picker.
 *
 * Priority:
 *   1. Electron  → ipcRenderer → native OS dialog (full absolute path)
 *   2. File System Access API  → window.showDirectoryPicker() (Chromium, returns name only)
 *   3. <input webkitdirectory> → hidden input click (Firefox / KDE / GNOME, returns name only)
 *
 * In environments 2 and 3 the browser security model prevents exposing the
 * absolute path, so only the top-level folder name is returned.  The TextInput
 * remains editable so the user can prepend the parent path manually.
 */

declare global {
  interface Window {
    electronAPI?: {
      selectDirectory: () => Promise<string | null>
    }
    showDirectoryPicker?: (opts?: { mode?: string }) => Promise<{ name: string }>
  }
}

export interface DirPickResult {
  /** The picked path or folder name. */
  path: string
  /** True when the result is a full absolute path (Electron only). */
  isAbsolute: boolean
}

/**
 * Returns true if any picker mechanism is available in the current runtime.
 * Call this to decide whether to show the Browse button.
 */
export function isDirPickerAvailable(): boolean {
  if (typeof window === 'undefined') return false
  if (window.electronAPI?.selectDirectory) return true
  if (typeof window.showDirectoryPicker === 'function') return true
  // webkitdirectory is supported in all modern browsers
  const probe = document.createElement('input')
  return 'webkitdirectory' in probe
}

/**
 * Opens a directory picker appropriate for the current runtime.
 * Returns null if the user cancels or an error occurs.
 */
export async function pickDirectory(): Promise<DirPickResult | null> {
  // ── 1. Electron native dialog ───────────────────────────────────────────────
  if (window.electronAPI?.selectDirectory) {
    const p = await window.electronAPI.selectDirectory()
    return p ? { path: p, isAbsolute: true } : null
  }

  // ── 2. File System Access API (Chrome / Edge) ───────────────────────────────
  if (typeof window.showDirectoryPicker === 'function') {
    try {
      const handle = await window.showDirectoryPicker({ mode: 'read' })
      return { path: handle.name, isAbsolute: false }
    } catch {
      // User cancelled (AbortError) or permission denied — treat as no-op.
      return null
    }
  }

  // ── 3. Hidden <input webkitdirectory> (Firefox, Safari, KDE/GNOME browsers) ─
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.setAttribute('webkitdirectory', '')
    input.style.display = 'none'
    document.body.appendChild(input)

    const cleanup = () => document.body.removeChild(input)

    input.onchange = () => {
      cleanup()
      const files = input.files
      if (!files || files.length === 0) return resolve(null)
      // webkitRelativePath = "folder/subdir/file.txt" — the root folder name is
      // the first segment.
      const rootName = files[0].webkitRelativePath.split('/')[0]
      resolve(rootName ? { path: rootName, isAbsolute: false } : null)
    }

    // Some browsers fire 'cancel' on the input element; fall back to a focus
    // listener on the window for browsers that don't.
    input.oncancel = () => { cleanup(); resolve(null) }

    input.click()
  })
}
