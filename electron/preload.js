'use strict'

/**
 * Preload script — runs in the renderer process before the page loads.
 * contextBridge exposes a minimal API surface to the React app without
 * granting full Node.js access to renderer code.
 */

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  /**
   * Opens the native macOS/Windows/Linux directory picker dialog.
   * Returns the selected absolute path, or null if cancelled.
   */
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
})
