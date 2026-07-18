#!/usr/bin/bash -l
# Provision the frozen pixi environments (idempotent). RelocaTE2 is NOT here: it
# is frozen via pinned cluster modules (callers/relocate2/pinned-modules.txt),
# not a pixi env, so it needs no install.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if ! command -v pixi >/dev/null 2>&1; then
  echo "ERROR: pixi not on PATH; required to provision frozen envs." >&2
  exit 1
fi
echo "[$(date)] provisioning frozen pixi environments"
for m in callers/relocate3 env/benchmark; do
  echo "== pixi install: $m =="
  ( cd "$m" && pixi install )
done
echo "[$(date)] done. Pixi envs are under each dir's .pixi/ (gitignored)."
echo "Note: RelocaTE2 uses pinned cluster modules (callers/relocate2/pinned-modules.txt), no install needed."
