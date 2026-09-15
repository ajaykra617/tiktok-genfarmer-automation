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

The Phase A scheduler and standalone proxy qualifier now enforce a fail-closed
network gate before proxy-required device work starts. The gate distinguishes
listener reachability from real internet egress and only qualifies a lane after
an external-IP endpoint succeeds through the configured HTTP proxy.

Live qualification on 2026-09-15 established that the tested HTTP proxy listener
was reachable, while the external HTTP(S) request timed out. Therefore the proxy
lane remains **blocked for apply-mode automation**: an open TCP port alone is not
accepted as proof of mobile internet availability. This result is consistent with
a modem/SIM/upstream-data-path problem, a proxy egress problem, or an HTTPS CONNECT
problem; the application automation layer should not guess which one.

Use the standalone qualifier first. Only after it reports TCP PASS, HTTP(S) egress
PASS and an external IP should the apply-mode wave executor be used. The executor
must continue to stop before touching a device when this gate is not satisfied.

A later device-route qualification is still required to prove that TikTok traffic
on Android is actually routed through the selected proxy; host-to-proxy egress
qualification does not by itself prove Android application routing.
