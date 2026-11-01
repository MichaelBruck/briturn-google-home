# Google Home integration

> **Status 2026-11-01 — project parked, Google Home control working.** This file is a
> checkpoint written 2026-10-30; where it says account linking/consent is pending or
> writes are disabled, that has since been completed. Start from
> [RESUME.md](../RESUME.md).

The active implementation is the [lightweight TV-box gateway](../gateway/README.md).
It can query/control the identified bulbs locally. Its local web gateway and approved temporary HTTPS tunnel are running.
Google Home account-link consent is pending.

Created **My Lights**, project ID `my-lights-project`, on 2026-10-30 under
`you@example.com`, confirmed as the iPhone Google Home account. The Light
integration is saved with its dedicated client credentials, URLs and icon;
[test] My Lights is visible on the iPhone. Actual Google account-link
consent is pending. No HomeGraph service account, paid plan or DNS change.

The earlier Mac/Docker HA plan is preserved in
[HA-PROTOTYPE-2026-10-28.md](HA-PROTOTYPE-2026-10-28.md), beside its compose and
templates. It was not installed or started. It is not the active route: this
32-bit box is unsupported by current Home Assistant.

See [RESUME.md](RESUME.md) for the current checkpoint.
