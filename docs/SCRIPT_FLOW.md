# GenFarmer `script.flow`

Official API source:

`https://genfarmer-support.gitbook.io/genfarmer-eng/main-menu-bar/api`

## What is officially confirmed

GenFarmer Automation Apps store automation logic in `script.flow`.
The public Local API example for updating an app shows:

```json
{
  "script": {
    "flow": {
      "nodes": [],
      "edges": []
    }
  }
}
```

The Automation UI exposes a node palette and allows apps to be created, edited,
saved and tested visually. The public documentation does **not** enumerate the
complete JSON schema for every node type.

Therefore we will not guess node payloads. We will learn the installed GenFarmer
version empirically and version the result.

## Goal

For GenFarmer 2.6.1, build a complete Python-compatible catalog containing:

- every node kind available in the Automation App palette;
- every observed node field and nested field;
- required vs optional fields;
- default values;
- input/output handles and edge behavior;
- selector formats;
- variable/input/output references;
- branching and loop semantics;
- app/device actions;
- wait/timing behavior;
- storage/output nodes;
- module/context nodes where applicable;
- exact edge schema variants;
- node compatibility notes for GenFarmer 2.6.1.

## First empirical corpus — 2026-09-04

The first read-only learner pass covered one Automation App and observed:

- 7 nodes;
- 3 edges;
- 4 Vue Flow node families: `custom`, `custom-context-menu`, `helper`, and `input`;
- 4 nodes used the broad `custom` family;
- all three edges shared one structural schema.

Important conclusion: **`node.type` is not enough to identify the actual automation operation.**
Multiple different operations are rendered as `type: "custom"`. Their semantic operation
identifier is carried by fields such as `data.action`. The original structural catalog
intentionally removed scalar values, so it grouped multiple real actions together.

The observed custom-node shapes already show several important GenFarmer runtime fields:

- `data.successNode` and `data.failNode`;
- `data.options.disabled` and `data.options.breakpoint`;
- `data.options.nodeSleep` and `data.options.nodeTimeout`;
- `data.options.timeoutAdbReconnect` and `data.options.timeoutNextNode`;
- one variant with `data.options.command` and `outputVariable`;
- one timing variant with `timeout`, `timeoutFrom`, `timeoutTo`, and `timeoutType`;
- `sourcePosition` and `targetPosition` graph metadata.

The observed edge schema contains:

- `source` / `target` node IDs;
- `sourceHandle` / `targetHandle`;
- duplicated handle metadata under `data.sourceHandle` / `data.targetHandle`;
- `type`, `animated`, `updatable`;
- visual coordinates and stroke styling.

This is enough to prove the graph is richer than a simple sequential node list, but it is
not enough to author arbitrary flows yet.

## Learning pipeline

### 1. Official documentation baseline

Treat the public GenFarmer API docs as the supported API contract. They confirm
that an existing Automation App can be read with `GET /automation/apps/:id` and
updated with `PUT /automation/apps`, including `script.flow`.

### 2. Existing-app structural corpus

Run:

```powershell
python scripts/genfarmer_flow_learn.py
```

This performs GET requests only. It reads every accessible Automation App,
collects its exact `script.flow` locally, and produces:

```text
evidence/genfarmer-flow-learn-.../
├── private/app-flows.raw.json
└── flow-catalog.shareable.json
```

The private raw corpus may contain selectors, text, app logic or other client-specific
information. It remains local and must never be committed.

### 3. Semantic action catalog

Because many actual operations share the same broad `type=custom`, run:

```powershell
python scripts/genfarmer_flow_semantics.py
```

This produces:

```text
evidence/genfarmer-flow-semantics-.../flow-semantics.shareable.json
```

The semantic catalog keeps only a strict allowlist of internal values such as:

- node family (`type`);
- `data.action`;
- handle names;
- timeout mode;
- disabled/breakpoint flags;
- option-key names and value types.

It does **not** expose node labels, IDs, selector text, commands, credentials, account
content or arbitrary user-entered strings. This catalog is the main shareable artifact
for building our Python node registry.

### 4. Packaged palette/action discovery

Live Automation Apps may not contain every action. GenFarmer 2.6.1 is Electron-packaged
and stores the renderer/application code in `resources/app.asar`. Run:

```powershell
python scripts/genfarmer_palette_scan.py
```

The scanner reads the package in place and does not extract or modify it. It searches for
strict token-like `action` declarations near automation-specific markers such as
`nodeSleep`, `nodeTimeout`, `successNode`, `failNode`, `casePaths`,
`sourcePosition`, and `targetPosition`.

It produces only a shareable token/metadata report:

