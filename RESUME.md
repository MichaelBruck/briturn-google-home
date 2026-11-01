# Resuming this project

Parked **2026-11-01** (Asia/Dubai). This file is everything needed to pick it up
again from a fresh clone, after the original laptop copy has been deleted.

## State when parked

- **Google Home control of both Briturn bulbs works** through the TV box
  gateway (reported by the user on 2026-11-01, after the Google account link
  was completed on the iPhone). The integration appears as
  **[test] My Lights**, devices **Tripod lamp** and **Reading Lamp**.
- Path: Google Home iPhone app → Google cloud → Cloudflare **Quick Tunnel** →
  Flask/Waitress gateway on the Android TV box (`192.168.1.199`, Termux) →
  bulbs on the HomeWiFi LAN (`192.168.1.172`, `192.168.1.195`, TCP 5577).
- Everything on the box was **started by hand**: Termux `sshd`, the gateway and
  `cloudflared`. **No auto-start.** If the box reboots or loses power, Google
  Home control stops until they are restarted — and the Quick Tunnel will come
  back with a **new hostname** (see "If Google Home stops working").
- Live box state was **not re-verified at park time** (the Mac was off the
  HomeWiFi Wi-Fi). Docs under `gateway/` and `google-home/RESUME.md` were last
  written 2026-10-30, just *before* the account link; where they say "consent
  pending" / "writes disabled", that has since been done.
- Offline tests at park time: 9/9 (`test_controller`) and 14/14
  (`gateway.test_gateway`) pass on the Mac.

## What is NOT in this repo (deliberately)

