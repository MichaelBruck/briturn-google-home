# TV-box Google Home gateway

> **Status 2026-11-01 — project parked, Google Home control working.** This file is a
> checkpoint written 2026-10-30; where it says account linking/consent is pending or
> writes are disabled, that has since been completed. Start from
> [RESUME.md](../RESUME.md).

Checkpoint: **2026-10-30, Asia/Dubai**. The local gateway is installed and running
on TV-box loopback `127.0.0.1:8766`. Google Home account linking remains pending.
Both bulbs were queried from the box this morning and report **off**. No visible
control test was performed this morning.

## Architecture

Google Home iPhone app → Google Cloud-to-cloud → HTTPS tunnel (temporary test active) →
Flask/Waitress on the TV box → `flux-led==1.2.0` → the two known bulbs.

The box is Android 9, 32-bit ARM, 1 GiB RAM. Current Home Assistant no longer
supports this architecture. This adapter uses maintained Flask, Flask-WTF,
OAuthLib, Waitress and flux_led; versions are pinned in `requirements.txt`.
The custom code maps Google intents and stores OAuth credentials. It does not
reimplement the bulb binary protocol.

## Commands from the Mac

```sh
cd ~/smart-bulb-control
./tvbox status           # Original box client: read-only, includes raw frames
./tvbox gateway-status   # Read-only Google-shaped bulb states from the box
./tvbox gateway-health   # Actual loopback HTTP server health
# Offline tests, simulated bulbs only:
gateway/.venv/bin/python -m unittest gateway.test_gateway -v
# Deploy reviewed source, preserve private config, run tests and status:
.venv/bin/python gateway/deploy.py
```

Fourteen offline tests pass on Mac and box: OAuth replay/concurrent exchange,
expiry, refresh rotation, client-secret/PKCE checks, exact redirects, CSRF,
revocation, missing/URL tokens, batch validation, unknown/offline devices,
checksum checks and device-identity/write guards.

On the box, from `~/.smart-bulb-bridge/gateway-app`, running
`~/.smart-bulb-bridge/gateway-venv/bin/python -m gateway.check` uses temporary
fixture credentials to exercise OAuth → SYNC → QUERY against the real bulbs,
then verifies revocation. It does not contact Google or change the lights.
`gateway.control_check` is a separate **visible** Reading Lamp test; do not use
it for routine monitoring or while the user expects lights to remain off.

## Hardware validation and corrections

On October 29, hardware read-back verified Reading Lamp brightness, RGB blue,
off/on and white temperature. These are device response checks, not a claim
that a human visually confirmed every step. Tripod remained unchanged.

The first UDP identity attempt stopped the test before writes. The real identity
reply arrived after 1.202 seconds, so the discovery window is now three seconds.

The test's first restoration passed RGB and white levels together, which did
not select the white write mask. Corrected it to pass `None` for RGB when
restoring white. A separate restoration verified both bulbs at exactly 100%,
nominal 3982 K. Keep this evidence distinction:

- `../diagnostics/tv-box/gateway-control-test.json`: controls passed; first restore failed.
- `gateway-restoration.json`: corrected restoration succeeded.
- `gateway-identity-probe.json`: timing and identity evidence.
- `gateway-local-validation.json`: temporary OAuth fixture and real read-only QUERY.
- `gateway-install-2026-10-30.log`: latest on-box dependency/test/status results.
- `gateway-http-start.txt`: actual loopback HTTP health HTTP 200 and unauthenticated HTTP 401.

Evidence filenames after the first bullet are in `../diagnostics/tv-box/` too.

## Runtime and secrets on the TV box

Relative to Termux's `$HOME/.smart-bulb-bridge/`:

| Path | Purpose |
| --- | --- |
| `gateway-app/` | Reviewed source and explicit bulb inventory |
| `gateway-venv/` | Separate pinned Python environment |
| `gateway-private/config.json` | Owner-only config, password hash, client secret |
| `gateway-private/gateway-password.txt` | Generated gateway login password |
| `gateway-private/oauth.sqlite` | Hashed codes/access/refresh tokens |
| `gateway-private/gateway.log` | Server error log, no OAuth debug logging |
| `gateway-private/gateway.pid` | Current manual start's PID; verify before use |

Private directory mode 700; files mode 600. Secrets are not copied into project
files or diagnostics. Config currently has project ID `my-lights-project`,
`public_url: https://random-words-example.trycloudflare.com`, `writes_enabled: false`.
Unauthenticated fulfillment returns HTTP 401. The approved public connection is
active; physical controls stay disabled until account linking is completed.

Interactive start on the box:

```sh
cd "$HOME/.smart-bulb-bridge/gateway-app"
"$HOME/.smart-bulb-bridge/gateway-venv/bin/python" -m gateway.manage serve
```

The current server was started manually in a detached process with those
arguments, loopback only. There is no boot service or automatic restart.
To stop it, verify the saved PID's `/proc/PID/cmdline` contains `gateway.manage`
and `serve`, then send SIGTERM. Never blindly kill a stale PID.
`python -m gateway.manage revoke` revokes all local codes/tokens; also unlink
from Google's connected-account settings. Automatic HomeGraph notification of
a locally initiated revoke is not implemented.