```text
evidence/genfarmer-palette-scan-.../palette-candidates.shareable.json
```

No raw proprietary source snippets are emitted. Static action candidates are **hints**, not
verified node templates; a candidate becomes authorable only after it is observed in a real
saved `script.flow` on GenFarmer 2.6.1.

### 5. Local exact-template registry

`src/genfarmer_automation/flow_registry.py` loads the private raw corpus locally and indexes
exact GenFarmer-generated templates using the semantic key:

```text
<node.type>:<data.action>
```

and a structural signature for each observed variant.

Until an action's complete schema is known, Python must create a node by cloning one of these
real local templates and changing only verified fields. The registry never writes the raw
corpus into Git or a shareable artifact.

### 6. Lossless round-trip gate

Before Python is allowed to update any flow, the parser must prove that it can
read and serialize the flow without dropping or changing any field:

```powershell
python scripts/genfarmer_flow_roundtrip.py --app-id <APP_ID>
```

Required result:

```text
Exact dict equality after Python load/save: YES
```

### 7. Full node-palette coverage

Compare the live semantic catalog with the packaged palette/action candidate list first.
For any palette action that still lacks a verified saved template, create a dedicated lab app:

```text
GF Lab - Node Catalog
```

Add the still-unobserved node types from the Automation palette once and save the app. Use
harmless synthetic configuration only. Do not attach real credentials or account data. Nodes
may remain unconnected when GenFarmer permits it.

Then run both learners against the catalog app:

```powershell
python scripts/genfarmer_flow_learn.py --app-id <NODE_CATALOG_APP_ID>
python scripts/genfarmer_flow_semantics.py --app-id <NODE_CATALOG_APP_ID>
```

This gives the local template registry a real GenFarmer-generated template for each semantic
action rather than relying on static package strings.

### 8. One-field-at-a-time differential learning

For fields whose meaning is unclear, capture a private before snapshot:

```powershell
python scripts/genfarmer_flow_snapshot.py --app-id <APP_ID> --tag before
```

Change **exactly one field** in the GenFarmer UI, save, then snapshot again:

```powershell
python scripts/genfarmer_flow_snapshot.py --app-id <APP_ID> --tag after
```

Compare the two private `flow.raw.json` files locally:

```powershell
python scripts/genfarmer_flow_diff.py `
  --before <BEFORE_PRIVATE_FLOW_JSON> `
  --after <AFTER_PRIVATE_FLOW_JSON> `
  --output evidence\one-field-diff.shareable.json
```

The diff masks arbitrary strings and exposes raw values only for safe internal enum/timing/
handle paths. This lets us learn selectors, branch handles, time modes, variable references,
booleans and other undocumented behavior without sharing client-specific flow content.

### 9. Inspector-assisted selector learning

GenFarmer Inspector exposes useful mobile element information such as package,
activity, XPathLite, class name, coordinates, text, resource ID, description and
element state. Selector-related node templates will be learned using synthetic
or harmless UI targets first.

### 10. Versioned Python node registry

After a semantic action is proven, add an adapter under the Python flow layer.
The registry is versioned against GenFarmer 2.6.1. Unknown fields must always be
preserved.

## Python editing rules

`src/genfarmer_automation/flow.py` is intentionally lossless and schema-tolerant.
Until a node action is fully understood, Python should create new nodes by cloning
a real GenFarmer-generated template of the same semantic action and changing only
verified fields.

Safe progression:

```text
GET app
  -> exact script.flow snapshot
  -> parse losslessly
  -> resolve semantic action (type + data.action)
  -> clone exact local template variant
  -> patch only proven fields
  -> validate graph
  -> dry-run diff
  -> explicit authorized PUT
```

Never fabricate an undocumented node payload from scratch just because its UI label is known.

## Privacy / IP boundary

Do not commit raw client flows, purchased mini-app logic, credentials, selectors,
account data, tokens or app-specific secrets to this public repository.

Only generic structural schemas, safe semantic action names, our own lab templates,
tests and reusable Python code belong in Git.

## Completion definition

`script.flow` support is complete for GenFarmer 2.6.1 only when:

- the full visible node palette has been cataloged;
- each semantic action has at least one real saved template;
- structural variants are documented;
- default values and required fields are known;
- edge/handle behavior is known;
- round-trip equality is proven;
- one-field differential tests cover ambiguous settings/enums;
- Python can make a harmless edit and GenFarmer UI loads it correctly;
- Python can generate a harmless flow from verified templates and GenFarmer runs it;
- unknown fields remain losslessly preserved;
- all automation mutations remain explicit and fail-closed by default.
