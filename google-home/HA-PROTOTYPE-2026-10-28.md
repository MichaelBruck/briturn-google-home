# DIY Google Home integration

The user selected manual Google Cloud-to-cloud setup on 2026-10-28. There is no
Google/Nest hub, so this route links the Google Home iPhone app through Google's
cloud to a locally hosted Home Assistant server, which controls the bulbs over
HomeWiFi. Briturn and paid bridge subscriptions are not involved in this route.
This document describes planned work, not a completed account link.

## Prototype

Use the Mac's existing Docker runtime for a supported, isolated proof of concept.
`compose.yaml` pins Home Assistant 2026.10.4; its Magic Home integration requires
the same `flux-led==1.2.0` package already verified with the physical bulbs.
The container has its own project network and configuration directory. It binds
port 8123 to **127.0.0.1 only**, has no restart policy, and is not yet public.
No existing containers, router settings or bulb pairing need to change.

Preparation and local start:

```sh
cd ~/smart-bulb-control/google-home
mkdir -p config
chmod 700 config
cp -n configuration.local.yaml config/configuration.yaml
docker compose up -d
```

Open `http://127.0.0.1:8123`. The user creates the local Home Assistant owner
account and password. Do not paste that password into chat. Then add **Magic
Home** through Settings → Devices & services, using the explicit bulb addresses:

- Tripod lamp: `192.168.1.172`, discovery ID `0865F0AAAAAA`.
- Reading Lamp: `192.168.1.195`, discovery ID `0865F0BBBBBB`.

Docker on macOS may not receive physical-LAN broadcast discovery; use the known
IPs instead. Confirm status and the actual entity IDs before enabling the Google
configuration. Entity IDs in the example file are intended names, not observed
registry entries yet. Importing a light must not reset it or change pairing.

Stop the prototype with `docker compose stop`. Its configuration remains on disk.
Do not use `down --volumes` as a routine stop command.

## Public HTTPS connection

The user's domains are not currently managed by Cloudflare. The chosen domain is
pending. Inspect public DNS for that domain, then propose the exact hostname,
connector and DNS change before applying external changes. Do not silently change
nameservers or start a public tunnel while Home Assistant is uninitialized.

Google must reach the OAuth and fulfillment endpoints by HTTPS. A tunnel can
avoid router port forwarding. A Cloudflare Quick Tunnel supplies a temporary
hostname without an account/domain, but the hostname changes on restart and it
has no uptime guarantee; it is suitable only for a deliberate short-lived test.
Choose a stable endpoint for daily use. Do not put an interactive email/login
gate in front of Google's machine-to-machine token or fulfillment requests.
Home Assistant's own authentication remains required.

## Google developer project and account linking

Use the current **Google Home Developer Console**, not an obsolete Actions-only
workflow. Sign in using the Google account used in the iPhone's Google Home app.
Before creating external resources, agree the project name and exact endpoints.
No billing or paid subscription is required by this local setup; any prompt to
enable billing, accept new terms or grant additional permissions needs attention
at that step, not an automatic click.

Once the final hostname is known:

1. Create a developer project, proposed display name **My Lights**, and add
   a Cloud-to-cloud integration with the Light device type.
2. Use the Home Assistant-documented Google OAuth client ID:
   `https://oauth-redirect.googleusercontent.com/r/PROJECT_ID`.
3. Authorization URL: `https://HOSTNAME/auth/authorize`.
4. Token URL: `https://HOSTNAME/auth/token`.
5. Fulfillment URL: `https://HOSTNAME/api/google_assistant`.
6. Set scopes `email` and `name`, following the current Home Assistant guide.
7. Enable the HomeGraph API and create the narrowly scoped service account/key
   described by the current Home Assistant documentation. Keep its JSON in the
   private, ignored configuration directory, never in a public repo or chat.
8. Enable the template Google configuration, exposing **only the two intended
   light entities**. Confirm their real entity IDs first.
9. In Google Home, use Works with Google and link the personal `[test]` integration.
   The user signs in and approves account linking on the iPhone.
10. Verify state and then test a single light command. Record the result and
    restore the intended light setting afterward.

No custom OAuth server, refresh-token store or bulb binary protocol needs to be
implemented: use the maintained Home Assistant integration.

## Android TV box

The Termux APK and installation instructions are ready in `../tv-box-install/`.
Native Android is not a standard Home Assistant server target. Termux working
would establish shell/runtime capability, not guarantee that this full Home
Assistant stack or its dependencies will work reliably. Inspect CPU ABI, RAM and
runtime support before selecting it as the permanent host. Keep the Mac
prototype's configuration portable; do not flash the box or promise migration
before testing. The Mac-hosted bridge is unavailable when the Mac sleeps or
leaves HomeWiFi.

## Sources checked 2026-10-28

- [Home Assistant manual Google Assistant setup](https://www.home-assistant.io/integrations/google_assistant/).
- [Create a Google Home developer project](https://developers.home.google.com/cloud-to-cloud/project/create).
- [Magic Home integration requirements for the pinned HA version](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/flux_led/manifest.json).
- [Cloudflare Quick Tunnel limitations](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
