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

    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>UMAP Sample Gallery</title>
  <script src="https://cdn.plot.ly/plotly-3.1.0.min.js"></script>
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
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: Georgia, "Times New Roman", serif; }
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
    .plot-placeholder {
      height: 560px;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 12px;
    }
    #worker-frame {
      position: fixed;
      width: 1px;
      height: 1px;
      left: -9999px;
      top: -9999px;
      border: 0;
      opacity: 0;
      pointer-events: none;
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
      .plot-host, .plot-placeholder { min-height: 480px; height: 480px; }
    }
  </style>
</head>
<body>
  <section class="topbar">
    <h1 class="title">UMAP Sample Gallery</h1>
    <p class="subtitle">Standalone UMAP plots extracted from split-pipe reports (Clustering → Samples only). Each panel is labeled by subsample fraction and replicate.</p>
    <div class="stats" id="stats"></div>
    <div class="actions">
      <button id="reload-all" type="button">Rebuild All Panels</button>
      <button id="single-col" type="button">Toggle Single Column</button>
    </div>
  </section>

  <main class="grid" id="gallery"></main>
  <iframe id="worker-frame" title="umap-worker"></iframe>

  <p class="hint">
    This page extracts UMAP traces from each source report and re-renders them here. It still needs same-origin access to the report HTMLs:
    serve the repo over HTTP (for example <span class="mono">python3 -m http.server</span> from repo root) and open
    <span class="mono">/figures/umap_sample_gallery.html</span>.
  </p>

  <script type="application/json" id="gallery-data">__PAYLOAD_JSON__</script>
  <script>
    const data = JSON.parse(document.getElementById("gallery-data").textContent);
    const gallery = document.getElementById("gallery");
    const stats = document.getElementById("stats");
    const workerFrame = document.getElementById("worker-frame");

    let queue = [];
    let queuePos = 0;
    let activeIdx = null;
    let workerBusy = false;

    function fmtFraction(x) {
      return Number(x).toFixed(3).replace(/0+$/, "").replace(/\\.$/, "");
    }

    function chip(text) {
      const el = document.createElement("span");
      el.textContent = text;
      return el;
    }

    function setStats() {
      stats.innerHTML = "";
      const runCount = new Set(data.map(d => d.run_id)).size;
      const panelCount = data.length;
      stats.append(
        chip(`${runCount} runs`),
        chip(`${panelCount} panels`),
        chip(`mode: extracted UMAP (Samples)`),
        chip(`source: all-sample_analysis_summary.html`)
      );
    }

    function statusByIdx(idx) {
      return document.getElementById(`status-${idx}`);
    }

    function hostByIdx(idx) {
      return document.getElementById(`plot-${idx}`);
    }

    function setStatus(idx, text) {
      const el = statusByIdx(idx);
      if (el) el.textContent = text;
    }

    function buildCards() {
      setStats();
      const frag = document.createDocumentFragment();
      data.forEach((d, idx) => {
        const card = document.createElement("section");
        card.className = "card";
        card.dataset.runId = d.run_id;
        card.dataset.sublib = d.sublib;

        const head = document.createElement("div");
        head.className = "card-head";
        const left = document.createElement("div");

        const runline = document.createElement("div");
        runline.className = "runline";
        runline.textContent = `${d.run_id} (${d.sublib})`;

        const metaline = document.createElement("div");
        metaline.className = "metaline";
        metaline.textContent = d.is_reference
          ? `reference full depth • fraction=${fmtFraction(d.fraction)} • replicate=${d.replicate}`
          : `fraction=${fmtFraction(d.fraction)} • replicate=${d.replicate}`;
        left.append(runline, metaline);

        const status = document.createElement("div");
        status.className = "status";
        status.id = `status-${idx}`;
        status.textContent = "queued";

        head.append(left, status);

        const wrap = document.createElement("div");
        wrap.className = "plot-wrap";
        const host = document.createElement("div");
        host.className = "plot-host";
        host.id = `plot-${idx}`;
        const ph = document.createElement("div");
        ph.className = "plot-placeholder";
        ph.textContent = "Waiting to extract UMAP…";
        host.appendChild(ph);
        wrap.appendChild(host);

        card.append(head, wrap);
        frag.appendChild(card);
      });
      gallery.replaceChildren(frag);
    }

    function resetQueue() {
      queue = data.map((_, idx) => idx);
      queuePos = 0;
      activeIdx = null;
      workerBusy = false;
      for (const idx of queue) {
        setStatus(idx, "queued");
        const host = hostByIdx(idx);
        if (!host) continue;
        if (window.Plotly && host.classList.contains("js-plotly-plot")) {
          Plotly.purge(host);
        } else if (window.Plotly && host.querySelector(".js-plotly-plot")) {
          const nested = host.querySelector(".js-plotly-plot");
          Plotly.purge(nested);
        }
        host.innerHTML = '<div class="plot-placeholder">Waiting to extract UMAP…</div>';
      }
    }

    function startQueue() {
      if (!window.Plotly) {
        console.error("Plotly failed to load");
        return;
      }
      pumpQueue();
    }

    function pumpQueue() {
      if (workerBusy) return;
      if (queuePos >= queue.length) return;

      activeIdx = queue[queuePos++];
      workerBusy = true;
      const entry = data[activeIdx];
      setStatus(activeIdx, "loading report");
      workerFrame.src = entry.src;
    }

    workerFrame.addEventListener("load", () => {
      if (activeIdx == null) return;
      tryExtract(activeIdx, 0);
    });

    function clickSafe(el) {
      if (!el) return false;
      try {
        el.click();
        return true;
      } catch (err) {
        console.warn("click failed", err);
        return false;
      }
    }

    function clonePlotState(gd) {
      const data = JSON.parse(JSON.stringify(gd.data || []));
      const layout = JSON.parse(JSON.stringify(gd.layout || {}));
      const config = {
        displayModeBar: false,
        responsive: true,
        scrollZoom: false,
      };
      if (!layout.margin) layout.margin = {};
      layout.autosize = true;
      delete layout.width;
      layout.height = 540;
      layout.margin.l = layout.margin.l ?? 20;
      layout.margin.r = layout.margin.r ?? 20;
      layout.margin.b = layout.margin.b ?? 20;
      layout.margin.t = layout.margin.t ?? 56;
      layout.title = { text: "Samples", x: 0.5 };
      layout.paper_bgcolor = "white";
      layout.plot_bgcolor = "white";
      return { data, layout, config };
    }

    function renderExtractedPlot(idx, state) {
      const host = hostByIdx(idx);
      if (!host) return Promise.reject(new Error("host missing"));
      host.innerHTML = "";
      return Plotly.newPlot(host, state.data, state.layout, state.config)
        .then(() => {
          setStatus(idx, "ready");
        });
    }

    function finishCurrent() {
      workerBusy = false;
      activeIdx = null;
      setTimeout(pumpQueue, 0);
    }

    function failCurrent(idx, message) {
      setStatus(idx, message);
      const host = hostByIdx(idx);
      if (host && !host.querySelector(".plot-placeholder")) {
        host.innerHTML = `<div class="plot-placeholder">${message}</div>`;
      }
      finishCurrent();
    }

    function tryExtract(idx, tries) {
      const entry = data[idx];
      try {
        const win = workerFrame.contentWindow;
        const doc = workerFrame.contentDocument || (win && win.document);
        if (!win || !doc) {
          setStatus(idx, "waiting for report DOM");
          if (tries < 12) return setTimeout(() => tryExtract(idx, tries + 1), 250);
          return failCurrent(idx, "worker load timeout");
        }

        if (typeof win.show_page !== "function") {
          setStatus(idx, "waiting for report scripts");
          if (tries < 16) return setTimeout(() => tryExtract(idx, tries + 1), 250);
          return failCurrent(idx, "report JS not ready");
        }

        win.show_page("Page2");
        const clusterBtn = doc.getElementById("pg2-plotly-cluster-btn");
        const sampleBtn = doc.getElementById("pg2-plotly-sample-btn");
        const umap = doc.getElementById("pg2-plotly-umap");
        if (!umap || !clusterBtn || !sampleBtn) {
          setStatus(idx, "waiting for UMAP controls");
          if (tries < 16) return setTimeout(() => tryExtract(idx, tries + 1), 250);
          return failCurrent(idx, "UMAP controls not found");
        }

        clickSafe(clusterBtn);
        if (typeof win.cur_cmap_focus !== "undefined") {
          win.cur_cmap_focus = "sample";
        }
        clickSafe(sampleBtn);
        if (typeof win.update_umap_plot === "function") {
          try { win.update_umap_plot(); } catch (e) { /* ignore */ }
        }

        const hasData = Array.isArray(umap.data) && umap.data.length > 0;
        const titleText =
          (umap.layout && umap.layout.title && umap.layout.title.text) ||
          (umap.querySelector(".gtitle") && umap.querySelector(".gtitle").textContent) ||
          "";
        const sampleReady = /sample/i.test(String(titleText));

        if (!hasData || !sampleReady) {
          setStatus(idx, !hasData ? "waiting for Plotly traces" : "switching to Samples");
          if (tries < 20) return setTimeout(() => tryExtract(idx, tries + 1), 300);
          if (!hasData) return failCurrent(idx, "no UMAP traces");
        }

        setStatus(idx, "extracting traces");
        const state = clonePlotState(umap);
        renderExtractedPlot(idx, state)
          .catch((err) => {
            console.warn("plot render failed", entry.src, err);
            failCurrent(idx, "Plotly render failed");
          })
          .finally(() => {
            if (activeIdx === idx) finishCurrent();
          });
      } catch (err) {
        console.warn("extract failed", entry.src, err);
        failCurrent(idx, "cross-origin blocked; use local http server");
      }
    }

    document.getElementById("reload-all").addEventListener("click", () => {
      resetQueue();
      startQueue();
    });

    document.getElementById("single-col").addEventListener("click", () => {
      const oneCol = gallery.style.gridTemplateColumns === "1fr";
      gallery.style.gridTemplateColumns = oneCol ? "" : "1fr";
    });

    buildCards();
    resetQueue();
    startQueue();
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
    html = build_html(entries)
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote gallery: {args.output} ({len(entries)} panels)")


if __name__ == "__main__":
    main()
