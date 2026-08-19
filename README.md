# ESS Comprestimator

Estimates the FCM compression ratio that IBM ESS / GPFS would achieve on a given file or directory.

Originally authored by _Avishay Traeger_, _Danny Harnik_, _Dmitry Sotnikov_.
Modified for ESS by _Sarvesh Chezhian_.

See [CHANGELOG.md](CHANGELOG.md) for release notes, including which past
releases are safe to use.

---

## Contents

- [Installation](#installation)
- [Using the app](#using-the-app)
- [Understanding the results](#understanding-the-results)
- [Security](#security)
- [Building from source](#building-from-source)
- [Command-line interface](#command-line-interface)
- [Development](#development)
- [Clean build](#clean-build)

---

## Installation

### macOS

1. Open the `.dmg` file and drag **Comprestimator** into your Applications folder.
2. Launch it. Signed, notarized builds open normally and need nothing further.
   Unsigned builds — the default when no Apple signing secrets are configured,
   see [macOS code signing and notarization](#macos-code-signing-and-notarization)
   — are blocked by Gatekeeper with one of two messages:

   **"Apple cannot verify this app"** — open **System Settings → Privacy & Security**, scroll to the blocked-app entry, and click **Open Anyway**.

   **"Comprestimator is damaged and can't be opened"** — this happens when macOS quarantines a file downloaded by a browser. Remove the quarantine flag in Terminal, then launch normally:

   ```bash
   xattr -dr com.apple.quarantine /Applications/Comprestimator.app
   ```

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
   - *Auto (default)* — samples 10% of the data. For a full scan, choose Exhaustive.
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
- **Skipped (incompressible)** — if the results panel shows a "Skipped" row, some sampled data could not be compressed (e.g. `.zip`, `.jpg`, `.mp4`, or encrypted files). These samples are excluded from the ratio estimate, which therefore reflects only the compressible portion of your data. If a large percentage is skipped, the ratio may be optimistic for the full dataset.

---

## Security

The backend API enforces the following controls:

### Path confinement

The analysis path is resolved to its real absolute path (symlinks followed) and then checked against an allowlist of user-owned locations before the binary is invoked:

| Allowed root | Purpose |
|---|---|
| `~` (home directory) | Primary user data |
| `/Volumes/*` (macOS) | External and network drives |
| `/media/*`, `/mnt/*` (Linux) | Mounted drives |
| `/tmp`, `/private/tmp` | Temporary files |

Requests targeting paths outside these roots (e.g. `/etc`, `/usr`, `/root`) are rejected with HTTP 403. This prevents another local process or a malicious `localhost` request from probing sensitive system paths.

### API response filtering

Internal fields such as the subprocess PID are stripped from all API responses and never exposed to the caller.

---

## Building from source

The packaged desktop app bundles the backend, frontend, and Go binary into a double-clickable installer.

### Prerequisites

**Required:**

| Tool | macOS | Linux |
|------|-------|-------|
| Go 1.21+ | `brew install go` | `sudo apt install golang-go` |
| Python 3.9+ | `brew install python` | `sudo apt install python3 python3-venv` |
| Node 18+ | `brew install node` | `sudo apt install nodejs npm` |

> **Go is required** — the build will fail if `go` is not found on PATH.

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

### macOS code signing and notarization

Builds are unsigned unless signing credentials are present, so the repo builds
fine without an Apple Developer account. To ship a `.dmg` that opens without a
Gatekeeper warning, you need a paid Apple Developer Program membership
($99/year) and the five repository secrets below.

**1. Create a Developer ID Application certificate.** In Xcode, go to
**Settings → Accounts**, select your team, click **Manage Certificates**, then
**+ → Developer ID Application**. (Without Xcode, create a Certificate Signing
Request in Keychain Access and upload it at
[developer.apple.com/account/resources/certificates](https://developer.apple.com/account/resources/certificates).)
Note that only an Account Holder can create Developer ID certificates.

**2. Export it as a `.p12`.** In **Keychain Access**, find the
`Developer ID Application: <your name> (<team id>)` entry, expand it so both the
certificate and its private key are selected, right-click → **Export 2 items**,
and save as `.p12` with a password. Keep that password — it becomes
`APPLE_CERTIFICATE_PASSWORD`.

**3. Base64-encode the `.p12`** so it can be stored as a secret. This prints the
value to paste into GitHub:

```bash
base64 -i /path/to/certificate.p12 | pbcopy
```

**4. Create an app-specific password** for notarization at
[appleid.apple.com](https://appleid.apple.com) under **Sign-In and Security →
App-Specific Passwords**. Your regular Apple ID password will not work.

**5. Add the secrets** under **Settings → Secrets and variables → Actions** in
this repository:

| Secret | Value |
|--------|-------|
| `APPLE_CERTIFICATE` | Base64 string from step 3 |
| `APPLE_CERTIFICATE_PASSWORD` | Password chosen when exporting the `.p12` |
| `APPLE_TEAM_ID` | 10-character Team ID from [the membership page](https://developer.apple.com/account#MembershipDetailsCard) |
| `APPLE_ID` | Apple ID email for the developer account |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific password from step 4 |

Once all five exist, the macOS job signs the app with the hardened runtime and
submits it to Apple's notary service. Notarization adds roughly 5–15 minutes to
the build. If any secret is missing, the build still succeeds and produces an
unsigned `.dmg`.

To verify a finished build:

```bash
spctl --assess --type execute --verbose /Applications/Comprestimator.app
```

`accepted` with `source=Notarized Developer ID` means it will open cleanly on
any Mac.

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

`dev.sh` automatically:
- Creates a Python virtual environment in `.venv/` if one does not exist
- Installs Python dependencies from `backend/requirements.txt`
- Runs `npm install` in `frontend/` if `node_modules/` is missing
- Installs git hooks (`scripts/hooks/`) into `.git/hooks/`

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

Install the pinned lint and test tooling (the same versions CI uses, so a local
pass means a CI pass):

```bash
pip install -r backend/requirements-dev.lock
```

These are pinned deliberately. Linters change their default rule sets between
releases, and an unpinned install lets a new release fail a build that touched
no Python at all. Bump `backend/requirements-dev.lock` when you want the new
rules, so the findings land in a reviewable diff.

Run dependency vulnerability scan:

```bash
pip-audit -r backend/requirements.txt
```

### Git hooks

Hooks are stored in `scripts/hooks/` and installed automatically by `dev.sh`. They run:

- **pre-commit** — `go vet`, `ruff` lint/format check (if installed), `shellcheck` (if installed)
- **pre-push** — full `pytest` suite

To install manually without running `dev.sh`:

```bash
cp scripts/hooks/pre-commit scripts/hooks/pre-push .git/hooks/
chmod +x .git/hooks/pre-commit .git/hooks/pre-push
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `COMPRESTIMATOR_PATH` | `./ess_comprestimator` | Path to the Go binary |
| `MOCK_BINARY` | `false` | Return synthetic results without invoking the binary |
| `MAX_CONCURRENT_JOBS` | `3` | Maximum parallel analysis jobs (must be an integer ≥ 1) |
| `DEV_CORS` | *(unset)* | Set to `true` to allow the Vite dev server origin — **never set in production** |

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
