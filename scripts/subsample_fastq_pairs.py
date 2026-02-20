#!/usr/bin/env python3
"""Subsample paired FASTQ files with synchronized R1/R2 selection."""

from __future__ import annotations

import argparse
import csv
import gzip
import os
import random
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
    header_checks = 0
    mismatches = 0

    if args.passthrough:
        safe_symlink(args.fq1.resolve(), args.out1)
        safe_symlink(args.fq2.resolve(), args.out2)
        for r1, r2 in iter_pairs(args.fq1, args.fq2):
            total_pairs += 1
            if total_pairs <= args.check_prefix:
                header_checks += 1
                if normalize_read_id(r1.header) != normalize_read_id(r2.header):
                    mismatches += 1
            sampled_pairs += 1
    else:
        if args.out1.exists() or args.out2.exists():
            if not args.overwrite:
                raise SystemExit("output fastq exists; pass --overwrite to replace")
            if args.out1.exists() or args.out1.is_symlink():
                args.out1.unlink()
            if args.out2.exists() or args.out2.is_symlink():
                args.out2.unlink()

        with gzip.open(args.out1, "wt") as out1, gzip.open(args.out2, "wt") as out2:
            for r1, r2 in iter_pairs(args.fq1, args.fq2):
                total_pairs += 1
                if total_pairs <= args.check_prefix:
                    header_checks += 1
                    if normalize_read_id(r1.header) != normalize_read_id(r2.header):
                        mismatches += 1
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
