# ESS Comprestimator

Estimates the FCM compression ratio that IBM ESS / GPFS would achieve on a given file or directory.

Originally authored by _Avishay Traeger_, _Danny Harnik_, _Dmitry Sotnikov_.
Modified for ESS by _Sarvesh Chezhian_.

---

## Contents

- [Installation](#installation)
- [Using the app](#using-the-app)
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
   - *Percentage* — enter a custom sample percentage (e.g. `25%`).
3. **Optional filters:**
   - *Skip hidden files* — ignore dotfiles and hidden directories.
   - *Top-level only* — do not descend into subdirectories.
   - *Exclude patterns* — comma-separated filenames or globs (e.g. `*.log`, `node_modules`).
4. Click **Run** and watch the live log output.
5. When the job completes, the **Results** panel shows:
   - Estimated compression ratio and interpretation (Excellent / Good / Moderate / Low)
   - Size reduction percentage and before/after chart
   - Sample size, blocks read, run time
   - **Download CSV** to export the raw numbers.

> Jobs are queued — you can submit multiple runs and they execute one at a time. Previous jobs remain visible in the list on the home screen.

---

## Building from source

The easiest way to use the tool is the packaged desktop app, which bundles the backend, frontend, and C binary into a double-clickable installer.

### Prerequisites

| Tool | macOS | Linux |
|------|-------|-------|
| Python 3.9+ | `brew install python` | `sudo apt install python3 python3-venv` |
| Node 18+ | `brew install node` | `sudo apt install nodejs npm` |
| GCC | Xcode Command Line Tools (`xcode-select --install`) | `sudo apt install gcc` |

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

- Python 3.x on PATH
- C binary compiled via `make` (see below)

### Build the C binary

```bash
make
```

Works on Linux (x86_64) and macOS (arm64, x86_64).

### Run

```bash
python3 run_comprestimator.py --path <file or directory>
```

#### Sampling options

| Flag | Description |
|------|-------------|
| *(default)* | Auto: 10% sample, or exhaustive if directory < 10 GB |
| `--exhaustive-sampling` | Scan entire directory — most accurate, slowest |
| `--sampling-percentage 25%` | Sample a specific percentage of the directory |

#### Filter options

| Flag | Description |
|------|-------------|
| `--skip-hidden` | Skip hidden files and directories (names starting with `.`) |
| `--skip-nested-directories` | Only scan the top level of the target directory |
| `--exclude FILE ...` | Exclude specific filenames or glob patterns |

#### Examples

```bash
# Estimate compression for a directory using 25% sampling
python3 run_comprestimator.py --path /data/myvolume --sampling-percentage 25%

# Exhaustive scan, skipping hidden files and node_modules
python3 run_comprestimator.py --path /data/myvolume --exhaustive-sampling \
    --skip-hidden --exclude node_modules "*.log"
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

Run with the mock binary (no C binary needed):

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
| `comprestimator`, `comprestimator.o` | Compiled C binary and object file |
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