| Item | Where it is / how to get it back |
| --- | --- |
| Mac→box SSH private key, pinned host key (`tv-box-install/private/`) | Only on the old laptop. **Back up these 3 files before deleting** (e.g. 1Password secure note). Otherwise re-bootstrap SSH (below). |
| Gateway secrets: OAuth client secret, password hash, gateway login password, token DB | Only on the box: `~/.smart-bulb-bridge/gateway-private/` (Termux). The client secret is also in the Google console integration. |
| Termux APK (109 MB, over GitHub's limit) | Re-download from F-Droid; URL + SHA-256 in `tv-box-install/installer-source.json`. |
| Upstream reference clones (`research/upstream/`) | Re-clone; commits pinned in `research/upstream-versions.json` (commands below). |
| Python runtimes / venvs / caches (`.python/`, `.venv/`, `.bootstrap/`, `.cache/`, `gateway/.venv/`) | Recreate with `uv` (below). |
| Home Assistant prototype config (`google-home/config/`) | Identical copy committed as `google-home/configuration.local.yaml`. |

## Restore on a new Mac

```bash
git clone https://github.com/MichaelBruck/briturn-google-home.git
```

```bash
cd smart-bulb-control
```

Install `uv` (any method, e.g. `brew install uv`), then recreate both environments:

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements.txt
```

```bash
uv venv --python 3.13 gateway/.venv && uv pip install --python gateway/.venv/bin/python -r gateway/requirements.txt
```

(The original setup kept uv's Python and cache inside the project with
`UV_PYTHON_INSTALL_DIR="$PWD/.python" UV_CACHE_DIR="$PWD/.cache/uv"`; optional.)

Check everything offline (no network, no bulbs):

```bash
.venv/bin/python -m unittest -v test_controller && gateway/.venv/bin/python -m unittest gateway.test_gateway -v
```

Optional reference clones:

```bash
mkdir -p research/upstream && cd research/upstream && git clone https://github.com/lightinglibs/flux_led.git && git clone https://github.com/jamesrom/ha-briturn.git && git clone https://github.com/vikstrous/zengge-lightcontrol.git
```

### Control bulbs directly from the Mac (needs HomeWiFi Wi-Fi)

```bash
./bulb discover
```

```bash
./bulb tripod status
```

See [README.md](README.md) for all commands. If bulb IPs changed (DHCP), update
`devices.json` only after the discovery ID matches.

### Regain SSH access to the TV box

**If you backed up `tv-box-install/private/`:** restore the three files
(`mac-ed25519` mode 600, `mac-ed25519.pub`, `box-known-hosts`), and make sure
the Mac has IP `192.168.1.141` on HomeWiFi — the box only accepts that source
IP. Then:

```bash
./tvbox status
```

If the Mac's IP differs, on the box (USB keyboard, Termux) edit
`~/.smart-bulb-bridge/mac-authorized-key` and change `from="192.168.1.141"`.

**If you did not back up the key:** generate a new one and re-bootstrap:

```bash
mkdir -p tv-box-install/private && ssh-keygen -t ed25519 -N '' -f tv-box-install/private/mac-ed25519
```

```bash
.venv/bin/python tv-box-install/serve-ssh-bootstrap.py
```

On the box, in Termux (stop any running sshd first with Ctrl+C), run
`curl http://<mac-ip>:8765/setup | bash`. It overwrites the authorized key with
the new one and restarts sshd in the foreground; the host key is kept, so the
fingerprint stays `SHA256:<box-host-key-fingerprint>`. Recreate
the pinned host-key file:

```bash
ssh-keyscan -p 8022 -t ed25519 192.168.1.199 > tv-box-install/private/box-known-hosts && ssh-keygen -lf tv-box-install/private/box-known-hosts
```

Confirm the fingerprint matches, then stop the bootstrap server. `tv_box.py`
hard-codes the box IP, port and Termux user `u0_a52`.

## If Google Home stops working

Most likely cause: the box slept/rebooted or Termux was closed, so sshd, the
gateway and the tunnel are gone. (This happened on 2026-11-01: the box went
into sleep mode and had to be restarted.) Opening Termux does **not** restart
anything.

0. On the box, in Termux (USB keyboard), start SSH in the background:
   `sshd -f ~/.smart-bulb-bridge/sshd_config` — then continue from the Mac over
   SSH (`./tvbox gateway-health` should connect, and fail on HTTP until step 1).
1. Start the gateway (loopback only):
   ```sh
   cd "$HOME/.smart-bulb-bridge/gateway-app"
   nohup "$HOME/.smart-bulb-bridge/gateway-venv/bin/python" -m gateway.manage serve \
     >> ../gateway-private/gateway.log 2>&1 &
   echo $! > ../gateway-private/gateway.pid
   ```
2. Start the tunnel: `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8766`
   and note the new `https://….trycloudflare.com` hostname.
3. Put that hostname in `public_url` in `~/.smart-bulb-bridge/gateway-private/config.json`
   and restart the gateway (verify the PID's `/proc/PID/cmdline` first).
4. In the [Google Home Developer Console](https://console.home.google.com/projects/my-lights-project/cloud-to-cloud/setup)
   update the three URLs: `https://HOST/oauth/authorize`, `https://HOST/oauth/token`,
   `https://HOST/fulfillment`. Re-link in the Google Home app if asked (the
   gateway login password is in `gateway-private/gateway-password.txt` on the box).
5. Check: `./tvbox gateway-health` and `./tvbox gateway-status` from the Mac.

`gateway/publish_test.py` automates 2–3 but refuses if `public_url` is already
set — clear it first, or follow the steps manually.

## Recommended next steps when resuming

1. **Auto-start:** Termux:Boot (F-Droid) script that runs `termux-wake-lock`,
   `sshd`, the gateway and the tunnel; then test a power cycle.
2. **Stable hostname:** named Cloudflare tunnel on a domain/subdomain you
   control (the domain is on GoDaddy with Google mail records — only delegate a
   subdomain or add a CNAME, don't move nameservers blindly).
3. **DHCP reservations** for the box, the bulbs and the Mac.
4. Optional: HomeGraph Report State / Request Sync so state changes made
   elsewhere (Briturn app, wall switch) show up promptly in Google Home.

## Map of the repo

| Path | What |
| --- | --- |
| [README.md](README.md) | Overview + Mac CLI (`./bulb`) usage |
| [docs/TV-BOX-HOME-HUB.md](docs/TV-BOX-HOME-HUB.md) | **Reusable lessons: Android TV box as a home hub** |
| [gateway/](gateway/README.md) | Google Home Cloud-to-cloud gateway that runs on the box |
| [tv-box-install/](tv-box-install/README.md) | Termux install packet, SSH bootstrap, read-only box client |
| [diagnostics/FINDINGS.md](diagnostics/FINDINGS.md) | Bulb protocol & LAN investigation log |
| [diagnostics/tv-box/README.md](diagnostics/tv-box/README.md) | Box investigation log, photos, evidence JSON |
| [google-home/](google-home/README.md) | Archived Home Assistant / Docker alternative (not used) |
| `controller.py`, `discover.py`, `lan.py`, `bulb` | Mac CLI for the bulbs (flux-led 1.2.0) |
| `tv_box.py`, `tvbox` | Mac → box SSH helper |
