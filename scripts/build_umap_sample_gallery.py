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
import html as html_mod
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
SAMPLE_COLOR_MAP = {
    "xcond_1": "#1f77b4",
    "xcond_2": "#ff7f0e",
    "xcond_3": "#2ca02c",
}
SAMPLE_NAME_MAP = {
    "xcond_1": "K562",
    "xcond_2": "SK-N-SH",
    "xcond_3": "HEPG2",
}
DISPLAY_COLOR_MAP = {
    "K562": "#1f77b4",
    "SK-N-SH": "#ff7f0e",
    "HEPG2": "#2ca02c",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid", type=Path, default=Path("config/subsample_grid.tsv"))
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--output", type=Path, default=Path("figures/umap_sample_gallery.html"))
    p.add_argument(
        "--svg-output",
        type=Path,
        default=Path("figures/umap_sample_gallery.svg"),
        help="Static SVG export for publication/Illustrator (default: %(default)s)",
    )
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


def fmt_fraction(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


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

    grouped: "OrderedDict[str, tuple[list[float], list[float]]]" = OrderedDict()
    for x, y, sample in zip(xs, ys, samples):
        if sample not in grouped:
            grouped[sample] = ([], [])
        gx, gy = grouped[sample]
        gx.append(x)
        gy.append(y)

    traces: List[dict] = []
    for sample, (gx, gy) in grouped.items():
        display_name = SAMPLE_NAME_MAP.get(sample, sample)
        traces.append(
            {
                "type": "scattergl",
                "mode": "markers",
                "name": display_name,
                "x": gx,
                "y": gy,
                "marker": {"size": 3, "opacity": 0.85, "color": SAMPLE_COLOR_MAP.get(sample)},
                "hovertemplate": f"<b>{display_name}</b><extra></extra>",
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
      gap: 14px;
      align-items: start;
    }
    .matrix-scroll {
      overflow-x: auto;
      padding-bottom: 4px;
    }
    .matrix-grid {
      --rows-head: 92px;
      --rep-cols: 3;
      --cell-min: 520px;
      display: grid;
      gap: 12px;
      align-items: start;
      grid-template-columns: var(--rows-head) repeat(var(--rep-cols), minmax(var(--cell-min), 1fr));
      min-width: calc(var(--rows-head) + var(--rep-cols) * var(--cell-min) + (var(--rep-cols)) * 12px);
    }
    .matrix-colhead,
    .matrix-rowhead {
      border: 1px solid var(--line);
      border-radius: 10px;
      background: color-mix(in oklab, var(--panel) 82%, white);
      box-shadow: var(--shadow);
      color: var(--muted);
      font-size: 12px;
      display: grid;
      place-items: center;
      min-height: 52px;
      text-align: center;
      padding: 8px;
    }
    .matrix-colhead strong,
    .matrix-rowhead strong { color: var(--ink); font-size: 13px; }
    .matrix-corner {
      border: 1px dashed var(--line);
      border-radius: 10px;
      min-height: 52px;
      background: rgba(255,255,255,0.4);
    }
    .matrix-empty {
      border: 1px dashed var(--line);
      border-radius: 12px;
      background: rgba(255,255,255,0.65);
      min-height: 640px;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 12px;
      text-align: center;
      padding: 12px;
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
      const nonRef = panels.filter(p => !p.is_reference);
      const repCount = new Set(nonRef.map(p => p.replicate)).size;
      const fracCount = new Set(nonRef.map(p => String(p.fraction))).size;
      stats.replaceChildren(
        chip(`${runCount} runs`),
        chip(`${panelCount} panels`),
        chip(`${totalPoints.toLocaleString()} points`),
        chip(`${fracCount} fraction rows × ${repCount} replicate cols`),
        chip('mode: Samples only'),
        chip('self-contained (report data baked in)')
      );
    }

    function makePanelCard(p, i) {
      const card = document.createElement('section');
      card.className = 'card';

      const head = document.createElement('div');
      head.className = 'card-head';
      const left = document.createElement('div');

      const runline = document.createElement('div');
      runline.className = 'runline';
      runline.textContent = p.run_id;

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
      return card;
    }

    async function renderAll() {
      if (!window.Plotly) {
        console.error('Plotly failed to load');
        return;
      }
      setStats();

      const nonRefPanels = panels.filter(p => !p.is_reference);
      const refPanels = panels.filter(p => p.is_reference);
      const replicates = [...new Set(nonRefPanels.map(p => p.replicate))].sort((a, b) => a - b);
      const fractions = [...new Set(nonRefPanels.map(p => p.fraction))].sort((a, b) => a - b);
      const matrixByKey = new Map();
      for (let i = 0; i < panels.length; i++) {
        const p = panels[i];
        p.__idx = i;
        if (!p.is_reference) {
          const key = `${p.fraction}|${p.replicate}`;
          if (!matrixByKey.has(key)) {
            matrixByKey.set(key, p);
          }
        }
      }

      const frag = document.createDocumentFragment();

      if (refPanels.length) {
        const refSection = document.createElement('div');
        refSection.className = 'grid';
        refSection.style.gridTemplateColumns = `repeat(${Math.max(1, refPanels.length)}, minmax(680px, 1fr))`;
        for (const p of refPanels) {
          refSection.append(makePanelCard(p, p.__idx));
        }
        frag.append(refSection);
      }

      const matrixScroll = document.createElement('div');
      matrixScroll.className = 'matrix-scroll';
      const matrix = document.createElement('div');
      matrix.className = 'matrix-grid';
      matrix.style.setProperty('--rep-cols', String(Math.max(1, replicates.length)));

      const corner = document.createElement('div');
      corner.className = 'matrix-corner';
      matrix.append(corner);
      for (const rep of replicates) {
        const ch = document.createElement('div');
        ch.className = 'matrix-colhead';
        ch.innerHTML = `<div><strong>Replicate ${rep}</strong></div>`;
        matrix.append(ch);
      }

      for (const frac of fractions) {
        const rh = document.createElement('div');
        rh.className = 'matrix-rowhead';
        rh.innerHTML = `<div><strong>f = ${fmtFraction(frac)}</strong></div>`;
        matrix.append(rh);

        for (const rep of replicates) {
          const key = `${frac}|${rep}`;
          const p = matrixByKey.get(key);
          if (p) {
            matrix.append(makePanelCard(p, p.__idx));
          } else {
            const empty = document.createElement('div');
            empty.className = 'matrix-empty';
            empty.textContent = `No panel for fraction ${fmtFraction(frac)}, replicate ${rep}`;
            matrix.append(empty);
          }
        }
      }
      matrixScroll.append(matrix);
      frag.append(matrixScroll);
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

    renderAll();
  </script>
</body>
</html>
"""
    return template.replace("__PAYLOAD_JSON__", payload_json)


def _iter_panel_points(panels: Sequence[dict]):
    for panel in panels:
        for trace in panel.get("traces", []):
            for x, y in zip(trace.get("x", []), trace.get("y", [])):
                yield float(x), float(y)


def _global_square_bounds(panels: Sequence[dict]) -> tuple[float, float, float, float]:
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    seen = False
    for x, y in _iter_panel_points(panels):
        seen = True
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y
    if not seen:
        return (-1.0, 1.0, -1.0, 1.0)

    span_x = max_x - min_x
    span_y = max_y - min_y
    span = max(span_x, span_y, 1.0)
    pad = span * 0.04
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    half = (span / 2.0) + pad
    return (cx - half, cx + half, cy - half, cy + half)


def _svg_rect(
    x: float,
    y: float,
    w: float,
    h: float,
    klass: str = "",
    rx: float = 0.0,
    ry: float = 0.0,
) -> str:
    klass_attr = f' class="{klass}"' if klass else ""
    round_attr = f' rx="{rx:.2f}" ry="{ry:.2f}"' if (rx or ry) else ""
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"'
        f"{round_attr}{klass_attr} />"
    )


def _svg_text(x: float, y: float, text: str, klass: str = "", anchor: str = "start") -> str:
    klass_attr = f' class="{klass}"' if klass else ""
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}"{klass_attr}>'
        f"{html_mod.escape(text)}</text>"
    )


def _svg_panel(
    panel: dict,
    x0: float,
    y0: float,
    panel_w: float,
    panel_h: float,
    bounds: tuple[float, float, float, float],
    clip_id: str,
) -> str:
    header_h = 34.0
    pad = 10.0
    plot_x = x0 + pad
    plot_y = y0 + header_h + 6.0
    plot_w = panel_w - 2.0 * pad
    plot_h = panel_h - header_h - 6.0 - pad
    min_x, max_x, min_y, max_y = bounds
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    scale = min(plot_w / span_x, plot_h / span_y)
    used_w = span_x * scale
    used_h = span_y * scale
    x_off = plot_x + (plot_w - used_w) / 2.0
    y_off = plot_y + (plot_h - used_h) / 2.0

    parts: List[str] = []
    parts.append('<g class="panel">')
    parts.append(_svg_rect(x0, y0, panel_w, panel_h, "card", rx=10, ry=10))
    parts.append(_svg_rect(x0, y0, panel_w, header_h, "cardHead", rx=10, ry=10))
    parts.append(_svg_rect(x0, y0 + header_h - 10.0, panel_w, 10.0, "cardHeadFill"))
    parts.append(_svg_text(x0 + 10.0, y0 + 15.0, str(panel["run_id"]), "runline"))
    meta = (
        ("reference full depth | " if panel.get("is_reference") else "")
        + f"f={fmt_fraction(float(panel['fraction']))} | rep={panel['replicate']} | "
        + f"{int(panel['n_points']):,} cells"
    )
    parts.append(_svg_text(x0 + 10.0, y0 + 28.0, meta, "metaline"))

    parts.append(_svg_rect(plot_x, plot_y, plot_w, plot_h, "plotBg", rx=8, ry=8))
    parts.append(_svg_rect(plot_x, plot_y, plot_w, plot_h, "plotFrame", rx=8, ry=8))

    parts.append("<defs>")
    parts.append(
        f'<clipPath id="{clip_id}">'
        + _svg_rect(plot_x + 1.0, plot_y + 1.0, plot_w - 2.0, plot_h - 2.0, rx=7, ry=7)
        + "</clipPath>"
    )
    parts.append("</defs>")
    parts.append(f'<g clip-path="url(#{clip_id})">')
    for trace in panel.get("traces", []):
        color = trace.get("marker", {}).get("color") or DISPLAY_COLOR_MAP.get(trace.get("name", ""), "#666")
        parts.append(f'<g fill="{html_mod.escape(str(color))}" fill-opacity="0.45" stroke="none">')
        xs = trace.get("x", [])
        ys = trace.get("y", [])
        for x, y in zip(xs, ys):
            px = x_off + (float(x) - min_x) * scale
            py = y_off + (max_y - float(y)) * scale
            parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="0.95" />')
        parts.append("</g>")
    parts.append("</g>")
    parts.append("</g>")
    return "".join(parts)


def build_svg(panels: List[dict]) -> str:
    ref_panels = [p for p in panels if p.get("is_reference")]
    non_ref_panels = [p for p in panels if not p.get("is_reference")]
    replicates = sorted({int(p["replicate"]) for p in non_ref_panels})
    fractions = sorted({float(p["fraction"]) for p in non_ref_panels})
    panel_by_key = {(float(p["fraction"]), int(p["replicate"])): p for p in non_ref_panels}
    bounds = _global_square_bounds(panels)

    margin = 18.0
    top_h = 42.0
    legend_h = 28.0
    section_gap = 14.0
    gap = 10.0
    row_head_w = 88.0
    col_head_h = 34.0
    panel_w = 300.0
    panel_h = 300.0

    ref_label_h = 20.0 if ref_panels else 0.0
    ref_row_h = panel_h if ref_panels else 0.0
    ref_row_gap = 8.0 if ref_panels else 0.0
    ref_row_w = (len(ref_panels) * panel_w) + (max(0, len(ref_panels) - 1) * gap)

    matrix_w = row_head_w + (len(replicates) * panel_w) + (max(0, len(replicates) - 1) * gap)
    total_w = max(660.0, margin * 2.0 + max(matrix_w, (row_head_w + ref_row_w if ref_panels else 0.0)))
    matrix_h = col_head_h + (len(fractions) * panel_h) + (max(0, len(fractions) - 1) * gap)
    total_h = (
        margin
        + top_h
        + legend_h
        + section_gap
        + (ref_label_h + ref_row_h + ref_row_gap + section_gap if ref_panels else 0.0)
        + matrix_h
        + margin
    )

    parts: List[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(total_w)}" height="{int(total_h)}" '
        f'viewBox="0 0 {int(total_w)} {int(total_h)}">'
    )
    parts.append("<style><![CDATA[")
    parts.append("svg{background:#f4f0e8}")
    parts.append(".title{font:700 18px Georgia,'Times New Roman',serif;fill:#1f1c17}")
    parts.append(".subtitle{font:12px Georgia,'Times New Roman',serif;fill:#6f6658}")
    parts.append(".legendText,.footer{font:11px Georgia,'Times New Roman',serif;fill:#1f1c17}")
    parts.append(".footer{font-size:10px;fill:#6f6658}")
    parts.append(".sectionLabel,.colheadText,.rowheadText{font:700 12px Georgia,'Times New Roman',serif;fill:#1f1c17}")
    parts.append(".colhead,.rowhead{fill:#fffaf1;stroke:#d8cfbe;stroke-width:1}")
    parts.append(".card{fill:#fffaf1;stroke:#d8cfbe;stroke-width:1}")
    parts.append(".cardHead{fill:#f4ede0;stroke:#d8cfbe;stroke-width:1}")
    parts.append(".cardHeadFill{fill:#f4ede0;stroke:none}")
    parts.append(".runline{font:700 12px Georgia,'Times New Roman',serif;fill:#1f1c17}")
    parts.append(".metaline{font:11px Georgia,'Times New Roman',serif;fill:#6f6658}")
    parts.append(".plotBg{fill:#fff;stroke:none}")
    parts.append(".plotFrame{fill:none;stroke:#efe8da;stroke-width:1}")
    parts.append("]]></style>")

    y = margin
    parts.append(_svg_text(margin, y + 16.0, "UMAP Sample Gallery (SVG)", "title"))
    parts.append(
        _svg_text(
            margin,
            y + 31.0,
            "Rows = subsample fraction; columns = replicate; samples-only UMAPs (full point density).",
            "subtitle",
        )
    )
    y += top_h

    legend_y = y + 12.0
    lx = margin
    for name in ("K562", "SK-N-SH", "HEPG2"):
        color = DISPLAY_COLOR_MAP[name]
        parts.append(
            f'<circle cx="{lx + 4.0:.2f}" cy="{legend_y:.2f}" r="4" fill="{color}" fill-opacity="0.75" />'
        )
        parts.append(_svg_text(lx + 14.0, legend_y + 4.0, name, "legendText"))
        lx += 80.0 if name == "K562" else (110.0 if name == "SK-N-SH" else 90.0)
    y += legend_h + section_gap

    clip_counter = 0
    if ref_panels:
        parts.append(_svg_text(margin, y + 12.0, "Reference (full depth)", "sectionLabel"))
        y += ref_label_h
        ref_x = margin + row_head_w
        for i, panel in enumerate(ref_panels):
            clip_counter += 1
            x0 = ref_x + i * (panel_w + gap)
            parts.append(_svg_panel(panel, x0, y, panel_w, panel_h, bounds, f"umapclip{clip_counter}"))
        y += ref_row_h + ref_row_gap + section_gap

    matrix_x = margin
    matrix_y = y
    parts.append(_svg_rect(matrix_x, matrix_y, row_head_w, col_head_h, "colhead", rx=8, ry=8))
    parts.append(_svg_text(matrix_x + row_head_w / 2.0, matrix_y + 21.0, "f / rep", "subtitle", anchor="middle"))
    for c, rep in enumerate(replicates):
        xh = matrix_x + row_head_w + c * (panel_w + gap)
        parts.append(_svg_rect(xh, matrix_y, panel_w, col_head_h, "colhead", rx=8, ry=8))
        parts.append(
            _svg_text(xh + panel_w / 2.0, matrix_y + 21.0, f"Replicate {rep}", "colheadText", anchor="middle")
        )

    for r, frac in enumerate(fractions):
        yr = matrix_y + col_head_h + r * (panel_h + gap)
        parts.append(_svg_rect(matrix_x, yr, row_head_w, panel_h, "rowhead", rx=8, ry=8))
        parts.append(
            _svg_text(matrix_x + row_head_w / 2.0, yr + 18.0, f"f = {fmt_fraction(frac)}", "rowheadText", anchor="middle")
        )
        for c, rep in enumerate(replicates):
            xp = matrix_x + row_head_w + c * (panel_w + gap)
            panel = panel_by_key.get((frac, rep))
            if panel is None:
                parts.append(_svg_rect(xp, yr, panel_w, panel_h, "card", rx=10, ry=10))
                parts.append(_svg_text(xp + panel_w / 2.0, yr + panel_h / 2.0, "missing", "metaline", anchor="middle"))
                continue
            clip_counter += 1
            parts.append(_svg_panel(panel, xp, yr, panel_w, panel_h, bounds, f"umapclip{clip_counter}"))

    parts.append(
        _svg_text(
            margin,
            total_h - 8.0,
            "Generated by scripts/build_umap_sample_gallery.py for Illustrator/publication import.",
            "footer",
        )
    )
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    args = parse_args()
    grid_meta = load_grid(args.grid)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.svg_output.parent.mkdir(parents=True, exist_ok=True)

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
    svg = build_svg(panels)
    args.svg_output.write_text(svg, encoding="utf-8")
    total_points = sum(p["n_points"] for p in panels)
    print(f"Wrote gallery HTML: {args.output} ({len(panels)} panels, {total_points} points)")
    print(f"Wrote gallery SVG: {args.svg_output} (full point density)")


if __name__ == "__main__":
    main()
