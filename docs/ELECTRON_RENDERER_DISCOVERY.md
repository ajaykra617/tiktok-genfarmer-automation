# GenFarmer Electron Renderer Discovery

## Why this exists

GenFarmer 2.6.1 is an Electron application. Its no-code node palette is rendered by a Chromium renderer from JavaScript/Vue state. Raw token scanning of `resources/app.asar` proved too noisy/incomplete to enumerate the palette reliably.

A better discovery lane is to inspect the **live renderer** through Chromium's remote-debugging protocol. This gives us the rendered palette and privacy-safe component metadata without clicking, dragging, saving, running, or modifying an Automation App.

## Safety boundary

`scripts/genfarmer_renderer_palette_probe.py` is read-only. It:

- connects only to the local Chromium DevTools endpoint;
- evaluates JavaScript in the renderer;
- scrolls the palette container and restores its previous scroll position;
- collects palette-region labels;
- collects DOM metadata and Vue component/prop **shapes**;
- retains only strict semantic scalar keys such as `action`, `type`, `nodeType`, `category`, `component`, `group`, and `kind`;
- writes its output under ignored `evidence/`.

It does **not** click, drag, create, edit, save, run, or execute any node.

## Starting GenFarmer with remote debugging

Save any current work in GenFarmer first, then close the normal instance. From PowerShell:

```powershell
$gf = Join-Path $env:LOCALAPPDATA "Programs\GenFarmer\GenFarmer.exe"
Start-Process $gf -ArgumentList "--remote-debugging-port=9222"
```

Confirm Chromium exposes a renderer target:

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/list
```

Do not expose the debugging port to the LAN. It must remain bound to localhost for this lab workflow.

## Install development dependency

```powershell
python -m pip install -e ".[dev]"
```

## Run the palette probe

Open an Automation App so the left node palette is visible, then run:

```powershell
python scripts/genfarmer_renderer_palette_probe.py
```

The result is written to:

```text
evidence/genfarmer-renderer-palette-.../renderer-palette.shareable.json
```

The console also prints the draggable palette labels it found.

## What we want from this pass

The renderer probe should give us a much stronger inventory than screenshots or raw archive scanning:

- every category heading that becomes rendered while the palette is scrolled;
- every draggable node label;
- associated Vue component names when exposed;
- prop field/type paths;
- safe semantic tokens such as internal action/type/category values when exposed.

This does not automatically prove each node's runtime settings. Once the full palette is known, settings are learned from live GenFarmer-generated templates and one-field differential snapshots.

## Next phase

After the full palette list is available:

1. compare it with the currently verified semantic-action registry;
2. create `GF Lab - Node Catalog` only for missing actions;
3. save one harmless instance of each missing node;
4. re-run structural and semantic flow learners;
5. use private exact templates for Python authoring;
6. learn each ambiguous setting by changing one UI control at a time and diffing the resulting `script.flow`.
