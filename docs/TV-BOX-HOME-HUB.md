# Using a cheap Android TV box as a home hub — lessons learned

Written 2026-11-01 when this project was parked. This is the reusable knowledge
from turning a generic Android TV box into an always-on home-automation host that
Google Home controls. It is deliberately independent of the bulbs, so it can be
used for future projects. Project-specific details are in
[`gateway/README.md`](../gateway/README.md) and
[`diagnostics/tv-box/README.md`](../diagnostics/tv-box/README.md).

**Bottom line:** a ~1 GiB, 32-bit Android 9 TV box *can* be a useful little
always-on Linux-ish server via **Termux**, reachable by **SSH**, running **small
Python services** and a **Cloudflare tunnel** for public HTTPS. It *cannot* run
current Home Assistant, Docker, or act as a Google Home/Matter hub. Design for a
small, purpose-built service rather than a full home-automation stack.

---

## 1. The hardware we had

| Property | Value | How it was established |
| --- | --- | --- |
| Reported manufacturer / board | Hivendor / `bigfish` (generic "android tv") | `getprop` over SSH |
| Android | 9 (SDK 28), security patch 2025-07-05 | Settings photos + `getprop` |
| CPU ABI | `armeabi-v7a,armeabi`, kernel `armv7l` → **32-bit ARM** | `getprop ro.product.cpu.abilist`, `uname -m` |
| RAM | 1 GiB (`MemTotal 1048576 kB`) | `/proc/meminfo` |
| Storage | ~4 GB data partition, ~1.5 GB free after Termux setup | `df -h` |
| Ports | 2 × USB-A (host only), Ethernet, Wi-Fi | Physical inspection / manual |
| Build string | `eng.dell.20251122…` — does **not** mean Dell hardware | Settings photos |
| LAN | HomeWiFi Wi-Fi, `192.168.1.199`, MAC `xx:xx:xx:xx:xx:xx` | Settings photos |

The build is an `eng` build with a generic name — typical of no-brand boxes.
Don't trust the model name; measure with `getprop` and `/proc`.

## 2. What did NOT work (save yourself the time)

1. **Network ADB.** TCP 5555 was closed, and stayed closed even after enabling
   Developer options → USB debugging. No "ADB over network" toggle exists on
   this firmware. Android 9 has no Android 11+ wireless-pairing flow.
2. **USB to the Mac.** The USB-A ports are host ports (for flash drives,
   keyboards). They are not OTG/device ports; don't use an A-to-A cable.
3. **Remote services out of the box.** Ports 22 (SSH), 6466 (Android TV
   remote), 8009 (Cast) all refused; no mDNS service announcements.
4. **Home Assistant.** Current HA dropped 32-bit ARM (release 2025.12), and
   native Android is not an HA install target anyway. Docker is unavailable.
5. **Google Home Matter route.** A Matter bridge on the box is not enough:
   Google requires a Matter-capable Google/Nest hub. With only the iPhone
   Google Home app, you need a **Cloud-to-cloud** integration instead.
6. **A Toshiba flash drive** enumerated as a USB device but never mounted as a
   disk on the Mac. A Seagate drive reformatted **MBR + FAT32** worked.

## 3. What DID work — the reusable recipe

### Step A — Install Termux without ADB (flash drive)

