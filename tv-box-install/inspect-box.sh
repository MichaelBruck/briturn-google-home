#!/system/bin/sh
# Read-only. No package installation, settings changes or network connections.
printf 'Model: '; getprop ro.product.model
printf 'Manufacturer: '; getprop ro.product.manufacturer
printf 'Android release: '; getprop ro.build.version.release
printf 'SDK: '; getprop ro.build.version.sdk
printf 'Supported ABIs: '; getprop ro.product.cpu.abilist
printf 'Hardware: '; getprop ro.hardware
printf 'Board: '; getprop ro.product.board
printf 'Kernel architecture: '; uname -m
printf 'Memory: '; awk '/^MemTotal:/ {print $2, $3}' /proc/meminfo
printf 'Termux storage:\n'; df -h "${HOME:-/data/local/tmp}"
