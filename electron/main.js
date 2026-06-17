'use strict'

/**
 * Electron main process.
 *
 * Startup sequence:
 *   1. Spawn the PyInstaller-bundled backend binary.
 *      The backend binds a socket, announces the port as JSON on stdout, then
 *      hands the socket to uvicorn — no TOCTOU race possible.
 *   2. Read the port from the first JSON line on the backend's stdout.
 *   3. Poll GET /health until the backend responds (up to 30 s).
 *   4. Open the main BrowserWindow loading http://127.0.0.1:{port}.
 */

const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')
const fs = require('fs')

// ── Path helpers ───────────────────────────────────────────────────────────────

function backendBinPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend', 'comprestimator-backend')
  }
  return path.join(__dirname, '..', 'dist', 'comprestimator-backend')
}

function comprestimatorBinPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'ess_comprestimator')
  }
  return path.join(__dirname, '..', 'ess_comprestimator')
}

// ── Backend process ────────────────────────────────────────────────────────────

let backendProc = null
let backendPort = null

/**
 * Reads stdout from `proc` until it finds a JSON line containing `{ port: N }`.
 * Non-JSON lines are forwarded to process.stdout as [backend] prefixed output.
 * Rejects if the process exits before the announcement, or after 15 s.
 */
function readPortFromStdout(proc) {
  return new Promise((resolve, reject) => {
    let buf = ''
    const timeout = setTimeout(
      () => reject(new Error('Backend did not announce its port within 15 s')),
      15_000
    )

    function onData(chunk) {
      buf += chunk.toString()
      const lines = buf.split('\n')
      // Keep the last (potentially incomplete) line in the buffer.
      buf = lines.pop()

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) continue
        try {
          const parsed = JSON.parse(trimmed)
          if (typeof parsed.port === 'number') {
            clearTimeout(timeout)
            proc.stdout.off('data', onData)
            // Forward all subsequent stdout as log output.
            proc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`))
            resolve(parsed.port)
            return
          }
        } catch {
          // Not JSON — forward as a log line.
          process.stdout.write(`[backend] ${trimmed}\n`)
        }
      }
    }

    proc.stdout.on('data', onData)
    proc.once('exit', (code) => {
      clearTimeout(timeout)
      reject(new Error(`Backend exited (code ${code}) before announcing its port`))
    })
  })
}

async function startBackend() {
  const bin = backendBinPath()
  if (!fs.existsSync(bin)) {
    throw new Error(
      `Backend binary not found at:\n${bin}\n\nRun  build.sh  to create it.`
    )
  }

  const compBin = comprestimatorBinPath()
  const env = {
    ...process.env,
    ...(fs.existsSync(compBin) ? { COMPRESTIMATOR_PATH: compBin } : {}),
  }

  backendProc = spawn(bin, [], { env, stdio: ['ignore', 'pipe', 'ignore'] })
  backendProc.on('exit', (code, signal) => {
    console.log(`[backend] exited  code=${code}  signal=${signal}`)
  })

  // Block until the backend announces the port it bound.
  backendPort = await readPortFromStdout(backendProc)
  console.log(`[main] Backend listening on port ${backendPort}`)
}

function stopBackend() {
  if (backendProc && !backendProc.killed) {
    backendProc.kill('SIGTERM')
    backendProc = null
  }
}

// ── Health poll ────────────────────────────────────────────────────────────────

function waitForBackend(port, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    function attempt() {
      http
        .get(`http://127.0.0.1:${port}/health`, (res) => {
          res.resume()
          if (res.statusCode === 200) return resolve()
          retry()
        })
        .on('error', retry)
    }
    function retry() {
      if (Date.now() >= deadline) {
        reject(new Error(`Backend did not respond to /health within ${timeoutMs / 1000} s`))
        return
      }
      setTimeout(attempt, 300)
    }
    attempt()
  })
}

// ── IPC handlers ──────────────────────────────────────────────────────────────

ipcMain.handle('select-directory', async () => {
  const win = BrowserWindow.getFocusedWindow()
  const result = await dialog.showOpenDialog(win ?? mainWindow, {
    properties: ['openDirectory'],
    title: 'Select directory to analyse',
  })
  return result.canceled ? null : result.filePaths[0]
})

// ── BrowserWindow ──────────────────────────────────────────────────────────────

let mainWindow = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    title: 'Comprestimator',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  mainWindow.loadURL(`http://127.0.0.1:${backendPort}`)

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Only open http/https URLs externally — block file://, custom schemes, etc.
    if (/^https?:\/\//i.test(url)) {
      shell.openExternal(url)
    }
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ── App lifecycle ──────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  try {
    await startBackend()
    await waitForBackend(backendPort)
    createWindow()
  } catch (err) {
    dialog.showErrorBox('Comprestimator — startup failed', String(err))
    app.quit()
  }
})

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})

app.on('before-quit', stopBackend)
