# Android TV box assessment

> **Status 2026-11-01 — project parked, Google Home control working.** This file is a
> checkpoint written 2026-10-28 to 10-30; where it says account linking/consent is pending or
> writes are disabled, that has since been completed. Start from
> [RESUME.md](../../RESUME.md).

## Latest checkpoint — 2026-10-30

The lightweight gateway is installed and running on box loopback only. Its 14
offline tests pass on Mac/box; actual HTTP health HTTP 200 and unauthenticated HTTP 401 are
verified. Both bulbs currently report off. Google project my-lights-project is
created under the confirmed personal Gmail account; HTTPS/account linking are
pending. See [active gateway handoff](../../gateway/README.md). Older sections
below are historical and do not supersede this checkpoint.

## Current result — connected and local bulb queries verified, 2026-10-29

Read the user's `IMG_1162.HEIC` setup photo. It shows `u0_a52@192.168.1.199:8022`
and host fingerprint `SHA256:<box-host-key-fingerprint>`.
Compared that fingerprint to the network-observed Ed25519 key before connecting;
strict host-key checking and the project-specific client key succeeded.

Read-only hardware inspection establishes:

- Reported manufacturer: Hivendor; hardware/board: `bigfish`.
- Android 9, SDK 28; 32-bit ABI `armeabi-v7a,armeabi`, kernel `armv7l`.
- `/proc/meminfo` reports 1,048,576 kB total RAM (1 GiB).
- Data filesystem: about 4.0 GB, 1.5 GB available after the initial Termux setup.
- Python 3.14.8 and OpenSSH 10.6p1 work in Termux.
- Both known bulb TCP ports are reachable directly from the box.

Created `~/.smart-bulb-bridge/venv` on the box and installed the same pinned
`flux-led==1.2.0`, `async-timeout==5.0.1` and `webcolors==25.10.0` dependencies.
Installed a read-only client under `~/.smart-bulb-bridge/read-bulbs.py`; it only
targets the two known addresses, binds to the box's LAN source address, permits
only the `818a8b96` query and validates the upstream framing/checksum.

Both bulbs returned valid state: on, CCT/white, 100.0%, nominal 3982 K, model
0x35/version byte 10. Each received only one read-only query. No light state was
changed. The temporary Mac HTTP bootstrap server has been stopped. The Termux
SSH server remains foreground-only; no automatic startup was installed.

From the Mac, `./tvbox status` runs the status query **on the TV box**, and
`./tvbox inspect` repeats read-only hardware inspection. Termux must stay open
with the SSH server running. The SSH key currently allows only the Mac source IP
`192.168.1.141`; a later DHCP change requires deliberate configuration update.

Current Home Assistant releases no longer support 32-bit ARM. Therefore this
box is not a supported host for the planned full Home Assistant container. The
successful lightweight bulb client can serve as a foundation for a smaller
agent, but the Google cloud bridge, authentication, hosting and unattended
reliability are not implemented or proven on it. Keep the supported Mac/Docker
prototype separate from this finding; do not claim it has been migrated.

