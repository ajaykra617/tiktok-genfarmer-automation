# XProxy

## Integration goals

For each position:

1. XProxy service reachable.
2. HTTP/SOCKS proxy ports available.
3. Cellular modem/SIM healthy.
4. Real mobile public IP verified.
5. IP rotation verified.
6. Workflow fails closed when a required proxy is unavailable.

## Local configuration

Do not commit client-specific:
- XProxy LAN addresses
- public proxy credentials
- SIM/provider identifiers
- device serials/IMEIs

Keep those in ignored local configuration/evidence.

## Current engineering note

The first position has been detected by XProxy and proxy listeners are available, but the cellular/SIM path still needs a real mobile public IP before proxy-required application workflows are enabled.
