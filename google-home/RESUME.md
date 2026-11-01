# Active checkpoint — 2026-10-30, Asia/Dubai

> **Status 2026-11-01 — project parked, Google Home control working.** This file is a
> checkpoint written 2026-10-30; where it says account linking/consent is pending or
> writes are disabled, that has since been completed. Start from
> [RESUME.md](../RESUME.md).

The user explicitly resumed and approved the public HTTPS test and registering
the dedicated gateway client credentials with Google. They also confirmed
Chrome was free. The user rejected the rental-company name for the lights;
use **My Lights** for the integration/gateway. Both bulb names stay
Tripod lamp and Reading Lamp.

## Current confirmed state

- Mac en0:192.168.1.141/24; box192.168.1.199. Pinned SSH works.
- Both bulbs last reported off. Do not infer who sent the previous overnight
  off commands; the retrieved execution record does not establish that.
- Box gateway and temporary Cloudflare tunnel are running. Physical writes are
  still disabled in private config. No automatic startup or DNS changes.
- Public origin: https://random-words-example.trycloudflare.com
- Project ID my-lights-project, Google account you@example.com.
  Project display name saved as My Lights. Integration saved as
  My Lights, Light type, control scope, dedicated client credentials,
  144×144 icon and all three HTTPS URLs. Saved creation and renamed project
  were directly verified in the console. Do not recreate the project.
- All 14 offline tests pass on Mac and box. Actual public HTTPS OAuth/code/
  refresh/SYNC/QUERY checks passed against the real bulbs, with negative auth,
  redirect, CSRF and replay checks. No physical command in that test. Test
  tokens were deleted without revoking other tokens.
- Google Home iPhone app, through iPhone Mirroring, shows [test] My Lights.
  Selected it and continued to Google's final account-link consent screen:
  see connected-device info; control connected devices when asked.
- An explicit confirmation request is pending to select Agree and continue
  on that screen and create the persistent Google link. Wait for the answer.
  Earlier approval covered the tunnel/credential setup; this prompt concerns
  the actual persistent account link.
- Gateway password is loaded in the CUA JS variable gatewayPassword; do not
  print it. The owner-only temporary transfer file was deleted. Credentials
  persist only in the box's protected gateway-private directory, plus the
  authorized dedicated client secret in Google's integration configuration.
- CUA browser connector is unavailable. Native Chrome/iPhone controls work.
  Do not try attaching OpenAndSavePanelService again: that call stalled for
  over an hour. File chooser selection worked after the verified icon was
  copied into Downloads and selected through its sidebar. No unrelated file
  was uploaded. The copied icon is Downloads/lights-icon.png.

## Next

After account-link consent approval, use the visible iPhone screen, proceed to
our My Lights gateway login and enter the existing gateway password
privately. Do not save passwords in a manager. Verify Google Home discovers
exactly Tripod lamp and Reading Lamp. Enable writes in private box config and
restart only the gateway (leave the tunnel running). Then test one explicit
Google Home on/off command and leave both lights off, verifying actual states.

All private paths, commands and limits: [gateway/README.md](../gateway/README.md).
The internal Google project ID remains its allocated value; user-facing names
have been corrected. The earlier Mac/HA plan is an archived alternative.