1. Download Termux from **F-Droid** (not Play Store; not random APK sites).
   We used the universal APK `com.termux_1002.apk` (v0.118.3,
   SHA-256 `e6265a57eb5ca363808488e3b01955958bed93bc0c8a0d281849b363b11027ec`,
   from <https://f-droid.org/en/packages/com.termux/>). Universal avoids guessing
   the ABI. Check [`tv-box-install/installer-source.json`](../tv-box-install/installer-source.json).
2. Copy to a **FAT32/MBR** flash drive; eject safely.
3. On the box open the preinstalled file manager (here **HiFileManager**),
   select the APK, allow "install unknown apps" for that file manager, install.
4. Open Termux (if absent from the TV launcher: Settings → Apps → Termux → Open).
   A **USB keyboard** plugged into the box makes the first steps bearable.
5. All future Termux add-ons (Termux:Boot, Termux:API…) **must also come from
   F-Droid** — builds from different sources have different signing keys and
   won't interoperate.

### Step B — Bootstrap key-only SSH from the Mac (one command typed on the TV)

Typing long commands on a TV is miserable, so the Mac serves a one-shot script:

- [`tv-box-install/serve-ssh-bootstrap.py`](../tv-box-install/serve-ssh-bootstrap.py)
  runs on the Mac at `http://<mac-ip>:8765/setup`, serves **only** to the box's
  IP, and templates in the Mac's public key and IPs.
- In Termux type: `curl http://<mac-ip>:8765/setup | bash` (or `pkg install curl` first).
- [`tv-box-install/ssh-bootstrap.sh`](../tv-box-install/ssh-bootstrap.sh) installs
  `openssh` + `python`, writes an isolated `sshd_config` under
  `~/.smart-bulb-bridge/` (port **8022**, key-only, `from="<mac-ip>"` restriction,
  no forwarding), prints the host-key fingerprint, and runs `sshd -D` in the
  foreground.
- Compare the printed fingerprint (take a phone photo of the TV) to what the Mac
  sees before trusting it; pin it in a project-specific `known_hosts`.
- Stop the Mac's bootstrap server afterwards.

Mac-side SSH wrapper: [`tv_box.py`](../tv_box.py) (strict host key checking,
dedicated key, `IdentitiesOnly`, timeouts). Termux's user looks like `u0_a52`.

### Step C — Run Python services in Termux

- Termux's `python` was 3.14 on this box; a `python -m venv` plus pinned
  `pip install -r requirements.txt` worked. Prefer **pure-Python** dependencies;
  packages needing native wheels for `armv7l` may need to compile (slow, may fail
  on 1 GiB RAM).
- What we ran successfully: Flask, Flask-WTF, OAuthLib, Waitress, flux_led, SQLite
  (stdlib). Waitress, not Flask's dev server.
- Bind services to **127.0.0.1** and expose them only via the tunnel. Keep
  secrets in an owner-only dir (`umask 077`, dir 700, files 600).
- Deploy from the Mac by piping a tar of an explicit file list over SSH, then
  running tests on the box: see [`gateway/deploy.py`](../gateway/deploy.py).
- Start detached with a PID file; before killing, check `/proc/PID/cmdline`
  really is your process (see [`gateway/publish_test.py`](../gateway/publish_test.py)).

### Step D — Public HTTPS for cloud integrations

- `pkg install cloudflared` (official Termux package, 2026.10.5 worked on armv7).
- A **Quick Tunnel** (`cloudflared tunnel --url http://127.0.0.1:8766`) needs no
  account or domain and gives `https://<random>.trycloudflare.com`. Great for a
  test; **the hostname changes every time it restarts** and there's no uptime
  guarantee.
- For anything permanent use a **named Cloudflare tunnel** on your own domain (requires
  moving DNS or a subdomain to Cloudflare), or evaluate Tailscale Funnel / ngrok
  static domains. None of those were set up here.

### Step E — Google Home Cloud-to-cloud with just the iPhone app

- Google Home Developer Console → project → Cloud-to-cloud integration, device
  type Light. You provide OAuth authorize/token URLs and a fulfillment URL.
- Your service must implement OAuth 2 (auth-code + refresh) and the SYNC / QUERY /
  EXECUTE / DISCONNECT intents. ~600 lines of Python here
  ([`gateway/`](../gateway/)).
- An unpublished integration shows in the Google Home app as **"[test] Name"**
  under Works with Google for the developer's own account. No certification,
  billing or Google hub needed for personal use.
- `willReportState: false` keeps it simple (no HomeGraph service account).

## 4. Operational gotchas (the real limits of a TV box)

| Issue | What happened / risk | Mitigation (not yet implemented unless stated) |
| --- | --- | --- |
| **Nothing auto-starts** | sshd, gateway and tunnel were all started by hand. A reboot or power cut kills everything. | Install **Termux:Boot** (F-Droid) and put start scripts in `~/.termux/boot/`. |
| **Android may kill Termux / sleep** | Background process limits, Doze, TV standby. **Observed 2026-11-01:** the box went into sleep mode, needed a restart, and all services were gone. | `termux-wake-lock`; keep Termux's notification; Developer options → Stay awake; disable the box's sleep/screensaver. Test it. |
| **Quick Tunnel hostname changes** | After any tunnel restart Google's saved URLs break → Google Home stops working. | Named tunnel / stable hostname; otherwise update the 3 URLs in the Google console and the box's `public_url` config. |
| **DHCP** | Box IP and Mac IP are baked into SSH (`ListenAddress`, `from=`), `tv_box.py`, and gateway config. | DHCP reservations on the router, or update those places together. |
| **1 GiB RAM / 32-bit** | No HA, no Docker, limited native packages. | Small single-purpose services. |
| **Termux must be open** | Foreground `sshd -D` dies if the Termux session is closed. | Run sshd daemonised from Termux:Boot / `termux-services`. |
| **Remote access only from one Mac IP** | `from="192.168.1.141"` in the authorized key. | Edit `~/.smart-bulb-bridge/mac-authorized-key` on the box (needs keyboard) for a new laptop/IP. |
| **Sandboxed agents & macOS Local Network** | Some "Operation not permitted" errors were the agent sandbox, not the network. | Re-run in a normal Terminal before concluding the LAN is blocked. |

## 5. Checklist for the next "TV box as hub" project

1. `getprop ro.product.cpu.abilist`, `uname -m`, `/proc/meminfo`, `df -h` — decide
   up front if your stack supports 32-bit ARM.
2. Termux from F-Droid via FAT32 flash drive; USB keyboard.
3. Key-only SSH on 8022 via the bootstrap pattern; pin the host key.
4. Router DHCP reservations for the box (and your laptop if you use `from=`).
5. Python venv with pinned deps; loopback-only service; owner-only secrets dir.
6. Termux:Boot + `termux-wake-lock` + disable box sleep; **test a power cycle**.
7. Stable public hostname (named tunnel) before linking any cloud service.
8. Cloud-to-cloud integration if your only Google Home controller is a phone.

## 6. Sources

- Termux: <https://github.com/termux/termux-app>, F-Droid page above.
- HA 32-bit removal: <https://www.home-assistant.io/blog/2025/12/03/release-202512/>
- Google Matter needs a hub: <https://support.google.com/googlehome/answer/13127223>
- Google Cloud-to-cloud OAuth: <https://developers.home.google.com/cloud-to-cloud/project/authorization>
- Cloudflare Quick Tunnels: <https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/>
