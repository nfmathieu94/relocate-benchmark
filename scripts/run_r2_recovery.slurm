#!/usr/bin/bash -l
#SBATCH -p epyc
#SBATCH --mem=64gb
#SBATCH --cpus-per-task=8
#SBATCH --time=08:00:00
#SBATCH -o logs/r2-recovery.%A_%a.log
# epyc previously verified MaxTime=30 days; submit wrapper rechecks live limit.
set -euo pipefail
BASE_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$BASE_DIR"
THREADS="${SLURM_CPUS_PER_TASK:-1}"
export THREADS
ADAPTER_DIR=callers/relocate2
source callers/relocate2/env.sh
apptainer --version
/usr/bin/time -v -o "logs/r2-recovery-resource.${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.txt" \
  python3.12 scripts/recover_checkpoint_r2.py --task "$SLURM_ARRAY_TASK_ID"
