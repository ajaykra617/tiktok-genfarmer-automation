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

Use `config/boost-phase-a-runtime.example.json` only as a template. Put real device ids, LAN addresses, proxy URLs, account labels, and media paths in `config/boost-phase-a-runtime.local.json`, which is ignored by git.

## Phase A readiness gate

`src/genfarmer_automation/proxy_readiness.py` provides vendor-neutral fail-closed checks for each configured HTTP proxy endpoint:

1. parse an explicit `http://host:port` endpoint;
2. prove the TCP listener is reachable;
3. in apply mode, route an external HTTP(S) request through that proxy;
4. require the response to contain a parseable external IP.

The external IP is private runtime evidence. It is not written into the shareable wave result.

`scripts/run_boost_phase_a_waves.py` validates the logical schedule before launch, checks every proxy used by a wave, starts tasks concurrently inside that wave, and enforces a hard barrier before the next wave. A failure in one task stops all later waves. The existing schedule policy additionally prevents two concurrent devices from using the same proxy identity for the same application.

Apply mode requires `--ip-check-url`; TCP reachability alone is intentionally insufficient for a proxy-required live run.

## Still deferred

The current readiness gate proves the host can reach the configured XProxy HTTP endpoint and obtain real egress through it. It does **not** yet claim that the Android device's TikTok traffic has been switched to that proxy or that XProxy modem rotation has occurred. Device-route assignment/rotation remains a separate qualification step and must not be inferred from the host-side readiness result.

## Current engineering note

One XProxy position has previously been reported live/working by the operator. Treat that as a strong readiness signal, but promote a position only after the external HTTP(S) egress gate passes and the observed external IP is recorded in ignored local evidence.
