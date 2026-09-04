# Device Map

The real client device map is intentionally **not committed** to this public repository.

Use:

`config/device-map.local.yaml`

Example schema:

| Field | Purpose |
|---|---|
| position | Farm position |
| name | Local friendly name |
| adb_id | ADB endpoint |
| genfarmer_id | GenFarmer identifier |
| xproxy_position | XProxy position |
| http_proxy | Local HTTP proxy endpoint |
| socks5_proxy | Local SOCKS5 proxy endpoint |

Start with one device and extend only after the workflow is stable.
