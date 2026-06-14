"""
ui_server.py — Parametric 3D Printing Companion UI Server
==========================================================

A Flask-based companion server that provides a real-time browser UI while
Claude is designing a 3D-printable object via the parametric-3d-printing skill.

Usage
-----
    python3 ui_server.py                          # port 7384, current directory
    python3 ui_server.py --port 8080              # custom port
    python3 ui_server.py --dir /path/to/project   # custom working directory
    python3 ui_server.py --no-browser             # skip auto-opening browser

How it works
------------
1. On startup the server begins watching the working directory for changes to
   *.stl, *_preview.png, and ui_state.json every 400 ms.
2. Changes are broadcast to all connected browser clients via Server-Sent Events.
3. The browser renders the latest STL in a Three.js 3D viewer, displays preview
   images, and shows Claude's current phase / parameters / slicer stats.

ui_state.json schema (written by Claude)
-----------------------------------------
{
  "phase": "Phase 2 — Features",
  "phase_id": "phase2",
  "object": "Arduino Uno enclosure",
  "material": "PETG",
  "printer": "Bambu X1C",
  "message": "Adding M3 heat insert holes on the base corners...",
  "parameters": { "width": 80.0, "depth": 65.0, "height": 30.0, "wall": 2.0 },
  "slicer_report": { "time": "3h 40m", "filament_g": "31",
                     "support_pct": 0.0, "layers": 184 }
}
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import time
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, Response, jsonify, render_template_string, send_from_directory

# ---------------------------------------------------------------------------
# Embedded single-page application
# ---------------------------------------------------------------------------

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>3D Design — Live Preview</title>

<!-- Three.js r128 (global build) -->
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>

<style>
/* ── Reset & base ─────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:        #0d0d14;
  --bg2:       #13131f;
  --bg3:       #1a1a2a;
  --border:    #252538;
  --accent:    #3d8ef8;
  --accent2:   #6ab0ff;
  --text:      #e4e4f0;
  --text-dim:  #7878a0;
  --text-dimmer: #44445a;
  --green:     #2ecc71;
  --amber:     #f39c12;
  --red:       #e74c3c;
  --sidebar-w: 260px;
  --header-h:  48px;
}
html, body { height: 100%; overflow: hidden; font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); font-size: 13px; }

/* ── Scrollbar ────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg2); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* ── Layout ───────────────────────────────────────────────────────────── */
#app { display: flex; flex-direction: column; height: 100vh; }

/* ── Header ───────────────────────────────────────────────────────────── */
#header {
  height: var(--header-h);
  min-height: var(--header-h);
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  overflow: hidden;
}
#logo { display: flex; align-items: baseline; gap: 0; font-size: 16px; font-weight: 700; letter-spacing: -0.3px; flex-shrink: 0; }
#logo .logo-3d { color: #fff; }
#logo .logo-design { color: var(--accent); }
#header-sep { width: 1px; height: 20px; background: var(--border); flex-shrink: 0; }
#obj-name { font-size: 13px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 240px; }
#header-chips { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
.chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 12px;
  font-size: 11px; font-weight: 600; letter-spacing: 0.3px;
  border: 1px solid var(--border);
  background: var(--bg3); color: var(--text-dim);
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}
.chip.active { background: rgba(61,142,248,0.15); color: var(--accent2); border-color: rgba(61,142,248,0.4); }
#status-dot {
  width: 10px; height: 10px; border-radius: 50%;
  background: #555; flex-shrink: 0;
  transition: background 0.4s;
  margin-left: auto;
}
#status-dot.connected { background: var(--green); box-shadow: 0 0 6px var(--green); }
#status-dot.working {
  background: var(--amber);
  animation: pulse-dot 1.4s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 4px var(--amber); }
  50% { box-shadow: 0 0 12px var(--amber), 0 0 20px rgba(243,156,18,0.4); }
}

/* ── Body row ─────────────────────────────────────────────────────────── */
#body-row { display: flex; flex: 1; overflow: hidden; }

/* ── Sidebar ──────────────────────────────────────────────────────────── */
#sidebar {
  width: var(--sidebar-w);
  min-width: var(--sidebar-w);
  background: var(--bg2);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
}
.sb-section { padding: 12px 14px; border-bottom: 1px solid var(--border); }
.sb-title { font-size: 10px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--text-dim); margin-bottom: 10px; }

/* Progress steps */
#steps-list { display: flex; flex-direction: column; gap: 4px; }
.step { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
.step-circle {
  width: 20px; height: 20px; border-radius: 50%;
  border: 2px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 700; color: var(--text-dimmer);
  flex-shrink: 0; transition: all 0.3s;
}
.step.done .step-circle {
  background: var(--accent); border-color: var(--accent); color: #fff;
}
.step.active .step-circle {
  border-color: var(--accent); color: var(--accent);
  box-shadow: 0 0 8px rgba(61,142,248,0.5);
}
.step-label { font-size: 11.5px; color: var(--text-dim); transition: color 0.3s; }
.step.done .step-label { color: var(--text); }
.step.active .step-label { color: var(--accent2); font-weight: 600; }

/* Parameters */
#params-table { font-family: 'Cascadia Code', 'Fira Code', 'Courier New', monospace; font-size: 11px; width: 100%; }
#params-table td { padding: 1px 0; }
#params-table td:first-child { color: var(--text-dim); padding-right: 8px; white-space: nowrap; }
#params-table td:last-child { color: var(--accent); text-align: right; }
#params-empty { color: var(--text-dimmer); font-size: 11px; font-style: italic; }

/* Slicer report */
#slicer-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.slicer-card {
  background: var(--bg3); border: 1px solid var(--border);
  border-radius: 6px; padding: 6px 8px;
}
.slicer-label { font-size: 10px; color: var(--text-dimmer); margin-bottom: 2px; }
.slicer-value { font-size: 13px; font-weight: 600; color: var(--text); }
.slicer-value.green { color: var(--green); }
.slicer-value.amber { color: var(--amber); }
.slicer-value.red { color: var(--red); }
#slicer-empty { color: var(--text-dimmer); font-size: 11px; font-style: italic; }

/* Status message */
#status-msg { font-size: 11.5px; font-style: italic; color: var(--text-dim); line-height: 1.5; }

/* ── Main ─────────────────────────────────────────────────────────────── */
#main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }

/* ── Tabs ─────────────────────────────────────────────────────────────── */
#tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); background: var(--bg2); flex-shrink: 0; }
.tab-btn {
  padding: 0 20px; height: 38px; line-height: 38px;
  font-size: 12.5px; font-weight: 600; color: var(--text-dim);
  cursor: pointer; border: none; background: none;
  border-bottom: 2px solid transparent;
  transition: color 0.2s, border-color 0.2s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }

#tab-panels { flex: 1; position: relative; overflow: hidden; }
.tab-panel { position: absolute; inset: 0; display: none; }
.tab-panel.active { display: flex; flex-direction: column; }

/* ── 3D viewer ────────────────────────────────────────────────────────── */
#viewer-wrap { flex: 1; position: relative; background: #0a0a0f; overflow: hidden; }
#three-canvas { display: block; width: 100% !important; height: 100% !important; }
#viewer-hint {
  position: absolute; bottom: 10px; left: 12px;
  font-size: 11px; color: var(--text-dimmer); pointer-events: none;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
}
#viewer-controls {
  position: absolute; bottom: 10px; right: 12px;
  display: flex; gap: 6px;
}
.viewer-btn {
  background: rgba(19,19,31,0.85); border: 1px solid var(--border);
  color: var(--text-dim); font-size: 11px; padding: 4px 10px;
  border-radius: 5px; cursor: pointer; transition: background 0.2s, color 0.2s;
}
.viewer-btn:hover { background: var(--bg3); color: var(--text); }
.viewer-btn.active { background: rgba(61,142,248,0.2); color: var(--accent); border-color: var(--accent); }
#stl-filename {
  position: absolute; top: 10px; left: 12px;
  font-size: 11px; font-family: 'Cascadia Code', 'Fira Code', monospace;
  color: var(--text-dim); pointer-events: none;
  background: rgba(13,13,20,0.7); padding: 2px 6px; border-radius: 4px;
}
#viewer-placeholder {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
  color: var(--text-dimmer);
}
#viewer-placeholder svg { opacity: 0.3; }
#viewer-placeholder p { font-size: 13px; }

/* ── Preview tab ──────────────────────────────────────────────────────── */
#preview-panel { overflow-y: auto; padding: 16px; gap: 20px; flex-direction: column; }
.preview-item { display: flex; flex-direction: column; gap: 6px; }
.preview-label { font-size: 11px; color: var(--text-dim); font-family: monospace; }
.preview-img {
  max-width: 100%; border-radius: 6px;
  border: 1px solid var(--border);
}
#preview-empty { color: var(--text-dimmer); font-size: 13px; font-style: italic; margin: auto; }

/* ── Files tab ────────────────────────────────────────────────────────── */
#files-panel { overflow-y: auto; padding: 12px; flex-direction: column; gap: 4px; }
.file-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; border-radius: 6px; cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}
.file-row:hover { background: var(--bg3); border-color: var(--border); }
.file-hex { flex-shrink: 0; }
.file-name { font-family: monospace; font-size: 12px; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge-latest {
  background: rgba(61,142,248,0.2); color: var(--accent);
  font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 10px;
  border: 1px solid rgba(61,142,248,0.4); flex-shrink: 0;
}
#files-empty { color: var(--text-dimmer); font-size: 13px; font-style: italic; margin: auto; }
</style>
</head>
<body>
<div id="app">

  <!-- Header -->
  <header id="header">
    <div id="logo"><span class="logo-3d">3D</span><span class="logo-design">Design</span></div>
    <div id="header-sep"></div>
    <div id="obj-name">—</div>
    <div id="header-chips">
      <span class="chip" id="chip-material">Material</span>
      <span class="chip" id="chip-printer">Printer</span>
    </div>
    <div id="status-dot"></div>
  </header>

  <div id="body-row">

    <!-- Sidebar -->
    <aside id="sidebar">
      <!-- Progress -->
      <div class="sb-section">
        <div class="sb-title">Progress</div>
        <div id="steps-list"></div>
      </div>
      <!-- Parameters -->
      <div class="sb-section">
        <div class="sb-title">Parameters</div>
        <table id="params-table"><tbody></tbody></table>
        <div id="params-empty" style="display:none">No parameters yet</div>
      </div>
      <!-- Slicer Report -->
      <div class="sb-section">
        <div class="sb-title">Slicer Report</div>
        <div id="slicer-grid" style="display:none"></div>
        <div id="slicer-empty">Not yet run</div>
      </div>
      <!-- Status -->
      <div class="sb-section" style="border-bottom:none">
        <div class="sb-title">Status</div>
        <div id="status-msg">Waiting for Claude…</div>
      </div>
    </aside>

    <!-- Main -->
    <main id="main">
      <div id="tabs">
        <button class="tab-btn active" data-tab="viewer">3D Model</button>
        <button class="tab-btn" data-tab="preview">Preview</button>
        <button class="tab-btn" data-tab="files">Files</button>
      </div>
      <div id="tab-panels">

        <!-- 3D viewer -->
        <div id="panel-viewer" class="tab-panel active">
          <div id="viewer-wrap">
            <canvas id="three-canvas"></canvas>
            <div id="viewer-placeholder">
              <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M32 4L60 20V44L32 60L4 44V20L32 4Z" stroke="#7878a0" stroke-width="2" fill="none"/>
                <path d="M32 4L32 60" stroke="#7878a0" stroke-width="1.5" stroke-dasharray="4 3"/>
                <path d="M4 20L60 20" stroke="#7878a0" stroke-width="1.5" stroke-dasharray="4 3"/>
                <path d="M4 44L60 44" stroke="#7878a0" stroke-width="1.5" stroke-dasharray="4 3"/>
              </svg>
              <p>Waiting for first STL export…</p>
            </div>
            <div id="stl-filename" style="display:none"></div>
            <div id="viewer-hint">Drag to rotate · Scroll to zoom · Right-drag to pan</div>
            <div id="viewer-controls">
              <button class="viewer-btn" id="btn-reset">Reset view</button>
              <button class="viewer-btn" id="btn-wire">Wireframe</button>
            </div>
          </div>
        </div>

        <!-- Preview -->
        <div id="panel-preview" class="tab-panel">
          <div id="preview-panel" class="tab-panel active" style="display:flex">
            <div id="preview-empty">No preview yet</div>
          </div>
        </div>

        <!-- Files -->
        <div id="panel-files" class="tab-panel">
          <div id="files-panel" class="tab-panel active" style="display:flex">
            <div id="files-empty">No STL files yet</div>
          </div>
        </div>

      </div><!-- /#tab-panels -->
    </main>

  </div><!-- /#body-row -->
</div><!-- /#app -->

<script>
// ═══════════════════════════════════════════════════════════════════════════
// Tab switching
// ═══════════════════════════════════════════════════════════════════════════
const tabBtns = document.querySelectorAll('.tab-btn');
const panels = { viewer: 'panel-viewer', preview: 'panel-preview', files: 'panel-files' };

function switchTab(name) {
  tabBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  Object.entries(panels).forEach(([k, id]) => {
    document.getElementById(id).classList.toggle('active', k === name);
  });
  if (name === 'viewer') resizeRenderer();
}

tabBtns.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));

// ═══════════════════════════════════════════════════════════════════════════
// Phase steps definition
// ═══════════════════════════════════════════════════════════════════════════
const PHASES = [
  { id: 'requirements', label: 'Requirements' },
  { id: 'search',       label: 'Repo Search' },
  { id: 'dimensions',   label: 'Dimensions' },
  { id: 'brief',        label: 'Design Brief' },
  { id: 'phase1',       label: 'Phase 1 — Base Shape' },
  { id: 'phase2',       label: 'Phase 2 — Features' },
  { id: 'structural',   label: 'Structural Check' },
  { id: 'phase3',       label: 'Phase 3 — Finish' },
  { id: 'slicer',       label: 'Slicer Verification' },
  { id: 'delivered',    label: 'Delivered' },
];
const PHASE_ORDER = PHASES.map(p => p.id);

// Build steps HTML
const stepsList = document.getElementById('steps-list');
PHASES.forEach((p, i) => {
  const div = document.createElement('div');
  div.className = 'step';
  div.id = 'step-' + p.id;
  div.innerHTML = `<div class="step-circle" id="circle-${p.id}">${i + 1}</div><div class="step-label">${p.label}</div>`;
  stepsList.appendChild(div);
});

function updateSteps(phaseId) {
  const activeIdx = PHASE_ORDER.indexOf(phaseId);
  PHASES.forEach((p, i) => {
    const step = document.getElementById('step-' + p.id);
    const circle = document.getElementById('circle-' + p.id);
    step.classList.remove('done', 'active');
    if (activeIdx < 0) return;
    if (i < activeIdx) {
      step.classList.add('done');
      circle.innerHTML = '✓';
    } else if (i === activeIdx) {
      step.classList.add('active');
      circle.innerHTML = i + 1;
    } else {
      circle.innerHTML = i + 1;
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// Header helpers
// ═══════════════════════════════════════════════════════════════════════════
const dot = document.getElementById('status-dot');

function setDot(state) {
  // state: 'disconnected' | 'connected' | 'working'
  dot.className = '';
  if (state === 'connected') dot.classList.add('connected');
  else if (state === 'working') dot.classList.add('working');
}

function updateHeader(state) {
  document.getElementById('obj-name').textContent = state.object || '—';
  const matChip = document.getElementById('chip-material');
  const prtChip = document.getElementById('chip-printer');
  matChip.textContent = state.material || 'Material';
  matChip.classList.toggle('active', !!state.material);
  prtChip.textContent = state.printer || 'Printer';
  prtChip.classList.toggle('active', !!state.printer);

  const phaseId = state.phase_id || '';
  const isWorking = phaseId && phaseId !== 'delivered';
  setDot(isWorking ? 'working' : 'connected');
}

// ═══════════════════════════════════════════════════════════════════════════
// Parameters
// ═══════════════════════════════════════════════════════════════════════════
function updateParams(params) {
  const tbody = document.querySelector('#params-table tbody');
  const empty = document.getElementById('params-empty');
  tbody.innerHTML = '';
  if (!params || Object.keys(params).length === 0) {
    document.getElementById('params-table').style.display = 'none';
    empty.style.display = '';
    return;
  }
  document.getElementById('params-table').style.display = '';
  empty.style.display = 'none';
  for (const [k, v] of Object.entries(params)) {
    const tr = document.createElement('tr');
    const val = typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : v;
    tr.innerHTML = `<td>${k}</td><td>${val}</td>`;
    tbody.appendChild(tr);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Slicer report
// ═══════════════════════════════════════════════════════════════════════════
function supportColor(pct) {
  if (pct === null || pct === undefined) return '';
  if (pct === 0) return 'green';
  if (pct < 25) return 'green';
  if (pct < 50) return 'amber';
  return 'red';
}

function updateSlicer(report) {
  const grid = document.getElementById('slicer-grid');
  const empty = document.getElementById('slicer-empty');
  if (!report) {
    grid.style.display = 'none';
    empty.style.display = '';
    return;
  }
  grid.style.display = 'grid';
  empty.style.display = 'none';
  const supPct = report.support_pct;
  const supColor = supportColor(supPct);
  const supText = supPct !== null && supPct !== undefined ? supPct + '%' : '—';
  grid.innerHTML = `
    <div class="slicer-card">
      <div class="slicer-label">Print time</div>
      <div class="slicer-value">${report.time || '—'}</div>
    </div>
    <div class="slicer-card">
      <div class="slicer-label">Filament (g)</div>
      <div class="slicer-value">${report.filament_g || '—'}</div>
    </div>
    <div class="slicer-card">
      <div class="slicer-label">Supports</div>
      <div class="slicer-value ${supColor}">${supText}</div>
    </div>
    <div class="slicer-card">
      <div class="slicer-label">Layers</div>
      <div class="slicer-value">${report.layers || '—'}</div>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════════════════
// Preview panel
// ═══════════════════════════════════════════════════════════════════════════
function updatePreviews(files) {
  const panel = document.getElementById('preview-panel');
  const empty = document.getElementById('preview-empty');
  panel.querySelectorAll('.preview-item').forEach(el => el.remove());
  if (!files || files.length === 0) {
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';
  const ts = Date.now();
  files.forEach(fname => {
    const item = document.createElement('div');
    item.className = 'preview-item';
    item.innerHTML = `
      <div class="preview-label">${fname}</div>
      <img class="preview-img" src="/file/${encodeURIComponent(fname)}?t=${ts}" alt="${fname}" />
    `;
    panel.appendChild(item);
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// Files panel
// ═══════════════════════════════════════════════════════════════════════════
function updateFiles(stlFiles) {
  const panel = document.getElementById('files-panel');
  const empty = document.getElementById('files-empty');
  panel.querySelectorAll('.file-row').forEach(el => el.remove());
  if (!stlFiles || stlFiles.length === 0) {
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';
  stlFiles.forEach((fname, idx) => {
    const row = document.createElement('div');
    row.className = 'file-row';
    row.innerHTML = `
      <svg class="file-hex" width="18" height="18" viewBox="0 0 18 18" fill="none">
        <path d="M9 1.5L15.5 5.25V12.75L9 16.5L2.5 12.75V5.25L9 1.5Z"
              fill="rgba(61,142,248,0.15)" stroke="#3d8ef8" stroke-width="1.2"/>
        <path d="M9 5L12 7V11L9 13L6 11V7L9 5Z" fill="#3d8ef8" opacity="0.5"/>
      </svg>
      <span class="file-name">${fname}</span>
      ${idx === 0 ? '<span class="badge-latest">latest</span>' : ''}
    `;
    row.addEventListener('click', () => {
      loadSTL(fname);
      switchTab('viewer');
    });
    panel.appendChild(row);
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// Three.js 3D viewer
// ═══════════════════════════════════════════════════════════════════════════
let scene, camera, renderer, controls, model, grid, axes;
let isWireframe = false;
let currentSTLFile = null;
let defaultCameraPos = null;

function initThree() {
  const canvas = document.getElementById('three-canvas');
  const wrap = document.getElementById('viewer-wrap');

  // Scene
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a0f);

  // Camera
  camera = new THREE.PerspectiveCamera(45, wrap.clientWidth / wrap.clientHeight, 0.1, 10000);
  camera.position.set(150, 120, 180);

  // Renderer
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(wrap.clientWidth, wrap.clientHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  // Controls
  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.screenSpacePanning = true;
  controls.mouseButtons = {
    LEFT: THREE.MOUSE.ROTATE,
    MIDDLE: THREE.MOUSE.DOLLY,
    RIGHT: THREE.MOUSE.PAN
  };

  // Lighting
  const ambient = new THREE.AmbientLight(0xb0c8ff, 0.35);
  scene.add(ambient);

  const key = new THREE.DirectionalLight(0xffffff, 1.2);
  key.position.set(80, 160, 100);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  scene.add(key);

  const fill = new THREE.DirectionalLight(0x5060ff, 0.4);
  fill.position.set(-100, 40, -80);
  scene.add(fill);

  const rim = new THREE.DirectionalLight(0xffaa44, 0.3);
  rim.position.set(0, -60, -120);
  scene.add(rim);

  // Grid
  grid = new THREE.GridHelper(400, 40, 0x1a1a2a, 0x1a1a2a);
  grid.material.opacity = 0.7;
  grid.material.transparent = true;
  scene.add(grid);

  // Axes
  axes = new THREE.AxesHelper(20);
  axes.position.y = 0.1;
  scene.add(axes);

  // Animate
  (function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  })();

  // Resize
  window.addEventListener('resize', resizeRenderer);
}

function resizeRenderer() {
  const wrap = document.getElementById('viewer-wrap');
  if (!wrap || !renderer) return;
  const w = wrap.clientWidth, h = wrap.clientHeight;
  if (w === 0 || h === 0) return;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}

function frameModel(mesh) {
  const box = new THREE.Box3().setFromObject(mesh);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  let dist = Math.abs(maxDim / Math.sin(fov / 2)) * 0.7;
  dist = Math.max(dist, maxDim * 1.5);
  camera.position.set(
    center.x + dist * 0.6,
    center.y + dist * 0.5,
    center.z + dist * 0.8
  );
  controls.target.copy(center);
  controls.update();
  defaultCameraPos = camera.position.clone();
}

function loadSTL(filename) {
  const placeholder = document.getElementById('viewer-placeholder');
  const fnLabel = document.getElementById('stl-filename');

  if (model) {
    scene.remove(model);
    model.geometry.dispose();
    model.material.dispose();
    model = null;
  }

  currentSTLFile = filename;
  fnLabel.textContent = filename;
  fnLabel.style.display = '';

  const loader = new THREE.STLLoader();
  loader.load(
    '/file/' + encodeURIComponent(filename),
    (geometry) => {
      geometry.computeVertexNormals();

      // Center on XZ, base at y=0
      geometry.computeBoundingBox();
      const box = geometry.boundingBox;
      const cx = (box.min.x + box.max.x) / 2;
      const cy = box.min.y;
      const cz = (box.min.z + box.max.z) / 2;
      geometry.translate(-cx, -cy, -cz);

      const mat = new THREE.MeshPhysicalMaterial({
        color: 0x3d8ef8,
        roughness: 0.4,
        metalness: 0.05,
        wireframe: isWireframe,
      });

      model = new THREE.Mesh(geometry, mat);
      model.castShadow = true;
      model.receiveShadow = true;
      scene.add(model);

      placeholder.style.display = 'none';
      frameModel(model);
    },
    undefined,
    (err) => {
      console.error('STL load error:', err);
    }
  );
}

// Viewer buttons
document.getElementById('btn-reset').addEventListener('click', () => {
  if (!model) return;
  frameModel(model);
});

document.getElementById('btn-wire').addEventListener('click', () => {
  isWireframe = !isWireframe;
  document.getElementById('btn-wire').classList.toggle('active', isWireframe);
  if (model) model.material.wireframe = isWireframe;
});

// ═══════════════════════════════════════════════════════════════════════════
// Main render function
// ═══════════════════════════════════════════════════════════════════════════
function renderState(state) {
  updateHeader(state);
  updateSteps(state.phase_id || '');
  updateParams(state.parameters || null);
  updateSlicer(state.slicer_report || null);
  document.getElementById('status-msg').textContent = state.message || 'Waiting for Claude…';

  const stlFiles = state._stl_files || [];
  const previewFiles = state._preview_files || [];

  // Auto-load new STL
  if (stlFiles.length > 0 && stlFiles[0] !== currentSTLFile) {
    loadSTL(stlFiles[0]);
    switchTab('viewer');
  }

  updatePreviews(previewFiles);
  updateFiles(stlFiles);
}

// ═══════════════════════════════════════════════════════════════════════════
// SSE connection
// ═══════════════════════════════════════════════════════════════════════════
let evtSource = null;

function connectSSE() {
  if (evtSource) { evtSource.close(); evtSource = null; }

  evtSource = new EventSource('/events');

  evtSource.addEventListener('open', () => {
    setDot('connected');
    // Fetch initial state
    fetch('/state')
      .then(r => r.json())
      .then(renderState)
      .catch(console.error);
  });

  evtSource.addEventListener('update', (e) => {
    try {
      const state = JSON.parse(e.data);
      renderState(state);
    } catch (err) {
      console.error('SSE parse error:', err);
    }
  });

  evtSource.addEventListener('error', () => {
    setDot('disconnected');
    evtSource.close();
    evtSource = null;
    setTimeout(connectSSE, 2000);
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════════════════
initThree();
connectSSE();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Global state (protected by _lock where applicable)
_lock = threading.Lock()
_subscribers: List[queue.Queue] = []
_last_mtimes: Dict[str, float] = {}
_work_dir: Path = Path.cwd()

# ---------------------------------------------------------------------------
# Watcher thread
# ---------------------------------------------------------------------------


def _scan_state(work_dir: Path) -> dict:
    """Read ui_state.json and augment with file listings from work_dir.

    Returns a dict ready to serialise as the current state.
    Handles missing files and JSON parse errors gracefully.
    """
    state: dict = {}

    state_file = work_dir / "ui_state.json"
    if state_file.exists():
        try:
            raw = state_file.read_text(encoding="utf-8")
            state = json.loads(raw)
        except (FileNotFoundError, json.JSONDecodeError):
            state = {}

    # STL files sorted by mtime descending
    stl_files: List[tuple] = []
    preview_files: List[tuple] = []
    try:
        for entry in work_dir.iterdir():
            if not entry.is_file():
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            name = entry.name
            if name.endswith(".stl"):
                stl_files.append((mtime, name))
            elif name.endswith("_preview.png") or name == "ceiling_map.png":
                preview_files.append((mtime, name))
    except FileNotFoundError:
        pass

    stl_files.sort(key=lambda x: x[0], reverse=True)
    preview_files.sort(key=lambda x: x[0], reverse=True)

    state["_stl_files"] = [n for _, n in stl_files]
    state["_preview_files"] = [n for _, n in preview_files]

    return state


def _get_watched_mtimes(work_dir: Path) -> Dict[str, float]:
    """Return a dict of {filename: mtime} for all watched files."""
    mtimes: Dict[str, float] = {}
    patterns = (".stl", "_preview.png", "ceiling_map.png", "ui_state.json")
    try:
        for entry in work_dir.iterdir():
            if not entry.is_file():
                continue
            name = entry.name
            if any(name.endswith(pat) or name == pat for pat in patterns):
                try:
                    mtimes[name] = entry.stat().st_mtime
                except OSError:
                    pass
    except FileNotFoundError:
        pass
    return mtimes


def _broadcast(state: dict) -> None:
    """Push a state update to all SSE subscribers."""
    payload = json.dumps(state, ensure_ascii=False)
    msg = f"event: update\ndata: {payload}\n\n"
    dead: List[queue.Queue] = []
    with _lock:
        for q in _subscribers:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _subscribers.remove(q)


def _watcher_loop(work_dir: Path, interval: float = 0.4) -> None:
    """Background thread: poll for file changes and broadcast state via SSE.

    Also emits an SSE heartbeat comment every 15 seconds to keep HTTP
    connections alive through proxies and load balancers.
    """
    last_heartbeat = time.monotonic()

    while True:
        time.sleep(interval)
        now = time.monotonic()

        # Check for file changes
        try:
            current = _get_watched_mtimes(work_dir)
        except Exception:
            current = {}

        changed = False
        with _lock:
            if current != _last_mtimes:
                _last_mtimes.clear()
                _last_mtimes.update(current)
                changed = True

        if changed:
            state = _scan_state(work_dir)
            _broadcast(state)

        # Heartbeat
        if now - last_heartbeat >= 15.0:
            last_heartbeat = now
            heartbeat = ": heartbeat\n\n"
            with _lock:
                dead = []
                for q in _subscribers:
                    try:
                        q.put_nowait(heartbeat)
                    except queue.Full:
                        dead.append(q)
                for q in dead:
                    _subscribers.remove(q)


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Serve the embedded single-page application."""
    return render_template_string(HTML)


