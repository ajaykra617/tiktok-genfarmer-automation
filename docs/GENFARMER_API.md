# GenFarmer API

## Authoritative documentation

Official API documentation:

`https://genfarmer-support.gitbook.io/genfarmer-eng/main-menu-bar/api`

The official examples use the Local API at `http://127.0.0.1:55554`. The client lab is configured through `GENFARMER_BASE_URL` in the local ignored `.env` file.

The official API docs are now the primary contract for supported automation endpoints. Packaged-app inspection remains a fallback only for gaps that are not documented publicly.

## Local service verified in the client lab

- `GET /` returns HTTP `200`.
- Root body identifies the service as **GenFarmer 2.6.1**.
- Windows listener process: `GenFarmer.exe`.
- Observed product/file version: `2.6.1.0`.
- Common local Swagger/OpenAPI endpoints are not exposed.
- GenFarmer is Electron-packaged and contains `resources/app.asar`.

Because the published API page predates the observed 2.6.1 installation, every endpoint still receives a lightweight local compatibility check before we rely on it for automation.

## Officially documented read endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/backend/auth/me` | Current authenticated GenFarmer user |
| GET | `/automation/apps` | List Automation Apps; supports `userId`, pagination and sorting |
| GET | `/automation/apps/:id` | Get one Automation App |
| GET | `/automation/runs` | List Automation Runs; supports `userId`, pagination and sorting |
| GET | `/automation/runs/:id/storages` | Retrieve output/storage records for a run |

The first live compatibility test is implemented in `scripts/genfarmer_api_smoke.py`. It uses only these documented GET endpoints and leaves mutations disabled.

## Officially documented mutation endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/automation/runs` | Create an Automation Run |
| POST | `/automation/tasks` | Create an Automation Task |
| PUT | `/automation/apps` | Update an Automation App |
| PUT | `/automation/runs/:id/run` | Execute an Automation Run |
| PUT | `/automation/tasks/:id/add-devices` | Assign devices to a task |
| PUT | `/automation/tasks/:id/remove-devices` | Remove devices from a task |
| PUT | `/automation/tasks/:id` | Update a task |
| DELETE | `/automation/apps` | Delete one or more apps |
| DELETE | `/automation/tasks` | Delete one or more tasks |

The Python client implements these methods, but **mutations are fail-closed by default**. `GenFarmerClient(..., allow_mutations=False)` is the default and any POST/PUT/DELETE call raises before a request is sent. Authorized mutation workflows must opt in explicitly after IDs and payloads are verified.

## Important documented device shape

Task device assignment examples use device objects containing:

```json
{
  "id": "...",
  "serialNo": "...",
  "name": "..."
}
```

The docs also show two spellings around task device configuration:

- task create/update examples use `devices.enable`;
- add/remove-device examples use `devices.enabled`.

Preserve the spelling required by the specific endpoint rather than normalizing it blindly.

## What the official API page does not clearly document

The current public API page focuses on Automation Apps, Tasks and Runs. It does **not clearly document** the following items we still need for the full farm controller:

- generic local device inventory/list endpoint;
- direct mapping from all GenFarmer device IDs to ADB endpoints;
- fingerprint/change-device/profile mutation endpoints;
- direct proxy update/assignment endpoint and schema;
- a documented GET endpoint for listing Automation Tasks.

One documentation inconsistency is also present: a cURL section labelled as a task-list example points to `/automation/runs`, so we do not infer a GET task endpoint from that label alone.

For these gaps only, we may compare official UI behavior with the read-only packaged-resource findings. The packaged app exposed candidates including `/api/devices`, `/devices/details` and `/api/update_proxy`, but those remain **undocumented/internal candidates**, not part of our supported client until verified.

## Python integration

Primary client:

`src/genfarmer_automation/genfarmer_client.py`

Read-only compatibility smoke:

`python scripts/genfarmer_api_smoke.py`

The client currently exposes:

- `get_current_user()`
- `list_apps()`
- `get_app()`
- `list_runs()`
- `get_run_storages()`
- documented task/app/run mutation methods guarded by explicit mutation opt-in

## Endpoint verification policy

For every endpoint used in a production workflow, record:

- method and path;
- required request fields;
- observed response schema on GenFarmer 2.6.1;
- required device/app/task/run identifier;
- side effects;
- timeout and failure behavior;
- sanitized evidence from a controlled test.
