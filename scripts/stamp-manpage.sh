#!/usr/bin/env bash
# Stamp the binary's version into the manpage so the two cannot drift.
#
# Single source of truth: the VERSION constant in cmd/root.go. The manpage
# .TH line carries a copy for `man` to display; this script keeps that copy in
# sync instead of relying on someone remembering to hand-edit it on every bump.
#
#   scripts/stamp-manpage.sh          # rewrite packaging/ess_comprestimator.1 in place
#   scripts/stamp-manpage.sh --check  # exit 1 if the manpage is out of sync (CI / hooks)
#
# The date field is left alone — it is release metadata, set deliberately, not
# something to churn on every build.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/cmd/root.go"
MAN="$ROOT/packaging/ess_comprestimator.1"

version="$(sed -nE 's/^const VERSION = "([^"]+)".*/\1/p' "$SRC" | head -1)"
if [[ -z "$version" ]]; then
  echo "ERROR: could not read 'const VERSION' from $SRC" >&2
  exit 1
fi

current="$(sed -nE '/^\.TH/ s/.*ess_comprestimator ([0-9][0-9.]*).*/\1/p' "$MAN" | head -1)"
if [[ -z "$current" ]]; then
  echo "ERROR: could not find 'ess_comprestimator <version>' in the .TH line of $MAN" >&2
  exit 1
fi

if [[ "${1:-}" == "--check" ]]; then
  if [[ "$current" != "$version" ]]; then
    echo "ERROR: manpage version ($current) does not match cmd/root.go VERSION ($version)." >&2
    echo "       Run: scripts/stamp-manpage.sh" >&2
    exit 1
  fi
  echo "manpage version in sync ($version)"
  exit 0
fi

if [[ "$current" == "$version" ]]; then
  echo "manpage already at version $version — no change"
  exit 0
fi

tmp="$(mktemp)"
sed -E '/^\.TH/ s/ess_comprestimator [0-9][0-9.]*/ess_comprestimator '"$version"'/' "$MAN" > "$tmp"
mv "$tmp" "$MAN"
echo "Stamped manpage: $current -> $version"