## Google project and prepared form

Project **My Lights**, ID **my-lights-project**, created under the user's
confirmed Google Home account `you@example.com` on October 30.
[Console setup](https://console.home.google.com/projects/my-lights-project/cloud-to-cloud/setup).

The integration is saved as **My Lights**, device type Light, scope
`control`, with the dedicated client credentials and verified public URLs. The
project display name is **My Lights**. The allocated project ID remains
`my-lights-project`; it is an internal identifier, not the lights' display name.

The icon is uploaded. Its 144×144 RGBA PNG and SVG source are in `assets/`.
The native chooser could not enable Open for the project-folder copy; copying
the verified PNG into Downloads and selecting it there succeeded. No unrelated
document was uploaded. Client credentials were transferred through an owner-only
temporary local file, read privately in the browser UI, then deleted.

Saved configuration (HOST is the current temporary tunnel hostname):

| Field | Value |
| --- | --- |
| OAuth client ID / secret | Dedicated random values in the box's private config |
| Authorization URL | `https://HOST/oauth/authorize` |
| Token URL | `https://HOST/oauth/token` |
| Fulfillment URL | `https://HOST/fulfillment` |
| Scope | `control` |
| HTTP Basic checkbox | Off; body credentials are supported, Basic also tested |
| Local fulfillment / App Flip | Off |

The dedicated client secret was registered with this Google project after
explicit approval. Exact production/sandbox Google redirects for this project
are accepted. Login uses the gateway's password, never the Google password.
Consent explains Google control of these two lights. Access tokens last one
hour; refresh tokens rotate. DISCONNECT revokes all local tokens. Password
attempts are durably limited to 10 per 15 minutes globally, without trusting
forwarded client-IP headers. Responses disable caching and framing.

SYNC exposes only `tripod` and `reading`, OnOff, Brightness, ColorSetting, RGB
and nominal 2700–6500 K. Writes revalidate direct UDP identity, model 0x35,
25-byte protocol and a checksum-valid state. QUERY and EXECUTE return freshly
observed states, subject to device channel/temperature quantization.

## Public-path validation and current consent step

The user explicitly approved the temporary tunnel and registering the dedicated
client credentials with Google. Public HTTPS is active at:

https://random-words-example.trycloudflare.com

`check_public.py` exercised real HTTPS, login, token exchange, refresh rotation,
SYNC and QUERY against the two real bulbs. It also verified unauthenticated HTTP 401,
wrong-client-secret HTTP 401, invalid-redirect HTTP 400, missing-CSRF HTTP 400, replayed-code HTTP 400,
replayed-refresh HTTP 400 and rejection of the cleaned-up test token HTTP 401. No Google
redirect was followed and no light-control command was sent. Only test tokens
were deleted; any actual Google-link tokens are preserved. Evidence:
`../diagnostics/tv-box/public-oauth-query.json` and
`../diagnostics/tv-box/public-https-validation.json`.

The iPhone's Google Home app now lists **[test] My Lights**. Its account
linking flow reached Google's consent page, which requests device information
and device control. An explicit action-time confirmation for that final Google
account-link grant is pending. Do not select Agree and continue until received.
The gateway login password is loaded privately in the current CUA session for
the next screen; its temporary Mac transfer file has been deleted.

Remaining steps:

1. Complete the approved Google consent and gateway login, verifying the exact
   two-device scope; do not save the password in a browser/password manager.
2. Confirm both lights appear in Google Home. Enable physical controls in the
   box's private config, restart only the gateway, and verify HTTP health.
3. Perform one intentional Google Home control test; restore the requested
   power state. Both lights are currently off and should stay off until then.
4. Choose a stable hostname and test Android sleep, network interruption and
   reboot behavior before adding automatic startup.

Official Termux `cloudflared 2026.10.5` is installed. The current Quick Tunnel
is running manually and changes hostname if recreated; it has no uptime
guarantee. No DNS/nameserver, router, firmware, billing or automatic-startup
changes were made. The user's domain remains on GoDaddy with existing Google
mail records. Tailscale Funnel and ngrok stable hostnames remain unvalidated
research options, not installed alternatives.

This personal development prototype uses `willReportState:false`. HomeGraph
Report State, Request Sync and certification are not implemented. Runtime and
SSH have stayed reachable during checks, but reboot recovery is unproven.
SSH is restricted to Mac source IP 192.168.1.141. DHCP changes need deliberate
reconciliation, not scans of unrelated networks.

Sources checked October 29–30:

- [Google OAuth](https://developers.home.google.com/cloud-to-cloud/project/authorization)
- [Google EXECUTE](https://developers.home.google.com/cloud-to-cloud/intents/execute)
- [Google colour schema](https://developers.home.google.com/cloud-to-cloud/traits/colorsetting)
- [OAuthLib server](https://oauthlib.readthedocs.io/en/latest/oauth2/preconfigured_servers.html)
- [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
- [HA32-bit removal](https://www.home-assistant.io/blog/2025/12/03/release-202512/)
