# GenFarmer API

## Base URL

Configured locally through `GENFARMER_BASE_URL` in `.env`.

## Known status

- API connectivity has been confirmed in the client lab.
- Fingerprint rotation has been tested successfully.
- Exact endpoint inventory and schemas still need to be captured.

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