Evidence: [hardware inspection](ssh-hardware-inspection.json),
[box-to-bulb queries](box-bulb-status.json),
[dependency installation log](bulb-client-install.log).
Source: [Home Assistant 32-bit support removal](https://www.home-assistant.io/blog/2025/12/03/release-202512/).

## Termux installed — temporary SSH prepared

The user reports Termux is installed and running on the box. Prepared a
project-specific Ed25519 client key in ignored `tv-box-install/private/` and a
temporary bootstrap server at the current Mac HomeWiFi address
`http://192.168.1.141:8765/setup`. It serves only the bootstrap script to the known
box IP `192.168.1.199` or the Mac itself; it does not expose project files.

The script installs the official Termux `openssh` and `python` packages, creates
an isolated SSH configuration under `~/.smart-bulb-bridge`, and runs SSH in the
foreground on port 8022 bound to the box's LAN IP. Only the prepared Mac public
key from the current Mac LAN IP is allowed; passwords, keyboard authentication
and forwarding are disabled. No automatic startup is registered and existing
SSH configuration/authorized keys are not modified. The private client key stays
on the Mac. The user must run the supplied command inside Termux; at this point
the script has only been prepared and validated on the Mac. Stop the temporary
HTTP server once the TV box has fetched the script and no longer needs it.

## Installer transfer drive prepared — 2026-10-29

The Toshiba USB drive enumerated as a USB device but never appeared as a disk;
it was not modified. The user explicitly confirmed that the old Seagate macOS
data was disposable and authorized reformatting that drive for the TV box.

Reverified the external USB Seagate BUP Slim Mac SL (2,000,398,933,504 bytes) and
its original Seagate volume UUID immediately before erasing it. Reformatted the
whole Seagate as MBR with one FAT32 volume named `TVBOX`. Verified the resulting
partition map and filesystem. Copied the stable Termux APK, README, source/hash
manifest and optional read-only inspection script to its root; all four copied
files matched their source SHA256 checksums. The drive was safely ejected.
Android mounting and APK installation on the actual box remain untested.

The drive reformat and transfer reports were omitted from this public copy.

Evidence checked 2026-10-28 (Asia/Dubai), from the user's Downloads photos.
The photos and their hash record are omitted from this public copy.

- SSID: HomeWiFi.
- IPv4: `192.168.1.199`; Wi-Fi MAC `xx:xx:xx:xx:xx:xx`.
- Reported model/device name: `android tv` (generic; manufacturer/chipset unknown).
- Reported Android version: `9.0`.
- Reported Android security patch: `July 5, 2025`.
- Kernel: `4.9.118 #172 Sat Nov 22 17:25:34 CST 2025`.
- Build: `eng.dell.20251122.171722`. This string does not establish Dell hardware.
- CPU architecture, RAM, storage, certification and background process behavior
  have not been measured. Device-reported metadata has not been independently
  verified with Android system properties.

Direct LAN connection checks on the identified IP returned connection refused for
TCP 5555 (ADB), 6466 (Android TV remote), 8009 (Cast) and 22 (SSH). Service browsing
also found no Android TV/Cast/ADB announcements during the brief observation.
The device is reachable, but no usable remote management connection was found.

Android 9 is within Termux's documented Android 7+ support range:
[Termux](https://github.com/termux/termux-app). This makes a reversible native
Android proof of concept plausible; it does not establish that a Matter bridge
will run reliably. The existing bulb controller also has macOS-specific route,
interface and socket code that must be adapted before use on Android.

Home Assistant's standard server installation options do not include native
Android. Matterbridge officially supports Linux/macOS/Windows; Android remains
an experiment, including checking Node/native dependency compatibility and
multicast/IPv6 behavior. No installation or firmware change has been attempted.

Next: open Developer options by selecting About → Build seven times, then inspect
the available debugging options. Remote debugging grants shell/app-install
access; any connection should be explicitly authorized by the user for this Mac.
Android 9 does not have the modern Android 11+ wireless pairing workflow, so do
not assume that newer phone instructions apply. If no suitable network debugging
option exists, evaluate a supported USB data connection or an on-device Termux
installation instead. Do not connect an arbitrary USB-A-to-USB-A cable.

References:

- [Android developer options](https://developer.android.com/studio/debug/dev-options).
- [Android Debug Bridge](https://developer.android.com/tools/adb).
- [Matterbridge supported platforms](https://github.com/Luligu/matterbridge).

The box's role would be a bridge host, not an assumed Google Home Matter hub.
Which Google/Nest hub is available remains unanswered. No Google integration
has been installed or paired yet.

## Developer-options photos — 23:03

Inspected `IMG_1138.HEIC` through `IMG_1145.HEIC` (photos not included in this public copy). Developer options are enabled.
USB debugging is available and off. No separate network/ADB-over-network option
is visible in the supplied photos. Stay awake is off, Don't keep activities is
off, and Background process limit is Standard limit. No setting was changed by
the agent.

Next practical check: the user may enable USB debugging to authorize a developer
connection, after understanding that ADB permits shell commands and app installs.
Then check TCP 5555 on this single known IP again. Some vendor firmware may link
the toggle to network ADB, but this has not been established for this box. If it
remains closed, use a verified USB device/OTG data port and suitable cable, or
install Termux on-device. Modern wireless-pairing instructions are not applicable
to the reported Android 9 version.

## USB debugging enabled by the user

The user enabled USB debugging. A new direct TCP connection attempt to
`192.168.1.199:5555` still returned `ECONNREFUSED`. This toggle did not expose the
standard network ADB listener. No ADB connection, shell, app installation or box
configuration change was performed by the agent. Next connection options are a
verified device/OTG USB data port, or an on-device Termux installation followed by
an explicitly authorized SSH setup. Physical port capabilities remain unknown.

## Google Home topology clarification

The user confirmed the only Google Home controller is the iPhone app; there are
no other Google/Nest devices. Google's current Matter setup documentation requires
a Matter-enabled Google Home hub, in addition to the phone. The Android box has
not been established as such a hub, so a Matter bridge on the box alone would not
complete the integration: https://support.google.com/googlehome/answer/13127223?hl=en

A cloud-linked integration can work through the Google Home mobile app without
adding a Google speaker/display. Home Assistant Cloud/Nabu Casa is the standard
Home Assistant route. Homebridge Google Smart Home (`homebridge-gsh`) is another
documented route that supports light on/off, brightness and hue/saturation, but
requires a subscription (since May 2025; new-user trial documented as 7 days).
Its documented light list does not explicitly promise white-temperature support.
It also needs Homebridge Config UI and accessory-control mode. Neither that
stack's Android compatibility nor its connection to these bulbs is verified.

Sources checked 2026-10-28:

- https://support.nabucasa.com/hc/en-us/articles/25619376817053-Google-Assistant
- https://github.com/homebridge-plugins/homebridge-gsh

No subscription, external account linking, bridge installation or Matter pairing
has been performed. Select cloud linking versus purchasing a compatible hub
before further box setup. The already verified local bulb controller continues
to work independently of that choice.


## USB storage route

The user reports two USB-A ports (rear and side), and the Getting Started manual
explains external-storage access using flash drives. This establishes a practical
APK transfer option without proving USB-device/OTG connectivity. A stable,
universal F-Droid Termux installer and install instructions are prepared
under `../../tv-box-install/`; the APK download and ZIP integrity checks passed.
Its source and transfer checksum are saved alongside it. No flash drive was mounted on the Mac when checked.
No APK has been installed on the box, and no remote-access service has been set up.
