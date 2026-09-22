#!/usr/bin/env bash
# Stamp the binary's version into every file that carries a copy, so they
# cannot drift from each other.
#
# Single source of truth: the VERSION constant in cmd/root.go. Two other files
# duplicate it for their own tooling:
#   - packaging/ess_comprestimator.1   (.TH line, shown by `man`)
#   - electron/package.json            ("version", used by electron-builder)
# This script keeps both in sync instead of relying on hand edits on every bump.
#
#   scripts/stamp-version.sh          # rewrite both files in place
#   scripts/stamp-version.sh --check  # exit 1 if either is out of sync (CI / hooks)
#
# --check is dependency-free (sed only) so it runs in CI jobs without Node.
# Manpage dates are release metadata and are left alone; only versions are stamped.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/cmd/root.go"
MAN="$ROOT/packaging/ess_comprestimator.1"
PKG="$ROOT/electron/package.json"

check_only=false
[[ "${1:-}" == "--check" ]] && check_only=true

version="$(sed -nE 's/^const VERSION = "([^"]+)".*/\1/p' "$SRC" | head -1)"
if [[ -z "$version" ]]; then
  echo "ERROR: could not read 'const VERSION' from $SRC" >&2
  exit 1
fi

# Current values in the two downstream files.
man_current="$(sed -nE '/^\.TH/ s/.*ess_comprestimator ([0-9][0-9.]*).*/\1/p' "$MAN" | head -1)"
pkg_current="$(sed -nE 's/.*"version": *"([^"]+)".*/\1/p' "$PKG" | head -1)"
if [[ -z "$man_current" ]]; then
  echo "ERROR: could not find 'ess_comprestimator <version>' in the .TH line of $MAN" >&2
  exit 1
fi
if [[ -z "$pkg_current" ]]; then
  echo "ERROR: could not find a top-level \"version\" field in $PKG" >&2
  exit 1
fi

if $check_only; then
  drift=0
  if [[ "$man_current" != "$version" ]]; then
    echo "ERROR: manpage version ($man_current) != cmd/root.go VERSION ($version)" >&2
    drift=1
  fi
  if [[ "$pkg_current" != "$version" ]]; then
    echo "ERROR: electron/package.json version ($pkg_current) != cmd/root.go VERSION ($version)" >&2
    drift=1
  fi
  if [[ "$drift" -ne 0 ]]; then
    echo "       Run: scripts/stamp-version.sh" >&2
    exit 1
  fi
  echo "versions in sync ($version): manpage, electron/package.json"
  exit 0
fi

changed=0

# Temp files are created next to the target so the mv is a same-filesystem
# atomic rename (avoids cross-device copy + chown warnings on mounted volumes).
if [[ "$man_current" != "$version" ]]; then
  tmp="$(mktemp "$MAN.XXXXXX")"
  sed -E '/^\.TH/ s/ess_comprestimator [0-9][0-9.]*/ess_comprestimator '"$version"'/' "$MAN" > "$tmp"
  mv "$tmp" "$MAN"
  echo "Stamped manpage: $man_current -> $version"
  changed=1
fi

if [[ "$pkg_current" != "$version" ]]; then
  # Replace only the first "version": "..." (the top-level field); dependency
  # version strings elsewhere in the file are left untouched.
  tmp="$(mktemp "$PKG.XXXXXX")"
  awk -v v="$version" '
    !done && /"version":[[:space:]]*"[^"]*"/ {
      sub(/"version":[[:space:]]*"[^"]*"/, "\"version\": \"" v "\"")
      done = 1
    }
    { print }
  ' "$PKG" > "$tmp"
  mv "$tmp" "$PKG"
  echo "Stamped electron/package.json: $pkg_current -> $version"
  changed=1
fi

[[ "$changed" -eq 0 ]] && echo "already at version $version — no change"
exit 0
