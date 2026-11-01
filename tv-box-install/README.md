# Termux installation packet for the Android TV box

Prepared 2026-10-28. Box: reported Android 9, HomeWiFi IP `192.168.1.199`.
This is a compatibility test, not an installed Google Home bridge.

## Files

- `Termux-0.118.3-fdroid.apk`: the suggested stable universal APK from the
  official [F-Droid Termux page](https://f-droid.org/en/packages/com.termux/).
  Supports Android 7+. Universal avoids guessing the box's CPU architecture.
- `installer-source.json`: source URL, size, SHA256 and verification limits.
- `inspect-box.sh`: optional read-only device-information commands, for later use
  once transferring/running files inside Termux is convenient. It does not start
  services, install packages, change settings, or contact bulbs.

## Install with a flash drive

1. Copy the APK to an existing flash drive. No formatting is required as part
   of this procedure. If Android cannot read it, stop and inspect the filesystem
   rather than erasing the drive.
2. Safely eject it from the Mac and plug it into one of the box's USB-A ports.
3. Open **HiFileManager**, which is visible in the supplied TV photos. Browse
   to the USB drive and select the APK.
4. If Android asks, allow **HiFileManager** to install apps from this source,
   then install this Termux APK. That permission allows the file manager to
   request APK installs; it can be revoked after this installation.
5. Open Termux. If it is not shown in the TV launcher, try Settings → Apps →
   Termux → Open. Allow its first-run base environment initialization to finish.
6. A USB keyboard is useful for the terminal. First try these short read-only
   commands and report the output:

   ```sh
   getprop ro.product.cpu.abilist
   getprop ro.build.version.sdk
   uname -m
   ```

If installation fails or the terminal does not open, report the exact error;
do not replace it with an APK from an unrelated site. Use F-Droid consistently
for future Termux app/plugins because builds from different sources have
different signing keys. This packet does not require installing the F-Droid
client itself.

The manual's external-storage instructions establish USB-host/storage support,
not USB-device/OTG support for connecting this box to a Mac. Do not assume a
USB-A port is a supported debugging/data input.

## What this establishes

A functioning Termux terminal lets us inspect the CPU ABI and available
resources, then test a portable bulb client. Remote SSH access and unattended
startup have not been configured. USB debugging is not needed for this APK
installation method; the user may switch it off if no longer using ADB.

Google Home on the iPhone alone still requires a cloud-linked integration for
the proposed setup, or a separate compatible Google Matter hub for the Matter
route. This APK does not add either integration. Android hosting compatibility
and long-running reliability remain unverified. No subscription has been chosen.
