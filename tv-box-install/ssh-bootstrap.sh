#!/data/data/com.termux/files/usr/bin/bash
# Installs a temporary, project-specific SSH endpoint; no startup registration.
set -euo pipefail
case "${PREFIX:-}" in
  */com.termux/files/usr) ;;
  *) echo 'Run this inside the Termux app.'; exit 1 ;;
esac

printf '\nPreparing key-only access from your Mac to this Termux environment.\n'
pkg install -y openssh python

bridge_dir="$HOME/.smart-bulb-bridge"
mkdir -p "$bridge_dir"
chmod 700 "$bridge_dir"
umask 077
printf '%s\n' 'from="__MAC_IP__" __AUTHORIZED_KEY__' > "$bridge_dir/mac-authorized-key"
if [ ! -f "$bridge_dir/ssh_host_ed25519_key" ]; then
  ssh-keygen -q -t ed25519 -N '' -f "$bridge_dir/ssh_host_ed25519_key"
fi

cat > "$bridge_dir/sshd_config" <<EOF
Port 8022
AddressFamily inet
ListenAddress __BOX_IP__
HostKey $bridge_dir/ssh_host_ed25519_key
PidFile $bridge_dir/sshd.pid
AuthorizedKeysFile $bridge_dir/mac-authorized-key
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
PermitRootLogin no
AllowUsers $(whoami)
AllowTcpForwarding no
AllowAgentForwarding no
X11Forwarding no
UseDNS no
PrintMotd no
Subsystem sftp internal-sftp
EOF

sshd -t -f "$bridge_dir/sshd_config"
printf '\nREADY: %s@__BOX_IP__:8022\n' "$(whoami)"
printf 'Host key fingerprint:\n'
ssh-keygen -lf "$bridge_dir/ssh_host_ed25519_key.pub"
printf '\nKeep Termux open. This server has no automatic startup.\n'
printf 'Ctrl+C stops this temporary SSH server.\n\n'
exec sshd -D -e -f "$bridge_dir/sshd_config"
