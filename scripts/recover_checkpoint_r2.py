#!/usr/bin/env python3
"""Recover six audited R2 tasks using cached alignments and isolated outputs.

Run from the benchmark root. Heavy work requires SLURM. Promotion requires all
six tasks and archives original results/reports; no original alignments move.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

SPEC = importlib.util.spec_from_file_location(
    "r2validate", "callers/relocate2/validate.py"
)
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)
TASKS = [
    ("mping", "cov30x_rep2"),
    ("mping", "cov30x_rep3"),
    ("ricetelib", "cov15x_rep1"),
    ("ricetelib", "cov15x_rep3"),
    ("ricetelib_divergence", "div010_rep02_cov5x"),
    ("ricetelib_divergence", "div010_rep03_cov5x"),
]
WORK = Path("runs/checkpoint-213a0df")
REPORT = Path("reports/checkpoint-213a0df/datasets")
RECOVERY = Path("runs/checkpoint-213a0df-r2-recovery")


def source_check():
    subprocess.run(
        [
            "python3.12",
            "callers/relocate3-checkpoint-213a0df/verify_source.py",
            "config/checkpoint-213a0df.source.json",
        ],
        check=True,
    )


def preflight():
    source_check()
    for ds, sample in TASKS:
        old = WORK / ds / "relocate2" / sample
        for step in (5, 6):
            jobs = validation.commands(old / "raw", step)
            if {a[3] for _, a in jobs} != {f"Chr{i}" for i in range(1, 13)}:
                raise ValueError(f"Unexpected chromosome set: {old}")
            for _, args in jobs:
                for index in (2, 4, 6, 9):
                    if not Path(args[index]).is_file():
                        raise FileNotFoundError(args[index])
        for name in ("bam", "raw/repeat/te_containing_fq", "raw/repeat/flanking_seq"):
            if not (old / name).is_dir():
                raise FileNotFoundError(old / name)
        bams = list((old / "bam").glob("*.bam"))
        bams += list((old / "raw/repeat/bwa_aln").glob("*.sorted.bam"))
        if len(bams) < 3:
            raise ValueError(f"Missing cached alignments: {old}")
        for bam in bams:
            if not Path(str(bam) + ".bai").is_file():
                raise FileNotFoundError(str(bam) + ".bai")
    print(
        "Preflight passed: six tasks, cached BAMs/indexes and 12 workers per step.",
        flush=True,
    )


def checked(command, log, cwd=None):
    with log.open("x") as handle:
        subprocess.run(
            command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, check=True
        )
    with log.open(errors="replace") as handle:
        if any("Traceback (most recent call last)" in line for line in handle):
            raise RuntimeError(f"Internal worker exception: {log}")


def run(index, threads):
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("Recovery must run through SLURM")
    source_check()
    ds, sample = TASKS[index]
    old = (WORK / ds / "relocate2" / sample).resolve()
    new = (RECOVERY / ds / sample).absolute()
    if (new / ".complete").exists():
        validation.validate(new)
        print(f"Recovery already complete: {new}")
        return
    if new.exists():
        raise FileExistsError(
            f"Incomplete recovery retained; inspect before retrying: {new}"
        )
    jobs = {step: validation.commands(old / "raw", step) for step in (5, 6)}
    (new / "raw/repeat/results").mkdir(parents=True)
    (new / "logs").mkdir()
    for directory in ("bam", "raw/repeat/bwa_aln"):
        target = new / directory
        target.mkdir(parents=True, exist_ok=True)
        for item in (old / directory).iterdir():
            (target / item.name).symlink_to(item.resolve())
    for directory in ("flanking_seq", "te_containing_fq"):
        (new / "raw/repeat" / directory).symlink_to(old / "raw/repeat" / directory)
    for name in ("raw/regex.txt", "raw/repeat/existingTE.bed"):
        shutil.copy2(old / name, new / name)
    image = Path("callers/relocate2/images/relocate2.sif").resolve()
    prefix = ["apptainer", "exec", str(image)]
    script_hashes = {}
    for step in (5, 6):
        commands = []
        script_dir = new / "raw/shellscripts" / f"step_{step}"
        script_dir.mkdir(parents=True)
        for script, args in jobs[step]:
            script_hashes[str(script)] = hashlib.sha256(script.read_bytes()).hexdigest()
            rewritten = [value.replace(str(old), str(new)) for value in args]
            (script_dir / script.name).write_text(shlex.join(rewritten) + "\n")
            commands.append(
                (prefix + rewritten, new / "logs" / f"step{step}-{args[3]}.log")
            )
        with ThreadPoolExecutor(max_workers=threads) as pool:
            list(pool.map(lambda item: checked(*item, cwd=new), commands))
    validation.validate(new, final=False)
    results = new / "raw/repeat/results"
    for kind in ("nonref", "ref"):
        for ext in ("txt", "gff"):
            destination = results / f"ALL.all_{kind}_insert.{ext}"
            with destination.open("x") as handle:
                for path in sorted(
                    results.glob(f"Chr*.repeat.all_{kind}_insert.{ext}")
                ):
                    for line in path.open():
                        if kind == "nonref" and ext == "txt" and line.startswith("TE"):
                            continue
                        handle.write(line)
    reference = jobs[5][0][1][4]
    checked(
        prefix
        + [
            "python",
            "/usr/local/bin/clean_false_positive.py",
            "--input",
            str(results / "ALL.all_nonref_insert.gff"),
            "--refte",
            str(new / "raw/repeat/existingTE.bed"),
            "--bedtools",
            "/usr/local/bin/bedtools",
        ],
        new / "logs/clean.log",
        cwd=new,
    )
    checked(
        prefix
        + [
            "perl",
            "/usr/local/bin/characterizer.pl",
            "-s",
            str(results / "ALL.all_nonref_insert.txt"),
            "-b",
            str(new / "bam"),
            "-g",
            reference,
            "--samtools",
            "/usr/local/bin/samtools",
        ],
        new / "logs/characterize.log",
        cwd=new,
    )
    validation.validate(new)
    subprocess.run(
        [
            "python3.12",
            "callers/relocate2/normalize.py",
            "--outdir",
            str(new),
            "--sample",
            sample,
        ],
        check=True,
    )
    subprocess.run(
        [
            "python3.12",
            "scoring/score_calls.py",
            "--truth",
            f"truth/{ds}/per_sample/{sample}.tsv",
            "--calls",
            str(new / "calls.normalized.tsv"),
            "--sample",
            sample,
            "--caller",
            "relocate2",
            "--window",
            "10",
            "--coordinate-policy",
            "tsd-interval",
            "--outdir",
            str(new / "report"),
        ],
        check=True,
    )
    source_check()
    (new / "provenance.json").write_text(
        json.dumps(
            dict(
                recorded=datetime.now().astimezone().isoformat(),
                source=str(old),
                job=os.environ["SLURM_JOB_ID"],
                script_sha256=script_hashes,
                scope="R2 steps 5/6/7 only; cached alignments; not full-pipeline timing",
            ),
            indent=2,
        )
    )
    (new / ".complete").write_text(datetime.now().astimezone().isoformat() + "\n")


def promote():
    source_check()
    # Validate every task before changing any original result.
    for ds, sample in TASKS:
        new = RECOVERY / ds / sample
        if not (new / ".complete").is_file():
            raise ValueError(f"Recovery not complete: {new}")
        validation.validate(new)
        for name in ("matches.tsv", "precision.tsv", "correctness.tsv"):
            if not (new / "report" / name).is_file():
                raise FileNotFoundError(new / "report" / name)
        with (new / "report/matches.tsv").open() as handle:
            if len(list(csv.DictReader(handle, delimiter="\t"))) != 500:
                raise ValueError(f"Invalid truth coverage: {new}")
    archive = RECOVERY / "original-results"
    # Archive the entire small report tree once, including PDFs before refresh.
    if not (archive / "reports").exists():
        archive.mkdir(parents=True, exist_ok=True)
        shutil.copytree(REPORT.parent, archive / "reports")
        (archive / ".reports_complete").touch()
    if not (archive / ".reports_complete").exists():
        raise RuntimeError(
            f"Interrupted report backup: inspect {archive}; original reports unchanged"
        )
    for ds, sample in TASKS:
        new = RECOVERY / ds / sample
        old = WORK / ds / "relocate2" / sample
        backup = archive / ds / sample
        if (new / ".promoted").exists():
            continue
        if backup.exists():
            raise FileExistsError(
                f"Interrupted promotion: inspect {backup}; originals retained there"
            )
        backup.mkdir(parents=True)
        shutil.move(str(old / "raw/repeat/results"), backup / "results")
        shutil.copytree(new / "raw/repeat/results", old / "raw/repeat/results")
        for name in ("calls.normalized.tsv", ".run_complete"):
            shutil.move(str(old / name), backup / name)
        shutil.copy2(new / "calls.normalized.tsv", old / "calls.normalized.tsv")
        (old / ".run_complete").write_text(
            "Recovered R2 steps 5/6/7; see " + str(new) + "\n"
        )
        shutil.copy2(new / "provenance.json", old / "recovery.provenance.json")
        target = REPORT / ds / "per_sample/relocate2" / sample
        shutil.move(str(target), backup / "report")
        shutil.copytree(new / "report", target)
        # Failed original runs cannot serve as full-pipeline resource measures.
        resource = REPORT / ds / "resources/relocate2" / f"{sample}.tsv"
        shutil.move(str(resource), backup / "original-resource.tsv")
        (new / ".promoted").write_text(datetime.now().astimezone().isoformat() + "\n")
    print(
        "Promoted six recovered results; original outputs archived. R2 resources now cover 66 valid full runs."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--task", type=int, choices=range(6))
    group.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        preflight()
    elif args.promote:
        promote()
    else:
        run(args.task, int(os.environ.get("SLURM_CPUS_PER_TASK", "1")))
