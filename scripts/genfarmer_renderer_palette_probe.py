#!/usr/bin/env python3
"""Read-only GenFarmer Electron renderer palette probe via Chrome DevTools Protocol.

This tool connects to a GenFarmer instance launched with Chromium remote
debugging enabled (for example ``--remote-debugging-port=9222``). It does not
click, drag, create, edit, save, or run automation nodes.

The probe scrolls the left automation palette in the renderer, collects visible
palette labels, and inspects only privacy-safe DOM/Vue metadata for elements in
that palette region. It is intended to enumerate the complete node palette in a
single pass without copying arbitrary application state.

Output is written below ignored ``evidence/``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

try:
    import websocket  # type: ignore
except ImportError:  # pragma: no cover - exercised on fresh client install
    websocket = None


PROBE_JS = r"""
(async () => {
  const sleepFrame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const tokenRe = /^[A-Za-z0-9_.:/ -]{1,120}$/;
  const safeTerminalKeys = new Set(['action', 'type', 'nodeType', 'category', 'component', 'group', 'kind']);

  function visible(el) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) !== 0;
  }

  function cleanText(raw) {
    if (!raw) return '';
    return raw.replace(/\s+/g, ' ').trim();
  }

  function safePrimitive(value) {
    if (value === null || typeof value === 'boolean' || typeof value === 'number') return value;
    if (typeof value === 'string' && tokenRe.test(value)) return value;
    return undefined;
  }

  function shapeAndSemantics(value, prefix = '', depth = 0, seen = new WeakSet()) {
    const paths = [];
    const semantics = {};
    if (depth > 4) return {paths, semantics};
    if (value && typeof value === 'object') {
      if (seen.has(value)) return {paths, semantics};
      seen.add(value);
    }

    const typeName = v => {
      if (v === null) return 'null';
      if (Array.isArray(v)) return 'list';
      return typeof v === 'object' ? 'object' : typeof v;
    };

    if (Array.isArray(value)) {
      paths.push(`${prefix}:list`);
      for (const item of value.slice(0, 10)) {
        const child = shapeAndSemantics(item, `${prefix}[]`, depth + 1, seen);
        paths.push(...child.paths);
        Object.assign(semantics, child.semantics);
      }
      return {paths, semantics};
    }

    if (value && typeof value === 'object') {
      for (const key of Object.keys(value).slice(0, 120)) {
        let child;
        try { child = value[key]; } catch (_) { continue; }
        const path = prefix ? `${prefix}.${key}` : key;
        paths.push(`${path}:${typeName(child)}`);
        if (safeTerminalKeys.has(key)) {
          const sv = safePrimitive(child);
          if (sv !== undefined) semantics[path] = sv;
        }
        if (depth < 4 && child && (typeof child === 'object')) {
          const nested = shapeAndSemantics(child, path, depth + 1, seen);
          paths.push(...nested.paths);
          Object.assign(semantics, nested.semantics);
        }
      }
    }
    return {paths, semantics};
  }

  function vueMetadata(el) {
    const out = {component: null, prop_paths: [], safe_semantics: {}, setup_keys: []};
    let inst = null;
    try { inst = el.__vueParentComponent || null; } catch (_) {}
    if (!inst) return out;
    try {
      out.component = inst.type && (inst.type.name || inst.type.__name) || null;
    } catch (_) {}
    try {
      const shaped = shapeAndSemantics(inst.props || {}, 'props');
      out.prop_paths = [...new Set(shaped.paths)].sort().slice(0, 500);
      out.safe_semantics = shaped.semantics;
    } catch (_) {}
    try {
      if (inst.setupState && typeof inst.setupState === 'object') {
        out.setup_keys = Object.keys(inst.setupState).sort().slice(0, 200);
      }
    } catch (_) {}
    return out;
  }

  const searchInput = [...document.querySelectorAll('input')].find(el => {
    const p = (el.getAttribute('placeholder') || '').toLowerCase();
    return p.includes('search') && (p.includes('ctrl') || p.includes('find'));
  });
  const paletteTop = searchInput ? searchInput.getBoundingClientRect().bottom - 5 : Math.min(320, innerHeight * 0.35);
  const leftLimit = Math.min(430, innerWidth * 0.35);

  const all = [...document.querySelectorAll('*')];
  let scrollables = all.filter(el => {
    if (!visible(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.left >= leftLimit || r.right > leftLimit + 120 || r.bottom <= paletteTop) return false;
    const s = getComputedStyle(el);
    return el.scrollHeight > el.clientHeight + 40 && ['auto','scroll'].includes(s.overflowY);
  });

  scrollables.sort((a,b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
  const scroller = scrollables[0] || null;
  const originalTop = scroller ? scroller.scrollTop : 0;
  const records = new Map();

  function collect() {
    const candidates = [...document.querySelectorAll('[draggable="true"],button,[role="button"],a,div,span')];
    for (const el of candidates) {
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.left >= leftLimit || r.right > leftLimit + 100 || r.bottom <= paletteTop || r.top >= innerHeight) continue;
      const text = cleanText(el.innerText || el.textContent || '');
      if (!text || text.length > 90 || text.split(' ').length > 12) continue;

      const draggable = el.getAttribute('draggable') === 'true';
      const role = el.getAttribute('role');
      const tag = el.tagName.toLowerCase();
      const cls = [...el.classList].filter(x => tokenRe.test(x)).slice(0, 20);
      const data = {};
      for (const attr of [...el.attributes]) {
        if (!attr.name.startsWith('data-')) continue;
        if (tokenRe.test(attr.value || '')) data[attr.name] = attr.value;
        else data[attr.name] = '<redacted>';
      }
      const vue = vueMetadata(el);

      // Prefer actual draggable/button-ish palette records. Plain div/span text is
      // retained only when it looks like a section heading (short, uppercase).
      const headingLike = !draggable && !role && !['button','a'].includes(tag) && text.length <= 40 && text === text.toUpperCase();
      if (!draggable && !role && !['button','a'].includes(tag) && !headingLike && !vue.component) continue;

      const key = JSON.stringify([text, tag, role || '', draggable, vue.component || '', vue.safe_semantics]);
      if (!records.has(key)) {
        records.set(key, {
          text,
          tag,
          role,
          draggable,
          heading_like: headingLike,
          class_tokens: cls,
          data_attributes: data,
          vue,
        });
      }
    }
  }

  if (scroller) {
    const max = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
    const step = Math.max(120, Math.floor(scroller.clientHeight * 0.72));
    for (let y = 0; y <= max; y += step) {
      scroller.scrollTop = y;
      await sleepFrame();
      collect();
    }
    scroller.scrollTop = max;
    await sleepFrame();
    collect();
    scroller.scrollTop = originalTop;
    await sleepFrame();
  } else {
    collect();
  }

  const items = [...records.values()].sort((a,b) => a.text.localeCompare(b.text));
  const draggableLabels = [...new Set(items.filter(x => x.draggable).map(x => x.text))].sort();
  const headingLabels = [...new Set(items.filter(x => x.heading_like).map(x => x.text))].sort();

  return {
    probe_format: 1,
    viewport: {width: innerWidth, height: innerHeight},
    palette_anchor_found: !!searchInput,
    palette_top: Math.round(paletteTop),
    left_limit: Math.round(leftLimit),
    scrollable_candidates: scrollables.length,
    selected_scroller: scroller ? {
      clientHeight: scroller.clientHeight,
      scrollHeight: scroller.scrollHeight,
      tag: scroller.tagName.toLowerCase(),
      class_tokens: [...scroller.classList].filter(x => tokenRe.test(x)).slice(0, 20),
    } : null,
    draggable_labels: draggableLabels,
    heading_labels: headingLabels,
    records: items,
  };
})()
"""


def http_json(url: str, timeout: float = 4.0):
    req = urllib.request.Request(url, headers={"User-Agent": "genfarmer-renderer-probe/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def choose_target(targets: list[dict]) -> dict | None:
    pages = [t for t in targets if t.get("type") in {"page", "webview", "background_page"} and t.get("webSocketDebuggerUrl")]
    if not pages:
        return None
    for target in pages:
        title = str(target.get("title") or "").lower()
        url = str(target.get("url") or "").lower()
        if "genfarmer" in title or "genfarmer" in url:
            return target
    for target in pages:
        url = str(target.get("url") or "")
        if not url.startswith("devtools://"):
            return target
    return pages[0]


def evaluate(ws_url: str, expression: str, timeout: float = 20.0):
    if websocket is None:
        raise RuntimeError('missing dependency "websocket-client"; run: python -m pip install -e ".[dev]"')
    ws = websocket.create_connection(ws_url, timeout=timeout)
    try:
        next_id = 1
        payload = {
            "id": next_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
                "userGesture": False,
            },
        }
        ws.send(json.dumps(payload))
        while True:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("id") != next_id:
                continue
            if "error" in msg:
                raise RuntimeError(f"CDP error: {msg['error']}")
            result = msg.get("result", {}).get("result", {})
            if result.get("subtype") == "error":
                raise RuntimeError(result.get("description") or "renderer evaluation failed")
            if "value" not in result:
                raise RuntimeError(f"renderer returned no serializable value: {result}")
            return result["value"]
    finally:
        ws.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only live Electron palette probe for GenFarmer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--output", help="Optional explicit output JSON path")
    args = parser.parse_args()

    endpoint = f"http://{args.host}:{args.port}"
    try:
        targets = http_json(endpoint + "/json/list")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot reach Electron remote debugging at {endpoint}: {exc}", file=sys.stderr)
        print("Launch GenFarmer with --remote-debugging-port=9222 after saving/closing the normal instance.", file=sys.stderr)
        return 2

    if not isinstance(targets, list):
        print("ERROR: /json/list did not return a target list", file=sys.stderr)
        return 2
    target = choose_target(targets)
    if target is None:
        print("ERROR: no debuggable renderer target found", file=sys.stderr)
        return 2

    try:
        probe = evaluate(str(target["webSocketDebuggerUrl"]), PROBE_JS)
    except Exception as exc:
        print(f"ERROR: renderer probe failed: {exc}", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = ROOT / "evidence" / f"genfarmer-renderer-palette-{stamp}" / "renderer-palette.shareable.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "catalog_format": 1,
        "privacy": "shareable renderer palette catalog; palette-region labels and safe DOM/Vue schema metadata only",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "debug_target": {
            "type": target.get("type"),
            "title": "GenFarmer renderer" if target.get("title") else None,
            "url_scheme": str(target.get("url") or "").split(":", 1)[0] or None,
        },
        "probe": probe,
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    labels = probe.get("draggable_labels", []) if isinstance(probe, dict) else []
    print("=" * 76)
    print("GENFARMER LIVE ELECTRON PALETTE PROBE")
    print("=" * 76)
    print(f"Renderer targets found: {len(targets)}")
    print(f"Draggable palette labels found: {len(labels)}")
    for label in labels:
        print(f" - {label}")
    print(f"Shareable result: {out_path}")
    print("Read-only: no click, drag, save, run, or flow mutation was performed.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
