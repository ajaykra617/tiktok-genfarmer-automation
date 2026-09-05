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

One XProxy position is now reported live/working by the operator. Treat that as a strong readiness signal, but do not promote it to a fully qualified proxy lane until an end-to-end request through the proxy succeeds and the observed external IP is recorded in ignored local evidence.

The Chrome qualification lane should therefore use two gates:

1. direct browser/device automation qualification, so GenFarmer/browser failures are isolated from network/proxy failures;
2. proxy qualification immediately afterward, verifying proxy reachability, successful external HTTP(S) egress and detected external IP before any proxy-required application workflow is enabled.

Once both gates pass, the same proxy preflight can become a fail-closed prerequisite for TikTok runs.
