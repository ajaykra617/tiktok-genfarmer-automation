# GenFarmer API

## Base URL

Configured locally through `GENFARMER_BASE_URL` in `.env`.

## Confirmed service metadata

- `GET /` returns HTTP `200`.
- Root body identifies the service as **GenFarmer 2.6.1**.
- Root content type observed: `text/html; charset=utf-8`.
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

Conclusion: the local GenFarmer service is reachable, but it does not expose conventional Swagger/OpenAPI metadata at the common paths tested.

## Known functional status

- GenFarmer API connectivity has been confirmed in the client lab.
- Fingerprint rotation has previously been tested successfully.
- Exact device/project/fingerprint endpoint schemas still need to be captured.

## Discovery strategy

1. Read-only HTTP metadata probe (`scripts/genfarmer_discovery.py`).
2. Read-only inspection of the Windows process listening on the configured GenFarmer port (`scripts/genfarmer_local_inspect.py`).
3. Scan only nearby non-secret text assets for route-like strings.
4. Confirm candidate routes using GET/HEAD or observation of the GenFarmer UI before implementing mutations.
5. Record every verified endpoint below with sanitized schemas/examples.

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
| TBD | TBD | Device listing | To discover |
| TBD | TBD | Device control | To discover |
| TBD | TBD | Fingerprint/profile | Partially proven functionally; schema to discover |
| TBD | TBD | Automation/project execution | To discover |
