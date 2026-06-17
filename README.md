# ESS Comprestimator

Estimates the FCM compression ratio that IBM ESS / GPFS would achieve on a given file or directory.

Originally authored by _Avishay Traeger_, _Danny Harnik_, _Dmitry Sotnikov_.
Modified for ESS by _Sarvesh Chezhian_.

---

## Contents

- [Installation](#installation)
- [Using the app](#using-the-app)
- [Understanding the results](#understanding-the-results)
- [Building from source](#building-from-source)
- [Command-line interface](#command-line-interface)
- [Development](#development)
- [Clean build](#clean-build)

---

## Installation

### macOS

1. Open the `.dmg` file and drag **Comprestimator** into your Applications folder.
2. On first launch, macOS may show *"Apple cannot verify this app"*. Open **System Settings → Privacy & Security**, scroll to the blocked app entry, and click **Open Anyway**.

### Linux

Choose the format that matches your distro.

#### AppImage (any distro — recommended)

AppImage bundles everything and needs no install. It does require FUSE to mount itself, which is missing by default on Ubuntu 22.04+ and some other distros.

```bash
# Ubuntu 22.04+ / Debian 12+ — install FUSE once
sudo apt install libfuse2

# Make executable and run
chmod +x Comprestimator-1.0.0.AppImage
./Comprestimator-1.0.0.AppImage
```

> On Fedora / RHEL: `sudo dnf install fuse` if the AppImage fails to start.

#### .deb (Ubuntu, Debian, Pop!\_OS, Linux Mint …)

```bash
sudo apt install ./comprestimator_1.0.0_amd64.deb
```

After install, launch **Comprestimator** from your application menu, or run `comprestimator` in a terminal.

#### .rpm (RHEL, Fedora, CentOS, Rocky Linux …)

```bash
sudo dnf install ./comprestimator-1.0.0.x86_64.rpm
```

After install, launch **Comprestimator** from your application menu, or run `comprestimator` in a terminal.

---

## Using the app

1. **Enter a path** — type or paste the full path to the directory you want to analyse.
2. **Choose a sampling mode:**
   - *Auto (default)* — samples 10% of the data; switches to exhaustive for directories under 1 MB.
   - *Exhaustive* — reads every file; most accurate but slowest.
   - *Percentage* — enter a custom sample percentage (e.g. `25`).
3. **Optional filters:**
   - *Skip hidden files* — ignore dotfiles and hidden directories.
   - *Exclude patterns* — comma-separated filenames or globs (e.g. `*.log`, `node_modules`).
4. Click **Run** and watch the live log output.
5. When the job completes, the **Results** panel shows:
   - Estimated compression ratio and interpretation (Excellent / Good / Moderate / Low)
   - Size reduction percentage and before/after chart
   - Sample size, run time
   - **Download CSV** to export the raw numbers.

> Jobs are queued — you can submit multiple runs and they execute one at a time. Previous jobs remain visible in the list on the home screen.

---

## Understanding the results

- **Estimated Compression Ratio** — e.g. `3.5x` means data compresses to ~28% of its original size.
- **FCM4 drive cap** — FCM4 drives are physically limited to 4x compression. If the estimate exceeds 4x, use 4x when provisioning vdisksets.
- **Sampling accuracy** — the default 10% sample gives good accuracy for most workloads, especially for directories with uniform file types or directories larger than 1 GB. For very large directories (100 TB+) even 1% sampling provides reliable results.

---

## Building from source

The packaged desktop app bundles the backend, frontend, and Go binary into a double-clickable installer.

### Prerequisites

| Tool | macOS | Linux |
|------|-------|-------|
| Go 1.21+ | `brew install go` | `sudo apt install golang-go` |
| Python 3.9+ | `brew install python` | `sudo apt install python3 python3-venv` |
| Node 18+ | `brew install node` | `sudo apt install nodejs npm` |

Install frontend and Electron dependencies:
```bash
(cd frontend && npm install)
(cd electron && npm install)
```

> **Python dependencies** are installed automatically into a `.venv/` virtual environment during `./build.sh` — you do not need to run `pip install` manually.

### Build the installer

```bash
./build.sh
```

Output (platform-dependent):

| Platform | Output |
|----------|--------|
| macOS (Apple Silicon) | `dist-electron/Comprestimator-1.0.0-arm64.dmg` |
| macOS (Intel) | `dist-electron/Comprestimator-1.0.0.dmg` |
| Linux | `dist-electron/Comprestimator-1.0.0.AppImage` |
| Linux | `dist-electron/comprestimator_1.0.0_amd64.deb` |
| Linux | `dist-electron/comprestimator-1.0.0.x86_64.rpm` |

> **Note:** The build always produces both macOS architectures, but each `.dmg` only contains binaries compiled on the host machine. Build on Apple Silicon for the `-arm64.dmg`; build on Intel for the x64 `.dmg`. To target only your architecture, set `"arch": ["arm64"]` (or `["x64"]`) in `electron/package.json`.

You can skip steps that are already up to date:

```bash
./build.sh --skip-frontend      # reuse existing frontend/dist/
./build.sh --skip-pyinstaller   # reuse existing dist/comprestimator-backend
```

---

## Command-line interface

### Requirements

- Go 1.21+ (to build) or a pre-compiled `ess_comprestimator` binary

### Build the binary

```bash
make
```

Works on Linux (x86_64) and macOS (arm64, x86_64).

### Run

```bash
./ess_comprestimator --path <file or directory>
```

#### Sampling options

| Flag | Description |
|------|-------------|
| *(default)* | 10% sample |
| `--exhaustive-sample` | Scan entire directory — most accurate, slowest |
| `--sampling-percentage 25` | Sample a specific percentage (integer, no `%`) |

#### Filter options

| Flag | Description |
|------|-------------|
| `--exclude-hidden` | Skip hidden files and directories (names starting with `.`) |
| `--exclude PATTERN` | Exclude filenames or glob patterns (repeatable) |

#### Performance options

| Flag | Description |
|------|-------------|
| `--threads N` | Number of parallel compression workers (default: logical CPU count) |
| `--error-log FILE` | Write unreadable file paths to a log (default: `comprestimator_errors.log`) |

#### Examples

```bash
# Estimate compression for a directory using 25% sampling
./ess_comprestimator --path /data/myvolume --sampling-percentage 25

# Exhaustive scan, skipping hidden files and node_modules
./ess_comprestimator --path /data/myvolume --exhaustive-sample \
    --exclude-hidden --exclude node_modules --exclude "*.log"

# Use 8 threads for a large parallel scan
./ess_comprestimator --path /data/myvolume --threads 8
```

---

## Development

Run the FastAPI backend and Vite frontend side-by-side without packaging:

```bash
./dev.sh
```

| Service | URL |
|---------|-----|
| Frontend (Vite) | http://localhost:5173 |
| Backend API docs | http://localhost:8000/api/docs |

Run with the mock binary (no Go binary needed):

```bash
MOCK_BINARY=true ./dev.sh
```

Run backend tests:

```bash
python3 -m pytest tests/ -v
```

---

## Clean build

To wipe all generated artifacts and start fresh:

```bash
make clean-all
```

This removes:

| Path | Contents |
|------|----------|
| `ess_comprestimator` | Compiled Go binary |
| `build/` | PyInstaller work directory |
| `dist/` | PyInstaller output (`comprestimator-backend`) |
| `dist-electron/` | Packaged installers (`.dmg`, `.AppImage`, `.deb`, `.rpm`) |
| `frontend/dist/` | Built React app |
| `.venv/` | Python virtual environment (PyInstaller + backend deps) |
| `frontend/node_modules/` | Frontend npm packages |
| `electron/node_modules/` | Electron npm packages |
| `**/__pycache__/`, `*.pyc` | Python bytecode cache |

After cleaning, a full rebuild is:

```bash
(cd frontend && npm install)
(cd electron && npm install)
./build.sh
```

Python dependencies are reinstalled automatically by `./build.sh` into a fresh `.venv/`.
