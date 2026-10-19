#!/usr/bin/bash -l
#SBATCH -p epyc
#SBATCH --mem=8gb
#SBATCH --cpus-per-task=2
#SBATCH --time=00:30:00
#SBATCH -o logs/r2-recovery-finalize.%j.log
set -euo pipefail
BASE_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$BASE_DIR"
THREADS="${SLURM_CPUS_PER_TASK:-1}"
export THREADS
python3.12 scripts/recover_checkpoint_r2.py --promote
CONFIG=config/benchmark.checkpoint-213a0df.toml DATASET_SELECTION=full \
  bash pipeline/aggregate.sh
