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

## Learning pipeline

### 1. Official documentation baseline

Treat the public GenFarmer API docs as the supported API contract. They confirm
that an existing Automation App can be read with `GET /automation/apps/:id` and
updated with `PUT /automation/apps`, including `script.flow`.

### 2. Existing-app corpus

Run:

```powershell
python scripts/genfarmer_flow_learn.py
```

This performs GET requests only. It reads every accessible Automation App,
collects its exact `script.flow` locally, and produces two files:

```text
evidence/genfarmer-flow-learn-.../
├── private/app-flows.raw.json
└── flow-catalog.shareable.json
```

`private/app-flows.raw.json` may contain selectors, text, app logic or other
client-specific information. It must remain local and must never be committed or
shared publicly.

`flow-catalog.shareable.json` contains only structural field paths, types, node
kind identifiers, counts and structural signatures. It is designed to be safe to
share back into this engineering conversation.

### 3. Lossless round-trip gate

Before Python is allowed to update any flow, the parser must prove that it can
read and serialize the flow without dropping or changing any field:

```powershell
python scripts/genfarmer_flow_roundtrip.py --app-id <APP_ID>
```

The required result is:

```text
Exact dict equality after Python load/save: YES
```

### 4. Full node-palette coverage

Existing apps may not contain every node kind. Create one dedicated lab app in
GenFarmer named approximately:

```text
GF Lab - Node Catalog
```

Add every available node from the Automation node palette once and save the app.
Do not attach real credentials or account data. Nodes can initially remain
unconnected when GenFarmer permits it.

Run the learner again against that app. Any node kinds not already present in the
corpus are added to the catalog.

If a node cannot be saved without required configuration, configure it only with
harmless synthetic values on a lab device.

### 5. One-field-at-a-time differential learning

For fields whose meaning is unclear:

1. snapshot the app;
2. change exactly one field in the GenFarmer UI;
3. save;
4. GET the app again;
5. diff the two flow payloads;
6. record the field semantics and allowed values.

This is how we learn enums, selector modes, time units, branch handles, variable
references and other undocumented details without guessing.

### 6. Inspector-assisted selector learning

GenFarmer Inspector exposes useful mobile element information such as package,
activity, XPathLite, class name, coordinates, text, resource ID, description and
element state. Selector-related node templates will be learned using synthetic
or harmless UI targets first.

### 7. Versioned Python node registry

After a node kind is proven, add a semantic adapter under the Python flow layer.
The registry will be versioned against the installed GenFarmer release. Unknown
fields must always be preserved.

## Python editing rules

`src/genfarmer_automation/flow.py` is intentionally lossless and schema-tolerant.
Until a node kind is fully understood, Python should create new nodes by cloning
a real GenFarmer-generated template of that same kind and changing only verified
fields.

The safe progression is:

```text
GET app
  -> exact script.flow snapshot
  -> parse losslessly
  -> clone/patch verified node templates
  -> validate graph
  -> dry-run diff
  -> explicit authorized PUT
```

Never fabricate an undocumented node payload from scratch just because its label
is known.

## Privacy / IP boundary

Do not commit raw client flows, purchased mini-app logic, credentials, selectors,
account data, tokens or app-specific secrets to this public repository.

Only generic structural schemas, our own lab templates, tests and reusable Python
code belong in Git.

## Completion definition

We will call `script.flow` support complete for GenFarmer 2.6.1 only when:

- the full visible node palette has been cataloged;
- each node kind has at least one real saved template;
- structural variants are documented;
- edge/handle behavior is known;
- round-trip equality is proven;
- Python can make a harmless edit and GenFarmer UI loads it correctly;
- Python can generate a harmless flow from verified templates and GenFarmer runs it;
- unknown fields remain losslessly preserved;
- all automation mutations remain explicit and fail-closed by default.
