#!/usr/bin/env python3
"""Build a single self-contained HTML gallery of split-pipe UMAPs in Samples mode.

The generator reads split-pipe `all-sample_analysis_summary.html` reports, extracts the
UMAP coordinates and sample labels (`umap_x`, `umap_y`, `samples_raw`) from the report's
embedded JavaScript, and writes a standalone HTML page that re-renders only the UMAPs
using Plotly.

Result: the gallery HTML no longer depends on loading the original report pages at view
 time and can be opened directly via `file://` (no local web server required).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class RunMeta:
    run_id: str
    fraction: float
    replicate: int
    is_reference: bool


@dataclass(frozen=True)
class GalleryEntry:
    run_id: str
    sublib: str
    fraction: float
    replicate: int
    is_reference: bool
    src_rel: str


_JS_STRING_RE_TEMPLATE = r"const\s+{var}\s*=\s*{func}\(\s*'((?:\\'|[^'])*)'\s*\);"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid", type=Path, default=Path("config/subsample_grid.tsv"))
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--output", type=Path, default=Path("figures/umap_sample_gallery.html"))
    p.add_argument(
        "--report-name",
        default="all-sample_analysis_summary.html",
        help="Report filename to aggregate (default: %(default)s)",
    )
    p.add_argument(
        "--sublib-glob",
        default="sublib_*",
        help="Sublibrary directory glob under each run (default: %(default)s)",
    )
    return p.parse_args()


def load_grid(grid_path: Path) -> Dict[str, RunMeta]:
    with grid_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        grid_rows: Dict[str, RunMeta] = {}
        for row in reader:
            run_id = row["run_id"]
            grid_rows[run_id] = RunMeta(
                run_id=run_id,
                fraction=float(row["fraction"]),
                replicate=int(row["replicate"]),
                is_reference=str(row["is_reference"]).strip() == "1",
            )
    return grid_rows


def collect_entries(
    runs_dir: Path,
    grid_meta: Dict[str, RunMeta],
    report_name: str,
    sublib_glob: str,
    output_path: Path,
) -> List[GalleryEntry]:
    entries: List[GalleryEntry] = []
    if not runs_dir.exists():
        raise FileNotFoundError(f"runs directory not found: {runs_dir}")

    output_dir = output_path.parent
    for run_id, meta in grid_meta.items():
        run_dir = runs_dir / run_id
        if not run_dir.exists():
            continue
        for report_path in sorted(run_dir.glob(f"{sublib_glob}/{report_name}")):
            sublib = report_path.parent.name
            src_rel = os.path.relpath(report_path, start=output_dir)
            entries.append(
                GalleryEntry(
                    run_id=run_id,
                    sublib=sublib,
                    fraction=meta.fraction,
                    replicate=meta.replicate,
                    is_reference=meta.is_reference,
                    src_rel=Path(src_rel).as_posix(),
                )
            )
    return entries


def _sort_key(entry: GalleryEntry):
    return (0 if entry.is_reference else 1, entry.fraction, entry.replicate, entry.sublib)


def _extract_js_single_quoted(text: str, var_name: str, func_name: str) -> str:
    pattern = _JS_STRING_RE_TEMPLATE.format(var=re.escape(var_name), func=re.escape(func_name))
    m = re.search(pattern, text, flags=re.S)
    if not m:
        raise ValueError(f"Could not find {var_name} = {func_name}('...') in report HTML")
    return m.group(1).replace("\\'", "'")


def decode_nlist(raw_str: str) -> List[float]:
    values: List[float] = []
    if not raw_str:
        return values
    for word in raw_str.split(","):
        if not word:
            continue
        if "x" in word:
            num_s, count_s = word.split("x", 1)
            count = int(count_s)
        else:
            num_s = word
            count = 1
        num = float(num_s)
        if count == 1:
            values.append(num)
        else:
            values.extend([num] * count)
    return values


def decode_comlist(raw_str: str) -> List[str]:
    if not raw_str:
        return []
    return raw_str.split(",")


def extract_umap_sample_traces(report_path: Path) -> List[dict]:
    text = report_path.read_text(encoding="utf-8", errors="replace")
    x_raw = _extract_js_single_quoted(text, "umap_x", "decode_nlist")
    y_raw = _extract_js_single_quoted(text, "umap_y", "decode_nlist")
    samples_raw = _extract_js_single_quoted(text, "samples_raw", "decode_comlist")

    xs = decode_nlist(x_raw)
    ys = decode_nlist(y_raw)
    samples = decode_comlist(samples_raw)

    if not (len(xs) == len(ys) == len(samples)):
        raise ValueError(
            f"UMAP length mismatch in {report_path}: x={len(xs)} y={len(ys)} samples={len(samples)}"
        )

    color_map = {
        "xcond_1": "#1f77b4",
        "xcond_2": "#ff7f0e",
        "xcond_3": "#2ca02c",
    }

    grouped: "OrderedDict[str, tuple[list[float], list[float]]]" = OrderedDict()
    for x, y, sample in zip(xs, ys, samples):
        if sample not in grouped:
            grouped[sample] = ([], [])
        gx, gy = grouped[sample]
        gx.append(x)
        gy.append(y)

    traces: List[dict] = []
    for sample, (gx, gy) in grouped.items():
        traces.append(
            {
                "type": "scattergl",
                "mode": "markers",
                "name": sample,
                "x": gx,
                "y": gy,
                "marker": {"size": 3, "opacity": 0.85, "color": color_map.get(sample)},
                "hovertemplate": f"<b>{sample}</b><extra></extra>",
            }
        )
    return traces


def build_panel_payload(
    entries: Sequence[GalleryEntry],
    runs_dir: Path,
    report_name: str,
) -> List[dict]:
    panels: List[dict] = []
    for e in sorted(entries, key=_sort_key):
        report_path = runs_dir / e.run_id / e.sublib / report_name
        traces = extract_umap_sample_traces(report_path)
        panels.append(
            {
                "run_id": e.run_id,
                "sublib": e.sublib,
                "fraction": e.fraction,
                "replicate": e.replicate,
                "is_reference": e.is_reference,
                "source_report": e.src_rel,
                "n_traces": len(traces),
                "n_points": int(sum(len(t.get("x", [])) for t in traces)),
                "traces": traces,
            }
        )
    return panels


def build_html(panels: List[dict]) -> str:
    payload_json = json.dumps(panels, separators=(",", ":"))

    template = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>UMAP Sample Gallery</title>
  <script src=\"https://cdn.plot.ly/plotly-3.1.0.min.js\"></script>
  <style>
    :root {
      --bg: #f4f0e8;
      --panel: #fffaf1;
      --ink: #1f1c17;
      --muted: #6f6658;
      --line: #d8cfbe;
      --accent: #1f6f78;
      --shadow: 0 10px 24px rgba(40, 32, 18, 0.08);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: Georgia, \"Times New Roman\", serif; }
    body { padding: 20px; }
    .topbar {
      position: sticky; top: 0; z-index: 20;
      background: color-mix(in oklab, var(--bg) 88%, white);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
      margin-bottom: 16px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(6px);
    }
    .title { font-size: 20px; font-weight: 700; margin: 0 0 4px; }
    .subtitle { font-size: 13px; color: var(--muted); margin: 0; }
    .stats { margin-top: 8px; font-size: 12px; color: var(--muted); display: flex; gap: 12px; flex-wrap: wrap; }
    .actions { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
    button {
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 999px;
      padding: 6px 10px;
      cursor: pointer;
      font: inherit;
      font-size: 12px;
    }
    button:hover { border-color: var(--accent); color: var(--accent); }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(680px, 1fr));
      gap: 14px;
      align-items: start;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }
    .card-head {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: start;
      padding: 10px 12px 8px;
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(135deg, rgba(31,111,120,0.08), rgba(31,111,120,0) 45%),
        linear-gradient(0deg, rgba(255,255,255,0.7), rgba(255,255,255,0.7));
    }
    .runline { font-size: 13px; font-weight: 700; }
    .metaline { font-size: 12px; color: var(--muted); }
    .status {
      font-size: 11px;
      color: var(--muted);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      white-space: nowrap;
      align-self: center;
    }
    .plot-wrap { background: #fff; padding: 8px; }
    .plot-host {
      min-height: 560px;
      border-radius: 10px;
      background:
        radial-gradient(circle at 20% 10%, rgba(31,111,120,0.05), transparent 30%),
        linear-gradient(#fff, #fff);
      border: 1px solid #efe8da;
    }
    .hint {
      margin-top: 14px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.35;
    }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    @media (max-width: 760px) {
      body { padding: 10px; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <section class=\"topbar\">
    <h1 class=\"title\">UMAP Sample Gallery</h1>
    <p class=\"subtitle\">Standalone UMAP plots extracted at build time from split-pipe reports (Samples mode only). No local server is required to view this file.</p>
    <div class=\"stats\" id=\"stats\"></div>
    <div class=\"actions\">
      <button id=\"single-col\" type=\"button\">Toggle Single Column</button>
    </div>
  </section>

  <main class=\"grid\" id=\"gallery\"></main>

  <p class=\"hint\">
    This HTML contains pre-extracted UMAP traces. It can be opened directly from <span class=\"mono\">file://</span> without loading the source report HTMLs.
    (It still loads Plotly from the CDN.)
  </p>

  <script type=\"application/json\" id=\"gallery-data\">__PAYLOAD_JSON__</script>
  <script>
    const panels = JSON.parse(document.getElementById('gallery-data').textContent);
    const gallery = document.getElementById('gallery');
    const stats = document.getElementById('stats');

    function fmtFraction(x) {
      return Number(x).toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
    }

    function chip(text) {
      const el = document.createElement('span');
      el.textContent = text;
      return el;
    }

    function baseLayout() {
      return {
        height: 540,
        margin: { l: 20, r: 14, t: 54, b: 20 },
        hovermode: 'closest',
        plot_bgcolor: 'white',
        paper_bgcolor: 'white',
        showlegend: true,
        legend: { orientation: 'h', y: 1.02, yanchor: 'bottom', x: 0, font: { size: 11 } },
        xaxis: {
          zeroline: false,
          showticklabels: false,
          showgrid: false,
          showline: false,
          title: { text: 'UMAP 1' }
        },
        yaxis: {
          zeroline: false,
          showticklabels: false,
          showgrid: false,
          showline: false,
          title: { text: 'UMAP 2' }
        },
        title: { text: 'Samples', x: 0.5 },
      };
    }

    function setStats() {
      const runCount = new Set(panels.map(p => p.run_id)).size;
      const panelCount = panels.length;
      const totalPoints = panels.reduce((n, p) => n + (p.n_points || 0), 0);
      stats.replaceChildren(
        chip(`${runCount} runs`),
        chip(`${panelCount} panels`),
        chip(`${totalPoints.toLocaleString()} points`),
        chip('mode: Samples only'),
        chip('self-contained (report data baked in)')
      );
    }

    async function renderAll() {
      if (!window.Plotly) {
        console.error('Plotly failed to load');
        return;
      }
      setStats();

      const frag = document.createDocumentFragment();
      for (let i = 0; i < panels.length; i++) {
        const p = panels[i];
        const card = document.createElement('section');
        card.className = 'card';

        const head = document.createElement('div');
        head.className = 'card-head';
        const left = document.createElement('div');

        const runline = document.createElement('div');
        runline.className = 'runline';
        runline.textContent = `${p.run_id} (${p.sublib})`;

        const metaline = document.createElement('div');
        metaline.className = 'metaline';
        const refText = p.is_reference ? 'reference full depth • ' : '';
        metaline.textContent = `${refText}fraction=${fmtFraction(p.fraction)} • replicate=${p.replicate} • ${p.n_points.toLocaleString()} cells`;

        left.append(runline, metaline);

        const status = document.createElement('div');
        status.className = 'status';
        status.textContent = 'rendering';

        head.append(left, status);

        const wrap = document.createElement('div');
        wrap.className = 'plot-wrap';
        const host = document.createElement('div');
        host.className = 'plot-host';
        host.id = `plot-${i}`;
        wrap.append(host);

        card.append(head, wrap);
        frag.append(card);
      }
      gallery.replaceChildren(frag);

      for (let i = 0; i < panels.length; i++) {
        const p = panels[i];
        const host = document.getElementById(`plot-${i}`);
        const card = host.closest('.card');
        const status = card.querySelector('.status');
        const layout = baseLayout();
        try {
          await Plotly.newPlot(host, p.traces, layout, {
            displayModeBar: false,
            responsive: true,
            scrollZoom: false,
          });
          status.textContent = 'ready';
        } catch (err) {
          console.warn('plot render failed', p.run_id, p.sublib, err);
          status.textContent = 'render failed';
          host.textContent = 'Plotly render failed';
        }
      }
    }

    document.getElementById('single-col').addEventListener('click', () => {
      const oneCol = gallery.style.gridTemplateColumns === '1fr';
      gallery.style.gridTemplateColumns = oneCol ? '' : '1fr';
    });

    renderAll();
  </script>
</body>
</html>
"""
    return template.replace("__PAYLOAD_JSON__", payload_json)


def main() -> None:
    args = parse_args()
    grid_meta = load_grid(args.grid)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    entries = collect_entries(
        runs_dir=args.runs_dir,
        grid_meta=grid_meta,
        report_name=args.report_name,
        sublib_glob=args.sublib_glob,
        output_path=args.output,
    )
    if not entries:
        raise SystemExit(
            f"No reports found for pattern {args.sublib_glob}/{args.report_name} under {args.runs_dir}"
        )

    panels = build_panel_payload(entries, args.runs_dir, args.report_name)
    html = build_html(panels)
    args.output.write_text(html, encoding="utf-8")
    total_points = sum(p["n_points"] for p in panels)
    print(f"Wrote gallery: {args.output} ({len(panels)} panels, {total_points} points)")


if __name__ == "__main__":
    main()
