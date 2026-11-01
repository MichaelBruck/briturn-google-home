# Findings — 2026-10-28, Asia/Dubai

## Result

**Both bulbs identified and queried locally after switching the Mac to
HomeWiFi. The first local white/brightness write succeeded at 22:38.** The earlier failure was while the Mac
was on the separate Xiaomi/guest subnet. See the dated follow-up below; earlier
observations are retained as chronology, not the current result.

The bulb specifications, Briturn pairing and OAuth HTTP 500/connection timeout
are user-provided context, not reverified here. The Amazon short link could not
be retrieved by the research tool; the retail listing therefore did not establish
protocol compatibility.

## Upstream inspection

- [flux_led](https://github.com/lightinglibs/flux_led) is the current destination
  of the supplied Danielhiversen URL. Its default branch has extensive model,
  version and protocol handling and a 2026-07-02 latest commit in the fetched
  snapshot. The installed PyPI release is 1.2.0; its actual installed discovery,
  query, checksum and initialization code was inspected separately. Current
  upstream contains changes not present in that release.
- [ha-briturn](https://github.com/jamesrom/ha-briturn) is a single-commit integration
  snapshot dated 2026-04-20. Its tested example is a different Amazon bulb,
  model byte 0x35; that does not establish the identity of SKY-TOUCH hardware.
  Its source constructs the same 2014 state query but its parser does not enforce
  the reply checksum. This project does enforce that checksum.
- [zengge-lightcontrol](https://github.com/vikstrous/zengge-lightcontrol) supplies
  historical protocol documentation; the fetched latest commit is 2020-05-09.
  It is a reference rather than the selected runtime.
- [Home Assistant's Magic Home documentation](https://www.home-assistant.io/integrations/flux_led/)
  describes local control and discovery for compatible hardware. No Home Assistant
  installation was performed.

Pinned commits and package versions: [upstream-versions.json](../research/upstream-versions.json).
Source reference clones: `../research/upstream/`.

Verified in `flux_led/protocol.py`: `ProtocolLEDENET8Byte.construct_state_query`
constructs `81 8A 8B` and `construct_message` appends `sum(bytes) & 0xFF`, yielding
`96`. Standard replies are 14 bytes, start with `81`, and pass the library checksum
validator. The model is at offset 1, power at 2, RGB at 6–8, WW at 9, version at
10, CW at 11, mode at 12, checksum at 13. The 9-byte levels protocol includes
separate warm/cool channels and an RGB/white write mask. These rules were verified
before any candidate query could be sent.

## LAN observations

- Active default route: `en0` (Wi-Fi), gateway `192.168.3.1`.
- Mac IPv4: `192.168.3.120`, mask `255.255.255.0`.
- Directly connected subnet: `192.168.3.0/24`; broadcast `192.168.3.255`.
- Other physical interfaces were inactive; VPN `utun*` interfaces were excluded.
- Initial ARP neighbors included `.1`, `.100`, `.103`, `.145`. None was assumed
  to be a bulb.
- Router ping succeeded: about 3 ms.
- Upstream UDP discovery, bound to `en0`/its source IPv4, ran for 8 seconds against
  `192.168.3.255:48899`; **zero replies**.
- Initial TCP 5577-only fallback across 253 remote LAN hosts with 0.6-second
  timeout found no open listener. All timed out, so this result was treated as
  potentially too short for ARP resolution rather than definitive.
- Follow-up 3-second direct TCP checks, with and without interface/source binding,
  returned `ECONNREFUSED` from `.100`, `.103`, `.145`. Router TCP 80 timed out;
  no assumption is made that router HTTP should be enabled.
- Direct UDP discovery to `.100`, `.103`, `.145` (3 seconds each) returned no
  replies. Ping to each succeeded (about 113, 89 and 98 ms respectively).
- Repeated TCP 5577-only fallback with 2-second timeout: **0 open**, 3 refused
  (`.100`, `.103`, `.145`), 250 timed out. No TCP application payload was sent
  because there were no open listeners. In particular no `81 8A 8B 96` requests
  reached a candidate during this run.

Raw reports:

- [UDP discovery](discovery-20261028-215824.json)
- [Initial TCP fallback](tcp5577-20261028-215900.json)
- [Bound/unbound connectivity comparison](connectivity.json)
- [Longer TCP fallback](tcp5577-20261028-220513.json)

## Permissions, isolation, compatibility — distinguish the evidence

1. **Execution sandbox:** initial `route`/`networksetup` commands failed with
   sandbox permission errors. Authorized checks were rerun outside that sandbox.
   The local loopback test also required an authorized network-capable execution.
   Those failures are not evidence of bulb or router behavior.
2. **macOS Local Network privacy:** read the actual System Settings → Privacy &
   Security → Local Network page. ChatGPT, node and Terminal were enabled. No
   Codex-labelled or Python-labelled entry was visible; the exact responsible
   process attribution was not independently established. No settings were
   changed. A narrow recent network-denial log search returned no matching
   messages, which does not prove absence of all privacy restrictions. Python
   received TCP refusals from three LAN peers, establishing that it can exchange
   traffic with those peers; a blanket local-network denial is unlikely.
3. **Network isolation:** the three peers' ping responses and TCP refusals show
   that complete peer isolation is not present between the Mac and those IPs.
   Bulb-specific isolation, another SSID/VLAN, powered-off bulbs, or bulbs on a
   different address range remain possible. Router reachability alone would not
   exclude those conditions.
4. **Protocol compatibility:** closed 5577 on unidentified peers says nothing
   conclusive about the bulbs. No valid Zengge discovery response or state reply
   was observed. Do not label SKY-TOUCH unsupported until a known bulb IP is tested.

## Initial next steps (resolved by the follow-up below)

Determine how many bulbs currently have mains power and whether Briturn's
device-information screen exposes an IP address. This was requested from the user.
If a known bulb IP is inside the current `/24`, run direct read-only discovery and
status using the README commands. If the app reports another subnet, establish
where the bulb is connected before considering network changes; this project
deliberately refuses to probe another subnet automatically. A known bulb that
is reachable but refuses 5577 would materially strengthen the alternate-protocol
hypothesis. If a normal Terminal run succeeds while this execution path fails,
investigate process-specific Local Network permissions instead.

The initial CLI allowed only 9-byte control variants. The discovered bulbs select
the library's 25-byte variant, which is now enabled and tested as described below.

## Initial verification

Seven offline tests passed, including subnet restrictions, invalid/truncated
state checksums, refusal of non-query frames on read-only connections, unknown
model rejection, library-generated white framing, temperature reporting and a
temporary loopback mock returning a fragmented response to the exact query.
All synthetic responses are test fixtures, not bulb observations.

## Follow-up — 22:33 onward, HomeWiFi LAN

The user confirmed two bulbs have mains power and pointed to screenshots in
Downloads. Read only the six newly added bulb-related screenshots, `IMG_1124.PNG`
through `IMG_1129.PNG`. Extracted evidence and source hashes are recorded in
[screenshot-evidence.json](screenshot-evidence.json). Virtual IDs were unnecessary
and are omitted from the extracted record.

Screenshots show:

- Tripod lamp: `192.168.1.172`, device/discovery ID `0865F0AAAAAA`.
- Reading Lamp: `192.168.1.195`, device/discovery ID `0865F0BBBBBB`.
- Firmware text: `WF.4C.35.286.0,V10_ZG-BK38-BP101`.
- The app's network diagnostics name `HomeWiFi`; app-reported Local and Cloud
  status were Online. These are screenshot observations, not independent tests
  of every app claim.
- The remote-control setting concerns Bluetooth remote controls/control panels,
  as stated on that screen. It is not evidence of a Wi-Fi/cloud permission and
  was not changed.

System Settings then showed the Mac connected to `GuestWiFi`, with HomeWiFi
available as a known network. The user confirmed the former is the Xiaomi SSID
and switched the Mac to HomeWiFi. No network settings were changed by the agent.

Verified after that switch:

- Mac `192.168.1.127/24`, `en0`; gateway `192.168.1.1`.
- Upstream broadcast discovery on `192.168.1.255:48899` found exactly two devices.
- Their returned discovery IDs exactly match the screenshots.
- Both returned `AK001-ZJ21413`, model `0x35` (Bulb RGBCW).
- Raw version reply for both: `+ok=35_286_20250619_ZG-BK38-BP101\r`.
  The library parses its version token as hexadecimal, reporting decimal 646
  (`0x286`); do not confuse that parser output with the separate state version
  byte `0x0A` (10) or the app's complete firmware string.
- Both returned firmware date `2025-06-19`, model info `ZG-BK38-BP101`.
- Both still report their existing cloud endpoint configured; it was queried
  but not disabled or changed. Local query success does not depend on OAuth.

| Bulb | IP | On | Mode | Intensity proxy | Nominal white K | WW / CW bytes |
| --- | --- | --- | --- | --- | --- | --- |
| Tripod lamp | 192.168.1.172 | Yes | CCT/white | 95.7% | 2871 | 233 / 11 |
| Reading Lamp | 192.168.1.195 | Yes | CCT/white | 98.8% | 2700 | 252 / 0 |

Brightness and Kelvin are the upstream library's interpretation of state bytes,
not measurements of emitted light. Both devices report RGB and CCT capabilities.
Both RGB channel triples currently read `0,0,0`.

Standard responses, checksum validated:

- Tripod: `81 35 23 61 30 50 00 00 00 E9 0A 0B 0F C7`.
- Reading: `81 35 23 61 30 50 00 00 00 FC 0A 00 0F CF`.

The upstream model/version table selects `LEDENET_25_BYTE` from the live model
and version byte. Inspected that installed implementation before enabling it:
color/white commands use the `B0 B1 B2 B3` wrapper, version 2, counter and payload
length, with outer sum-of-prior-bytes checksum. The payload uses HSV for RGB and
temperature/brightness percentages for white, with `0xA1` / `0xB1` mode masks.
Power commands and state queries retain their existing checksum-based frames.
The controller uses the library to generate these frames; no protocol was
reimplemented. Tests verify selected frame length, wrapper fields, mask,
temperature/intensity and checksum without sending them to a bulb.

ARP separately showed actual Wi-Fi MAC addresses `08:65:f0:aa:aa:ab` (Tripod)
and `08:65:f0:bb:bb:bc` (Reading). Those differ from the discovery IDs by one in
the last byte. Record both observations; do not claim they are the same MAC or
infer why the firmware uses separate identifiers. The write path performs a direct read-only UDP discovery and checks the device
ID against the app screenshot. An ARP-based guard was replaced because `arp`
launched from Python inconsistently returned “no entry” despite the shell showing
the entries. The device discovery ID avoids that platform-dependent behavior.
Unicast discovery also waits for the identity reply rather than finishing early
after version/cloud replies.

New reports:

- [Successful discovery and live states](discovery-20261028-223314.json).
- [Direct queries to screenshot-identified bulbs](known-bulbs-20261028-223323.json).
- [Named CLI status and discovery identity verification](verified-cli-status.json).
- [Named device registry](../devices.json).

Current verification: **nine tests pass**. The new checks cover 25-byte framing
using the observed Tripod reply and stale-IP identity rejection. Both named CLI
status commands also passed live, with only state queries sent.

**First visible test, left for the user:** `./bulb tripod white 4000 --brightness 50`.
This changes only the Tripod lamp. Visible control and perception of color/
brightness remain unverified until that command is run and observed. No reset,
firmware change, router change, pairing change, service or Home Assistant install
has been performed.

## First physical control test — 22:38:57–22:38:59

The user asked to run the tests here. All nine automated tests passed, then the
agent ran `./bulb tripod white 4000 --brightness 50` once. Identity verification
passed and the command returned successfully.

Independent fresh status queries before and after showed:

| Bulb | Before | After |
| --- | --- | --- |
| Tripod | On, white, 95.7%, nominal 2871 K; WW/CW 233/11 | On, white, 49.8%, nominal 3987 K; WW/CW 84/43 |
| Reading | On, white, 98.8%, nominal 2700 K; WW/CW 252/0 | Identical state and raw reply |

The requested values were 4000 K and 50%; small differences reflect the device's
quantized state and the library's nominal temperature conversion. Changed raw
state verifies a successful local command, not a direct visual observation by
the agent. User confirmation of the lamp's appearance has not been received.

The first command's immediate output retained slightly optimistic channel values
from the library even after querying. The CLI now creates a new read-only bulb
object for its post-write status so that its output reflects independently read
state. The independent after-query in the saved test report already used that
fresh-object path.

Saved full before/command/after results:
[first-visible-test-20261028-223859.json](first-visible-test-20261028-223859.json).
The lamp is left at its new test setting. RGB, power on/off and standalone
brightness commands remain untested against physical bulbs. No further control
commands were sent during this test.

## Reading Lamp control test — 22:40:21–22:40:23

At the user's request, ran `./bulb reading white 4000 --brightness 50` once.
Its identity check passed and the command succeeded. Fresh queries showed the
Reading Lamp change from 98.8%, nominal 2700 K (WW/CW 252/0) to 49.8%, nominal
3987 K (WW/CW 84/43), still on in white mode. The Tripod lamp's raw state was
identical before and after, confirming it was unaffected. The corrected command
read-back agreed with the independent fresh query.

Both bulbs are left at the test setting. Saved complete results:
[reading-visible-test-20261028-224023.json](reading-visible-test-20261028-224023.json).

## Full brightness — 22:41

At the user's request, ran `brightness 100` for both named lamps, preserving their
white mix. Both commands and independent fresh queries succeeded: on, CCT mode,
100.0%, nominal 3982 K, WW/CW 169/86. The few-Kelvin difference from the prior
setting is channel quantization. Standalone white-mode brightness is now tested
on both bulbs. Results: [full-brightness-20261028-224139.json](full-brightness-20261028-224139.json).