@app.route("/state")
def state():
    """Return current state as JSON (used for initial page load)."""
    current_state = _scan_state(_work_dir)
    return jsonify(current_state)


@app.route("/events")
def events():
    """Server-Sent Events endpoint.

    Each subscriber gets a ``queue.Queue``; the watcher thread puts messages
    into every queue and this generator yields them to the HTTP response.
    """
    sub_q: queue.Queue = queue.Queue(maxsize=10)
    with _lock:
        _subscribers.append(sub_q)

    # Send the current state immediately so the client doesn't wait
    initial = _scan_state(_work_dir)
    payload = json.dumps(initial, ensure_ascii=False)
    first_msg = f"event: update\ndata: {payload}\n\n"

    def generate():
        yield first_msg
        while True:
            try:
                msg = sub_q.get(timeout=20)
                yield msg
            except queue.Empty:
                # Send a comment to keep the connection alive
                yield ": keepalive\n\n"

    def cleanup(q):
        with _lock:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass

    response = Response(
        generate(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
    # Register cleanup when the client disconnects
    response.call_on_close(lambda: cleanup(sub_q))
    return response


@app.route("/file/<path:filename>")
def serve_file(filename: str):
    """Serve an STL or PNG file from the working directory.

    Only plain filenames (no path traversal) are allowed.
    Returns 404 if the file does not exist or the name is unsafe.
    """
    # Safety: reject any path that contains directory separators
    if "/" in filename or "\\" in filename or ".." in filename:
        return ("Not found", 404)

    try:
        return send_from_directory(
            str(_work_dir),
            filename,
            as_attachment=False,
        )
    except FileNotFoundError:
        return ("Not found", 404)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Parametric 3D Printing companion UI server.\n\n"
            "Starts a local Flask server that watches the working directory for\n"
            "*.stl, *_preview.png, and ui_state.json changes and streams updates\n"
            "to a browser-based 3D viewer via Server-Sent Events."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7384,
        help="TCP port to listen on (default: 7384)",
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        metavar="PATH",
        help="Working directory to watch (default: current directory)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        default=False,
        help="Do not automatically open the browser on startup",
    )
    return parser.parse_args()


def _open_browser(url: str, delay: float = 0.5) -> None:
    """Open *url* in the default browser after *delay* seconds."""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)

    t = threading.Thread(target=_open, daemon=True)
    t.start()


def main() -> None:
    """Configure and start the UI server."""
    global _work_dir

    args = parse_args()

    # Resolve working directory
    if args.dir:
        _work_dir = Path(args.dir).resolve()
    else:
        _work_dir = Path.cwd()

    if not _work_dir.is_dir():
        print(f"[ui_server] ERROR: directory does not exist: {_work_dir}")
        raise SystemExit(1)

    url = f"http://127.0.0.1:{args.port}"
    print(f"[ui_server] Watching : {_work_dir}")
    print(f"[ui_server] Serving  : {url}")

    # Seed mtime cache
    with _lock:
        _last_mtimes.update(_get_watched_mtimes(_work_dir))

    # Start background watcher
    watcher = threading.Thread(
        target=_watcher_loop,
        args=(_work_dir,),
        daemon=True,
        name="ui-watcher",
    )
    watcher.start()

    # Auto-open browser (after 500 ms so Flask is ready)
    if not args.no_browser:
        _open_browser(url, delay=0.5)

    # Start Flask (suppress the default reloader so we don't double-spawn)
    app.run(
        host="127.0.0.1",
        port=args.port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
