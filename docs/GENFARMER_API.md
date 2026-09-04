# GenFarmer API

## Base URL

Configured locally through `GENFARMER_BASE_URL` in `.env`.

## Confirmed service metadata

- `GET /` returns HTTP `200`.
- Root body identifies the service as **GenFarmer 2.6.1**.
- Root content type observed: `text/html; charset=utf-8`.
- The Windows process listening on the configured GenFarmer port is `GenFarmer.exe`.
- Observed product/file version: `2.6.1.0`.
- The executable is installed under the user's Local Programs `GenFarmer` directory.
- GenFarmer is Electron-packaged and includes `resources/app.asar`.
- A read-only packaged-resource scan discovered 69 route-like strings from `app.asar`.
- The following common metadata/documentation paths returned HTTP `404` in the client lab:
  - `/health`
  - `/api/health`
  - `/version`
  - `/api/version`
  - `/docs`
  - `/redoc`
  - `/swagger`
  - `/swagger/`
  - `/swagger/index.html`
  - `/openapi.json`
  - `/swagger.json`
  - `/api-docs`
  - `/api/docs`

## High-confidence route candidates from the packaged app

The following strings appear relevant to GenFarmer itself and are being verified using GET-only requests before any mutation calls are implemented:

- `/api/devices`
- `/devices`
- `/devices/details`
- `/devices/random`
- `/device`
- `/profile`
- `/group`
- `/instance`
- `/automation`
- `/automation/runs`
- `/tasks`
- `/apps`
- `/apps/total`
- `/api/update_proxy` — likely mutating; do not call until its method/schema is confirmed
- `/v1/devices/assign` — likely mutating; do not call until confirmed
- `/v1/devices/validate`
- `/v1/resource/device`

The packaged scan also found many dependency/API strings that may not belong to the local GenFarmer service, so route presence in `app.asar` is evidence for investigation, not proof that a localhost endpoint exists.

## Discovery strategy

1. Read-only HTTP metadata probe (`scripts/genfarmer_discovery.py`).
2. Read-only Windows listener/process inspection (`scripts/genfarmer_local_inspect.py`).
3. Read-only packaged application scan (`scripts/genfarmer_package_inspect.py`).
4. GET-only verification of curated high-confidence routes (`scripts/genfarmer_route_probe.py`).
5. Record verified endpoint schemas here before adding any mutation support.

## Discovery checklist

For every endpoint we confirm, record:

- Method
- Path
- Request schema
- Response schema
- Required device identifier
- Side effects
- Timeout behavior
- Failure behavior
- Example sanitized request/response

## Endpoint inventory

| Method | Path | Purpose | Status |
|---|---|---|---|
| GET | `/` | Service/version landing response | Verified: GenFarmer 2.6.1 |
| GET? | `/api/devices` | Candidate device listing | Route discovered; verification pending |
| GET? | `/devices` | Candidate device listing/control surface | Route discovered; verification pending |
| GET? | `/devices/details` | Candidate device details | Route discovered; verification pending |
| GET? | `/automation/runs` | Candidate automation-run listing | Route discovered; verification pending |
| GET? | `/tasks` | Candidate task listing | Route discovered; verification pending |
| GET? | `/apps` | Candidate app/project listing | Route discovered; verification pending |
| TBD | `/api/update_proxy` | Candidate proxy update endpoint | Do not call until mutation schema is confirmed |
| TBD | TBD | Fingerprint/profile mutation | Functionally proven previously; exact endpoint/schema still to discover |
