#!/usr/bin/bash -l
# Run from the benchmark root. A receipt prevents accidental duplicate recovery.
set -euo pipefail
BASE_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$BASE_DIR"
python3.12 scripts/recover_checkpoint_r2.py --preflight
if ! partition="$(timeout 15 scontrol show partition epyc -o)"; then
  echo "Cannot read epyc partition limits from SLURM. No jobs submitted; retry from the cluster terminal." >&2
  exit 1
fi
python3.12 - "$partition" <<'PY'
import re
import sys
match = re.search(r'\bMaxTime=(\S+)', sys.argv[1])
if not match:
    raise SystemExit('Cannot validate epyc wall-time limit; no jobs submitted.')
value = match[1]
if value != 'UNLIMITED':
    days, clock = value.split('-', 1) if '-' in value else ('0', value)
    parts = [int(part) for part in clock.split(':')]
    seconds = int(days) * 86400
    for part, scale in zip(reversed(parts), (1, 60, 3600)):
        seconds += part * scale
    if seconds < 8 * 3600:
        raise SystemExit('epyc does not allow requested eight hours; no jobs submitted.')
print('Verified epyc MaxTime=' + value)
PY
mkdir -p logs
receipt=logs/checkpoint-213a0df-r2-recovery.submission
# Exclusive creation: retain even an unconfirmed attempt for scheduler review.
(set -o noclobber; date -Iseconds > "$receipt") || {
  echo "Submission receipt already exists: $receipt; inspect it before resubmitting." >&2
  exit 1
}
if ! array="$(timeout 30 sbatch --parsable --array=0-5 scripts/run_r2_recovery.slurm)"; then
  echo "Array submission failed or is unconfirmed. Inspect squeue and $receipt before retrying." >&2
  exit 1
fi
array="${array%%;*}"
[[ "$array" =~ ^[0-9]+$ ]] || { echo "Unconfirmed array submission; inspect scheduler and $receipt" >&2; exit 1; }
echo "array=$array" | tee -a "$receipt"
if ! finalize="$(timeout 30 sbatch --parsable --dependency="afterok:$array" scripts/finalize_r2_recovery.slurm)"; then
  echo "Array $array submitted; finalization failed or is unconfirmed. Inspect $receipt and scheduler; do not resubmit the array." >&2
  exit 1
fi
finalize="${finalize%%;*}"
[[ "$finalize" =~ ^[0-9]+$ ]] || { echo "Array $array submitted; finalization unconfirmed. See $receipt" >&2; exit 1; }
echo "finalize=$finalize" | tee -a "$receipt"
