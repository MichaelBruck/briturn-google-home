# Smart-bulb control (Briturn bulbs → Google Home via an Android TV box)

> **About this public copy.** This is a cleaned-up copy of a personal project, published
> as a worked example. Device MACs and discovery IDs, the TV box's SSH fingerprint, the
> Google account and project ID, the tunnel hostname and photos of the TV have been
> replaced with placeholders or removed. The private LAN addresses (`192.168.1.x`)
> are left as they were. Change `devices.json`, `tv_box.py` and the gateway config to match
> your own network. No support or warranty: read the code before running it against your
> devices or exposing anything to the internet.
>
> Licensed under the [MIT License](LICENSE). It builds on [flux_led](https://github.com/lightinglibs/flux_led)
> (LGPL-3.0-or-later), which is installed from PyPI and imported as a library, not copied into this repo.

**Parked 2026-11-01. Google Home control of both bulbs works.**
To pick it up again, read **[RESUME.md](RESUME.md)** first. The reusable lessons
about turning a cheap Android TV box into a home hub are in
**[docs/TV-BOX-HOME-HUB.md](docs/TV-BOX-HOME-HUB.md)**.

Two Briturn (Zengge / Magic Home protocol, `flux_led`-compatible) Wi-Fi bulbs had a
broken vendor cloud link to Google Home. This project:

1. Controls them **locally from the Mac** over the LAN (`./bulb …`, below).
2. Runs a small **Google Home Cloud-to-cloud gateway** on a 32-bit Android 9 TV
   box under Termux, published via a Cloudflare tunnel ([gateway/](gateway/README.md)),
   so the Google Home iPhone app controls the bulbs without Briturn's cloud, a
   Google hub, Home Assistant or a subscription.

The sections below are the original Mac CLI documentation (2026-10-28/29).

## Mac CLI history

Phase one, 2026-10-28 (Asia/Dubai). **Both bulbs are identified and answer local
read-only queries on HomeWiFi.** The Mac is now `192.168.1.127/24` on `en0`.
The initial discovery failure was on the separate Xiaomi/guest Wi-Fi subnet.
Local white-temperature/brightness tests succeeded on Tripod at 22:38 and Reading
at 22:40. At the user's request, both were then set to full brightness at 22:41;
fresh queries report 100% and nominal 3982 K. Each test changed only its intended
lamp.
No pairing settings were changed. See [diagnostics/FINDINGS.md](diagnostics/FINDINGS.md).

| Alias | Bulb | IP | Observed state at 22:33 |
| --- | --- | --- | --- |
| `tripod` | Tripod lamp | `192.168.1.172` | On, white, 95.7%, nominal 2871 K |
| `reading` | Reading Lamp | `192.168.1.195` | On, white, 98.8%, nominal 2700 K |

Both report module `AK001-ZJ21413`, model `0x35` (RGBCW), state version byte
`0x0A`, and firmware date `2025-06-19`. Briturn screenshots show
`WF.4C.35.286.0,V10_ZG-BK38-BP101`. The maintained library selects its
`LEDENET_25_BYTE` control format for this version; state queries remain the
checksum-protected 2014 query. RGB and CCT are the model's supported modes.

This project uses the published `flux-led==1.2.0` library in an isolated Python
3.13 environment. Current upstream repositories were separately inspected and
cloned under `research/upstream/`; commits and installed versions are recorded
in [research/upstream-versions.json](research/upstream-versions.json).
No Home Assistant, daemon, router change, reset or firmware change is involved.

## Run

From this directory, no environment activation is needed:

```sh
./bulb discover
```

Discovery runs upstream `BulbScanner.scan` with a directed broadcast on the
active physical IPv4 LAN. Darwin `IP_BOUND_IF` binds sockets to that interface,
and their source address is its LAN address. Discovery never targets VPNs,
other subnets or the Internet. Its UDP messages on port 48899 are:
`HF-A11ASSISTHREAD`, `AT+LVER\r`, and `AT+SOCKB\r` (read-only queries).
There are no AT setters, provisioning requests, cloud-disable requests or reboots.
Discovery JSON includes replies, model/firmware fields when available, and
checksum-validated TCP state results for discovered candidates.

Read the identified bulbs:

```sh
./bulb tripod status
./bulb reading status
```

You can also check any directly connected bulb IP explicitly (replace `BULB_IP`):

```sh
./bulb discover --host BULB_IP
./bulb BULB_IP status
```

Status accepts an explicit IP on the current physical LAN. It sends only
`81 8A 8B 96` to TCP 5577, requires a standard 14-byte reply beginning with
`81`, validates its checksum and power byte, then uses the upstream library
to identify and parse it. A TCP listener alone never establishes bulb identity.
Status has a transport-level guard refusing non-state-query frames.

## Repeat the successful local test

With the Mac connected to **HomeWiFi**, this targets only the Tripod lamp:

```sh
./bulb tripod white 4000 --brightness 50
```

This selects nominal 4000 K white at 50%. On firmware that does not automatically
power on when setting levels, run `./bulb tripod on` afterward. Software power
off is supported; a bulb switched off at the wall cannot be reached.

Other commands:

```sh
./bulb tripod on
./bulb tripod off
./bulb tripod brightness 30
./bulb tripod rgb 255 0 0
./bulb tripod white 2700 --brightness 30
./bulb reading status
```

Each write first reads and validates live state and checks the live UDP discovery identity
against [devices.json](devices.json) to catch stale IPs. Controls are gated to
identified devices, model `0x35`, RGB+CCT capabilities, and the library's
`LEDENET`, `LEDENET_AUTO_ON`, `LEDENET_DIMMABLE_EFFECTS`, or `LEDENET_25_BYTE`
variants. The last is selected for both of these bulbs. Frame generation and
checksums are tested offline. **White temperature and brightness have also been
verified through changed live device state.** RGB and power commands have not yet
been exercised on the physical bulbs. Other models and unrecognized framing fail
closed.

Brightness is 0–100%, preserves a static RGB hue or white mix, and refuses effects
or ambiguous zero-channel states. RGB values are 0–255; the largest channel sets
the intensity. White temperature is the library's nominal 2700–6500 K mapping,
not a measured calibration. Firmware may power on when color/brightness changes;
use `off` explicitly to turn off. A zero brightness level is not an `off` command.

Commands use a new read-only connection/object after writing to avoid reporting
the library's optimistic cached values, then close their TCP connections.
The JSON is the observed read-back, not a claim of perceptual success. If read-back
fails, a write may already have reached the bulb; check status before retrying.
Choose one bulb IP at a time; there is no implicit “all lights” action.
DHCP can change addresses. If an alias stops working, rerun discovery and update
its IP in `devices.json` only after matching the discovery ID; do not remove the
identity check. The discovery ID and actual Wi-Fi MAC differ by one in the final
byte on both bulbs; both separately observed identifiers are recorded. The write
guard uses the discovery ID that matches the app screenshots. Room/name
association comes from your screenshots, not from a model byte.

## Diagnostics and tests

```sh
.venv/bin/python probe_lan.py
.venv/bin/python -m unittest -v test_controller
```

The fallback checks **only TCP 5577**, with 16 workers and a 2-second connection
timeout, on the directly connected LAN. It refuses automatic subnets larger
than `/24`. It queries only open listeners and labels invalid replies as errors.
It does not treat ordinary peers as bulbs. Discovery and fallback save timestamped
JSON in `diagnostics/`; these contain local IPs/device identifiers, so review them
before sharing externally. Tests use synthetic replies and a short-lived loopback
server; they do not contact bulbs.

If running through a sandbox, shell-level `Operation not permitted` can mean the
execution sandbox denied networking. It is distinct from macOS Local Network
privacy and from LAN isolation. Use a normal Terminal session on this Mac for
these commands if the execution host denies network access. No `sudo` is needed.

## Environment and reproducibility

The existing `.venv` works now. The project-local runtime is under `.python/`;
bootstrap tooling and caches are under `.bootstrap/` and `.cache/`. Nothing was
installed into system Python. To recreate from the existing bootstrap tool:

```sh
UV_PYTHON_INSTALL_DIR="$PWD/.python" UV_CACHE_DIR="$PWD/.cache/uv" \
  .bootstrap/bin/uv venv --python 3.13 --managed-python .venv
UV_CACHE_DIR="$PWD/.cache/uv" \
  .bootstrap/bin/uv pip install --python .venv/bin/python -r requirements.txt
```

`requirements.txt` pins all three runtime packages. The upstream source clones
are reference material; the controller imports the pinned installed package.

The [TV-box gateway](gateway/README.md) is installed and its loopback HTTP server
is running. The [Google Home project](google-home/README.md) exists; public HTTPS
and account linking remain pending. The Mac CLI works independently.
