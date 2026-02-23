#!/usr/bin/env python3
"""Subsample paired FASTQ files with synchronized R1/R2 selection."""

from __future__ import annotations

import argparse
import csv
import gzip
import os
import random
import re
import shutil
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, TextIO


@dataclass
class FastqRecord:
    header: str
    seq: str
    plus: str
    qual: str


def normalize_read_id(header: str) -> str:
    token = header.strip().split()[0]
    if token.startswith("@"):
        token = token[1:]
    if token.endswith("/1") or token.endswith("/2"):
        token = token[:-2]
    return token


def read_record(handle: TextIO) -> FastqRecord | None:
    h = handle.readline()
    if not h:
        return None
    s = handle.readline()
    p = handle.readline()
    q = handle.readline()
    if not q:
        raise ValueError("Malformed FASTQ: truncated record")
    return FastqRecord(h, s, p, q)


def iter_pairs(fq1: Path, fq2: Path) -> Iterator[tuple[FastqRecord, FastqRecord]]:
    with gzip.open(fq1, "rt") as h1, gzip.open(fq2, "rt") as h2:
        while True:
            r1 = read_record(h1)
            r2 = read_record(h2)
            if r1 is None and r2 is None:
                break
            if (r1 is None) != (r2 is None):
                raise ValueError("R1/R2 length mismatch")
            yield r1, r2


def write_record(handle: TextIO, rec: FastqRecord) -> None:
    handle.write(rec.header)
    handle.write(rec.seq)
    handle.write(rec.plus)
    handle.write(rec.qual)


