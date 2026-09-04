# GenFarmer API

## Base URL

Configured locally through `GENFARMER_BASE_URL` in `.env`.

## Known status

- API connectivity has been confirmed in the client lab.
- Fingerprint rotation has been tested successfully.
- Exact endpoint inventory and schemas still need to be captured.

## Safe discovery workflow

Run:

```powershell
python scripts/genfarmer_discovery.py
```

The discovery probe is intentionally GET-only and limited to root, health, version, and common API metadata/documentation paths. It does not send POST, PUT, PATCH, or DELETE requests.

Results are written locally under `evidence/genfarmer-discovery-*/result.json` and are Git-ignored.

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
| TBD | TBD | Device listing | To discover |
| TBD | TBD | Device control | To discover |
| TBD | TBD | Fingerprint/profile | Partially discovered |
| TBD | TBD | Automation/project execution | To discover |
