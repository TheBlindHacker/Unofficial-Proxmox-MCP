#!/usr/bin/env bash
# ==============================================================================
# Unofficial-Proxmox-MCP Proxmox VE Host Turnkey LXC Deployer
# Run this script directly in the Proxmox VE hypervisor host shell.
# ==============================================================================

set -euo pipefail

if ! command -v pveversion >/dev/null 2>&1; then
    echo "ERROR: This script must be run directly on a Proxmox VE hypervisor host." >&2
    exit 1
fi

echo "============================================================"
echo "    Proxmox VE Unofficial-Proxmox-MCP Turnkey Container     "
echo "============================================================"

read -rp "Container VMID [299]: " LXC_ID
LXC_ID=${LXC_ID:-299}

read -rp "Container Hostname [proxmox-mcp]: " LXC_HOSTNAME
LXC_HOSTNAME=${LXC_HOSTNAME:-proxmox-mcp}

read -rp "Target Storage Pool [local-lvm]: " LXC_STORAGE
LXC_STORAGE=${LXC_STORAGE:-local-lvm}

read -rp "Create dedicated Proxmox user 'mcp-bot@pve' with scoped role? (y/n) [y]: " CREATE_USER
CREATE_USER=${CREATE_USER:-y}

if [[ "$CREATE_USER" =~ ^[Yy]$ ]]; then
    echo "[+] Creating scoped role 'PVEMCP'..."
    pveum role add PVEMCP -privs "VM.Audit VM.Console VM.PowerMgmt VM.Config.CPU VM.Config.Memory VM.Config.Disk VM.Config.Network VM.Config.Options VM.Snapshot VM.Snapshot.Rollback VM.Clone VM.Allocate Datastore.Audit Datastore.AllocateSpace Sys.Audit SDN.Audit" 2>/dev/null || true

    echo "[+] Creating user 'mcp-bot@pve'..."
    pveum user add mcp-bot@pve -comment "Dedicated AI Assistant MCP User" 2>/dev/null || true
    pveum acl modify / -user mcp-bot@pve -role PVEMCP

    echo "[+] Generating API token 'mcp-bot@pve!mcp-token'..."
    TOKEN_SECRET=$(pveum user token add mcp-bot@pve mcp-token -privsep 0 2>&1 | grep -oP '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}' || true)
    
    if [ -z "${TOKEN_SECRET:-}" ]; then
        read -rsp "Token already exists or generated earlier. Paste Token Secret UUID: " TOKEN_SECRET
        echo ""
    fi
    LXC_USER="mcp-bot@pve!mcp-token"
    LXC_SECRET="${TOKEN_SECRET}"
else
    read -rp "Proxmox API User [root@pam!mcp]: " LXC_USER
    LXC_USER=${LXC_USER:-root@pam!mcp}
    read -rsp "Proxmox API Token Secret UUID: " LXC_SECRET
    echo ""
fi

read -rp "Protected VM/LXC IDs [100,101,${LXC_ID}]: " LXC_PROTECTED
LXC_PROTECTED=${LXC_PROTECTED:-100,101,${LXC_ID}}

# Ensure Debian 12 template is available
TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
if ! pveam list local | grep -q "$TEMPLATE"; then
    echo "[+] Downloading Debian 12 LXC template to local storage..."
    pveam download local "$TEMPLATE" || true
fi

echo "[+] Creating LXC container ${LXC_ID}..."
pct create "${LXC_ID}" "local:vztmpl/${TEMPLATE}" \
    --hostname "${LXC_HOSTNAME}" \
    --cores 2 \
    --memory 1024 \
    --swap 512 \
    --rootfs "${LXC_STORAGE}:8" \
    --net0 name=eth0,bridge=vmbr0,firewall=1,ip=dhcp \
    --unprivileged 1 \
    --onboot 1 \
    --start 1

echo "[+] Waiting for container networking..."
sleep 8

echo "[+] Installing system dependencies inside container..."
pct exec "${LXC_ID}" -- apt-get update
pct exec "${LXC_ID}" -- apt-get install -y python3 python3-pip python3-venv git curl

echo "[+] Installing unofficial-proxmox-mcp..."
pct exec "${LXC_ID}" -- git clone https://github.com/your-username/Unofficial-Proxmox-MCP.git /opt/unofficial-proxmox-mcp 2>/dev/null || true
if ! pct exec "${LXC_ID}" -- test -d /opt/unofficial-proxmox-mcp; then
    pct exec "${LXC_ID}" -- mkdir -p /opt/unofficial-proxmox-mcp
fi

# Self-Protection marker
pct exec "${LXC_ID}" -- bash -c "echo '${LXC_ID}' > /etc/pve-self-vmid"

# Write configuration
pct exec "${LXC_ID}" -- bash -c "cat << 'EOF' > /opt/unofficial-proxmox-mcp/.env
PVE_HOST=127.0.0.1
PVE_PORT=8006
PVE_USER=${LXC_USER}
PVE_TOKEN_SECRET=${LXC_SECRET}
PVE_VERIFY_SSL=false
PVE_SELF_VMID=${LXC_ID}
PVE_PROTECTED_VMIDS=${LXC_PROTECTED}
MCP_TRANSPORT=sse
MCP_HOST=0.0.0.0
MCP_PORT=8000
EOF"

pct exec "${LXC_ID}" -- chmod 600 /opt/unofficial-proxmox-mcp/.env
pct exec "${LXC_ID}" -- python3 -m venv /opt/unofficial-proxmox-mcp/.venv
pct exec "${LXC_ID}" -- /opt/unofficial-proxmox-mcp/.venv/bin/pip install --upgrade pip
pct exec "${LXC_ID}" -- /opt/unofficial-proxmox-mcp/.venv/bin/pip install mcp proxmoxer requests urllib3 pydantic python-dotenv

# Systemd Daemon
pct exec "${LXC_ID}" -- bash -c "cat << 'EOF' > /etc/systemd/system/unofficial-proxmox-mcp.service
[Unit]
Description=Unofficial Proxmox MCP SSE Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/unofficial-proxmox-mcp
EnvironmentFile=/opt/unofficial-proxmox-mcp/.env
ExecStart=/opt/unofficial-proxmox-mcp/.venv/bin/python3 -m unofficial_proxmox_mcp --transport sse --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

pct exec "${LXC_ID}" -- systemctl daemon-reload
pct exec "${LXC_ID}" -- systemctl enable --now unofficial-proxmox-mcp

LXC_IP=$(pct exec "${LXC_ID}" -- ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "UNKNOWN")

echo "============================================================"
echo "Unofficial-Proxmox-MCP LXC is live!"
echo "Endpoint        : http://${LXC_IP}:8000/sse"
echo "Self-Protection : Enabled (VMID ${LXC_ID} protected against deletion/power-off)"
echo "============================================================"