def safe_symlink(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    dst.symlink_to(src)


def default_threads() -> int:
    for key in ("SUBSAMPLE_THREADS", "SLURM_CPUS_PER_TASK"):
        raw = os.environ.get(key)
        if raw:
            with suppress(ValueError):
                n = int(raw)
                if n > 0:
                    return n
    return max(1, os.cpu_count() or 1)


def check_pair_headers_prefix(fq1: Path, fq2: Path, limit: int) -> tuple[int, int]:
    if limit <= 0:
        return 0, 0

    checks = 0
    mismatches = 0
    with gzip.open(fq1, "rt") as h1, gzip.open(fq2, "rt") as h2:
        while checks < limit:
            r1 = read_record(h1)
            r2 = read_record(h2)
            if r1 is None and r2 is None:
                break
            if (r1 is None) != (r2 is None):
                raise ValueError("R1/R2 length mismatch")
            checks += 1
            if normalize_read_id(r1.header) != normalize_read_id(r2.header):
                mismatches += 1
    return checks, mismatches


def run_seqtk_size(path: Path) -> int:
    proc = subprocess.run(["seqtk", "size", str(path)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"seqtk size failed for {path}:\n{proc.stderr.strip()}")
    fields = proc.stdout.strip().split()
    if not fields:
        raise RuntimeError(f"seqtk size produced no output for {path}")
    try:
        return int(fields[0])
    except ValueError as exc:
        raise RuntimeError(f"Could not parse seqtk size output for {path}: {proc.stdout!r}") from exc


def count_paired_reads_seqtk(fq1: Path, fq2: Path) -> int:
    n1 = run_seqtk_size(fq1)
    n2 = run_seqtk_size(fq2)
    if n1 != n2:
        raise ValueError(f"R1/R2 read count mismatch from seqtk size: {n1} != {n2}")
    return n1


_REFORMAT_READS_RE = re.compile(r"^(Input|Output):\s+([0-9][0-9,]*)\s+reads\b", re.MULTILINE)


def parse_reformat_read_counts(log_text: str) -> tuple[int, int]:
    counts: dict[str, int] = {}
    for label, raw_n in _REFORMAT_READS_RE.findall(log_text):
        counts[label] = int(raw_n.replace(",", ""))
    if "Input" not in counts or "Output" not in counts:
        raise RuntimeError("Could not parse Input/Output read counts from reformat.sh output")
    return counts["Input"], counts["Output"]


def run_reformat_sample(
    fq1: Path,
    fq2: Path,
    out1: Path,
    out2: Path,
    fraction: float,
    seed: int,
    threads: int,
) -> tuple[int, int]:
    cmd = [
        "reformat.sh",
        f"in={fq1}",
        f"in2={fq2}",
        f"out={out1}",
        f"out2={out2}",
        f"samplerate={fraction:.12g}",
        f"sampleseed={seed}",
        f"threads={max(1, threads)}",
        "verifypaired=t",
        "allowidenticalnames=t",
        "ow=t",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    log_text = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(f"reformat.sh failed (exit {proc.returncode}):\n{log_text.strip()}")

    input_reads, output_reads = parse_reformat_read_counts(log_text)
    if input_reads % 2 != 0 or output_reads % 2 != 0:
        raise RuntimeError(
            f"Expected paired read counts from reformat.sh, got input={input_reads}, output={output_reads}"
        )
    return input_reads // 2, output_reads // 2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fq1", required=True, type=Path)
    p.add_argument("--fq2", required=True, type=Path)
    p.add_argument("--out1", required=True, type=Path)
    p.add_argument("--out2", required=True, type=Path)
    p.add_argument("--stats-out", required=True, type=Path)
    p.add_argument("--fraction", required=True, type=float)
    p.add_argument("--seed", required=True, type=int)
    p.add_argument("--check-prefix", type=int, default=10000)
    p.add_argument("--passthrough", action="store_true", help="Symlink input FASTQs instead of writing sampled FASTQs")
    p.add_argument("--threads", type=int, default=default_threads())
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not (0.0 < args.fraction <= 1.0):
        raise SystemExit("--fraction must be in (0, 1]")

    args.out1.parent.mkdir(parents=True, exist_ok=True)
    args.out2.parent.mkdir(parents=True, exist_ok=True)
    args.stats_out.parent.mkdir(parents=True, exist_ok=True)

    if not args.overwrite and args.stats_out.exists():
        raise SystemExit(f"stats output already exists: {args.stats_out}")

    rng = random.Random(args.seed)

    total_pairs = 0
    sampled_pairs = 0
    header_checks, mismatches = check_pair_headers_prefix(args.fq1, args.fq2, args.check_prefix)

    if args.passthrough:
        safe_symlink(args.fq1.resolve(), args.out1)
        safe_symlink(args.fq2.resolve(), args.out2)
        if shutil.which("seqtk"):
            total_pairs = count_paired_reads_seqtk(args.fq1, args.fq2)
            sampled_pairs = total_pairs
        else:
            for _r1, _r2 in iter_pairs(args.fq1, args.fq2):
                total_pairs += 1
                sampled_pairs += 1
    else:
        if args.out1.exists() or args.out2.exists():
            if not args.overwrite:
                raise SystemExit("output fastq exists; pass --overwrite to replace")
            if args.out1.exists() or args.out1.is_symlink():
                args.out1.unlink()
            if args.out2.exists() or args.out2.is_symlink():
                args.out2.unlink()

        if shutil.which("reformat.sh"):
            total_pairs, sampled_pairs = run_reformat_sample(
                fq1=args.fq1,
                fq2=args.fq2,
                out1=args.out1,
                out2=args.out2,
                fraction=args.fraction,
                seed=args.seed,
                threads=args.threads,
            )
        else:
            with gzip.open(args.out1, "wt") as out1, gzip.open(args.out2, "wt") as out2:
                for r1, r2 in iter_pairs(args.fq1, args.fq2):
                    total_pairs += 1
                    if rng.random() <= args.fraction:
                        write_record(out1, r1)
                        write_record(out2, r2)
                        sampled_pairs += 1

    with args.stats_out.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(
            [
                "fq1",
                "fq2",
                "out1",
                "out2",
                "fraction",
                "seed",
                "total_read_pairs",
                "sampled_read_pairs",
                "header_checks",
                "header_mismatches",
                "passthrough",
            ]
        )
        writer.writerow(
            [
                str(args.fq1),
                str(args.fq2),
                str(args.out1),
                str(args.out2),
                f"{args.fraction:.6f}",
                str(args.seed),
                str(total_pairs),
                str(sampled_pairs),
                str(header_checks),
                str(mismatches),
                "1" if args.passthrough else "0",
            ]
        )

    if mismatches > 0:
        raise SystemExit(f"detected {mismatches} read header mismatches in paired FASTQ prefix")


if __name__ == "__main__":
    main()
