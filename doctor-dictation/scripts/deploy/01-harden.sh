#!/usr/bin/env bash
# Run as root on a fresh Ubuntu 24.04 VPS.
#   Stage 1:  bash 01-harden.sh             user, firewall, fail2ban, auto-updates, Docker
#   Stage 2:  bash 01-harden.sh --lock-ssh  turn off root and password logins
# Run stage 2 ONLY after `ssh deploy@<ip>` works from your Mac, or you lock yourself out.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run as root." >&2; exit 1; }
DEPLOY_USER=${DEPLOY_USER:-deploy}

if [ "${1:-}" = "--lock-ssh" ]; then
  [ -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ] || { echo "No SSH key for $DEPLOY_USER; not locking." >&2; exit 1; }
  # 00- sorts first and sshd keeps the FIRST value it sees, so this beats cloud-init's 50-cloud-init.conf.
  cat > /etc/ssh/sshd_config.d/00-hardening.conf <<CONF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
CONF
  sshd -t
  systemctl reload ssh
  echo "SSH locked: root login and passwords are off. Keep this terminal open and test a NEW login as $DEPLOY_USER."
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y upgrade
apt-get -y install ufw fail2ban unattended-upgrades ca-certificates curl gnupg age

# Normal user with the same SSH key as root (the key you added in Hostinger).
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"
echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$DEPLOY_USER"   # no password exists; Docker access is root-equivalent anyway
chmod 440 "/etc/sudoers.d/90-$DEPLOY_USER"

# Firewall. Docker publishes 80/443 itself; the app port is loopback-only (docker-compose.yml).
ufw default deny incoming
ufw default allow outgoing
ufw limit 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

systemctl enable --now fail2ban
cat > /etc/apt/apt.conf.d/20auto-upgrades <<CONF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF

# Docker Engine and the compose plugin from Docker's own repository.
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "$DEPLOY_USER"
systemctl enable --now docker

echo
echo "Stage 1 done. Next, from your Mac:  ssh -i ~/.ssh/id_ed25519_dictdoc_vps $DEPLOY_USER@<server-ip>"
echo "When that works, run on the server as root:  bash 01-harden.sh --lock-ssh"
