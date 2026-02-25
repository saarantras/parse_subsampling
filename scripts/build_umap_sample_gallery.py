#!/usr/bin/env python3
"""Build a single HTML gallery of split-pipe UMAP reports in 'Samples' view.

This generates an aggregate HTML document that embeds each split-pipe
`all-sample_analysis_summary.html` report in an iframe, labels it with run
metadata (fraction/replicate), and uses parent-page JavaScript to switch the
embedded report to the Clustering page and click the "Samples" UMAP view.

Notes:
- The generated page is best opened via a local HTTP server (same-origin iframe
  scripting is often blocked when opening with `file://` URLs).
- The page is intentionally heavy because each panel embeds a full split-pipe
  report.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


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
        grid_rows = {}
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
            # Keep lexical paths (do not resolve symlinks), so URLs stay under `runs/...`.
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
    # Reference first, then ascending fraction, then replicate, then sublib.
    return (0 if entry.is_reference else 1, entry.fraction, entry.replicate, entry.sublib)


def build_html(entries: List[GalleryEntry]) -> str:
    entries = sorted(entries, key=_sort_key)
    payload = [
        {
            "run_id": e.run_id,
            "sublib": e.sublib,
            "fraction": e.fraction,
            "replicate": e.replicate,
            "is_reference": e.is_reference,
            "src": e.src_rel,
        }
        for e in entries
    ]

    payload_json = json.dumps(payload, indent=2)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>UMAP Sample Gallery</title>
  <style>
    :root {{
      --bg: #f4f0e8;
      --panel: #fffaf1;
      --ink: #1f1c17;
      --muted: #6f6658;
      --line: #d8cfbe;
      --accent: #1f6f78;
      --shadow: 0 10px 24px rgba(40, 32, 18, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: Georgia, "Times New Roman", serif; }}
    body {{ padding: 20px; }}
    .topbar {{
      position: sticky; top: 0; z-index: 20;
      background: color-mix(in oklab, var(--bg) 88%, white);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
      margin-bottom: 16px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(6px);
    }}
    .title {{ font-size: 20px; font-weight: 700; margin: 0 0 4px; }}
    .subtitle {{ font-size: 13px; color: var(--muted); margin: 0; }}
    .stats {{ margin-top: 8px; font-size: 12px; color: var(--muted); display: flex; gap: 12px; flex-wrap: wrap; }}
    .actions {{ margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }}
    button {{
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 999px;
      padding: 6px 10px;
      cursor: pointer;
      font: inherit;
      font-size: 12px;
    }}
    button:hover {{ border-color: var(--accent); color: var(--accent); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(680px, 1fr));
      gap: 14px;
      align-items: start;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    .card-head {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: start;
      padding: 10px 12px 8px;
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(135deg, rgba(31,111,120,0.08), rgba(31,111,120,0) 45%),
        linear-gradient(0deg, rgba(255,255,255,0.7), rgba(255,255,255,0.7));
    }}
    .runline {{ font-size: 13px; font-weight: 700; }}
    .metaline {{ font-size: 12px; color: var(--muted); }}
    .status {{
      font-size: 11px;
      color: var(--muted);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      white-space: nowrap;
      align-self: center;
    }}
    .frame-wrap {{ padding: 0; background: #fff; }}
    iframe {{
      width: 100%;
      height: 700px;
      border: 0;
      display: block;
      background: white;
    }}
    .hint {{
      margin-top: 14px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.35;
    }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    @media (max-width: 760px) {{
      body {{ padding: 10px; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <section class="topbar">
    <h1 class="title">UMAP Sample Gallery</h1>
    <p class="subtitle">Embedded split-pipe reports auto-switched to Clustering → Samples. Each panel is labeled by subsample fraction and replicate.</p>
    <div class="stats" id="stats"></div>
    <div class="actions">
      <button id="reload-all" type="button">Re-apply UMAP View</button>
      <button id="single-col" type="button">Toggle Single Column</button>
    </div>
  </section>

  <main class="grid" id="gallery"></main>

  <p class="hint">
    If panels stay on the Summary page or show a cross-origin error, serve this repo over HTTP (for example:
    <span class="mono">python -m http.server</span> from the repo root) and open
    <span class="mono">/figures/umap_sample_gallery.html</span>.
  </p>

  <script type="application/json" id="gallery-data">{payload_json}</script>
  <script>
    const data = JSON.parse(document.getElementById("gallery-data").textContent);
    const gallery = document.getElementById("gallery");
    const stats = document.getElementById("stats");

    function fmtFraction(x) {{
      return Number(x).toFixed(3).replace(/0+$/, "").replace(/\\.$/, "");
    }}

    function buildCards() {{
      stats.innerHTML = "";
      const runCount = new Set(data.map(d => d.run_id)).size;
      const panelCount = data.length;
      stats.append(
        chip(`${{runCount}} runs`),
        chip(`${{panelCount}} panels`),
        chip(`report: all-sample_analysis_summary.html`)
      );

      const frag = document.createDocumentFragment();
      data.forEach((d, idx) => {{
        const card = document.createElement("section");
        card.className = "card";
        card.dataset.runId = d.run_id;
        card.dataset.sublib = d.sublib;

        const head = document.createElement("div");
        head.className = "card-head";
        const left = document.createElement("div");
        const runline = document.createElement("div");
        runline.className = "runline";
        runline.textContent = d.is_reference
          ? `${{d.run_id}} (${{
              d.sublib
            }})`
          : `${{d.run_id}} (${{d.sublib}})`;

        const metaline = document.createElement("div");
        metaline.className = "metaline";
        metaline.textContent = d.is_reference
          ? `reference full depth • fraction=${{fmtFraction(d.fraction)}} • replicate=${{d.replicate}}`
          : `fraction=${{fmtFraction(d.fraction)}} • replicate=${{d.replicate}}`;
        left.append(runline, metaline);

        const status = document.createElement("div");
        status.className = "status";
        status.textContent = "loading";
        status.id = `status-${{idx}}`;

        head.append(left, status);

        const wrap = document.createElement("div");
        wrap.className = "frame-wrap";
        const iframe = document.createElement("iframe");
        iframe.loading = "lazy";
        iframe.src = d.src;
        iframe.dataset.statusId = status.id;
        iframe.dataset.index = String(idx);
        iframe.title = `UMAP samples view: ${{d.run_id}} ${{d.sublib}}`;
        iframe.addEventListener("load", () => {{
          status.textContent = "loaded; applying view";
          scheduleApply(iframe, 0);
          // Re-apply after Plotly scripts finish in the embedded page.
          [250, 800, 1800, 3500].forEach(ms => setTimeout(() => scheduleApply(iframe, 0), ms));
        }});
        wrap.appendChild(iframe);

        card.append(head, wrap);
        frag.appendChild(card);
      }});
      gallery.replaceChildren(frag);
    }}

    function chip(text) {{
      const el = document.createElement("span");
      el.textContent = text;
      return el;
    }}

    function statusEl(frame) {{
      return document.getElementById(frame.dataset.statusId);
    }}

    function setStatus(frame, msg) {{
      const el = statusEl(frame);
      if (el) el.textContent = msg;
    }}

    function injectIframeStyle(doc) {{
      if (doc.getElementById("codex-umap-gallery-style")) return;
      const style = doc.createElement("style");
      style.id = "codex-umap-gallery-style";
      style.textContent = `
        html, body {{
          margin: 0 !important;
          padding: 0 !important;
          background: #fff !important;
          overflow: hidden !important;
        }}
        nav, footer, #Page1, #Page3, #Page4 {{
          display: none !important;
        }}
        #Page2 {{
          display: block !important;
          margin: 0 !important;
          padding: 0 !important;
        }}
        #Page2 > nav {{
          display: none !important;
        }}
        #Page2 > .container {{
          width: auto !important;
          margin: 0 !important;
          padding: 0 !important;
        }}
        #filter-col {{
          display: none !important;
        }}
        #Page2 #plotly-parent-div {{
          float: none !important;
          width: 100% !important;
          max-width: none !important;
          margin: 0 !important;
          padding: 0 !important;
        }}
        #Page2 #plotly-parent-div > div:first-child {{
          display: none !important;
        }}
        #Page2 #plotly-parent-div .container {{
          width: auto !important;
          margin: 0 !important;
          padding: 0 !important;
          box-shadow: none !important;
          border: 0 !important;
        }}
        #Page2 #plotly-child-div {{
          margin: 0 !important;
          padding: 8px 8px 0 8px !important;
        }}
        #Page2 #plotly-tabs {{
          margin-bottom: 6px !important;
        }}
        #Page2 #pg2-plotly-umap {{
          margin: 0 auto !important;
        }}
      `;
      doc.head.appendChild(style);
    }}

    function clickSafe(el) {{
      if (!el) return false;
      try {{
        el.click();
        return true;
      }} catch {{
        return false;
      }}
    }}

    function fitFrameToPlot(frame, doc) {{
      const root = doc.getElementById("plotly-parent-div") || doc.getElementById("pg2-plotly-umap") || doc.body;
      if (!root) return;
      const rect = root.getBoundingClientRect();
      if (rect && rect.height > 100) {{
        const target = Math.ceil(rect.height + 8);
        frame.style.height = `${{Math.max(580, Math.min(target, 1200))}}px`;
      }}
    }}

    function scheduleApply(frame, tries) {{
      try {{
        const win = frame.contentWindow;
        const doc = frame.contentDocument || (win && win.document);
        if (!win || !doc) {{
          setStatus(frame, "waiting for iframe document");
          if (tries < 8) setTimeout(() => scheduleApply(frame, tries + 1), 300);
          return;
        }}

        injectIframeStyle(doc);

        if (typeof win.show_page === "function") {{
          win.show_page("Page2");
        }}

        const sampleBtn = doc.getElementById("pg2-plotly-sample-btn");
        const clusterBtn = doc.getElementById("pg2-plotly-cluster-btn");
        const umap = doc.getElementById("pg2-plotly-umap");

        // Ensure UMAP exists and plot is initialized before switching.
        if (!umap) {{
          setStatus(frame, "UMAP container not found");
          if (tries < 8) setTimeout(() => scheduleApply(frame, tries + 1), 400);
          return;
        }}

        // Cluster first (idempotent), then sample; split-pipe initializes on cluster.
        clickSafe(clusterBtn);
        clickSafe(sampleBtn);

        fitFrameToPlot(frame, doc);

        const title = umap.querySelector(".gtitle");
        const looksLikeSample = !!title && /sample/i.test(title.textContent || "");
        setStatus(frame, looksLikeSample ? "Samples view ready" : "view applied");

        if (!looksLikeSample && tries < 6) {{
          setTimeout(() => scheduleApply(frame, tries + 1), 500);
        }}
      }} catch (err) {{
        setStatus(frame, "cross-origin blocked; use local http server");
        console.warn("iframe control failed", frame.src, err);
      }}
    }}

    document.getElementById("reload-all").addEventListener("click", () => {{
      document.querySelectorAll("iframe").forEach((frame) => scheduleApply(frame, 0));
    }});

    document.getElementById("single-col").addEventListener("click", () => {{
      const grid = document.getElementById("gallery");
      const oneCol = grid.style.gridTemplateColumns === "1fr";
      grid.style.gridTemplateColumns = oneCol ? "" : "1fr";
    }});

    buildCards();
  </script>
</body>
</html>
"""


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
    html = build_html(entries)
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote gallery: {args.output} ({len(entries)} panels)")


if __name__ == "__main__":
    main()
