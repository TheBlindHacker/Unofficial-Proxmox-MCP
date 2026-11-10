#!/usr/bin/env bash
# ==============================================================================
# Unofficial-Proxmox-MCP Universal Interactive Installer
# Supports:
#   1) Local Machine Installation (uv / pip / Claude / Antigravity / Cursor)
#   2) Docker / Docker Compose Deployment (SSE Transport)
#   3) Proxmox VE Host Turnkey LXC Container (with auto-self-protection & user creation)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}     Unofficial-Proxmox-MCP Universal Installer 🚀          ${NC}"
echo -e "${BLUE}============================================================${NC}"

# Detect if executing directly on a Proxmox VE hypervisor host
IS_PVE_HOST=false
if command -v pveversion >/dev/null 2>&1; then
    IS_PVE_HOST=true
    echo -e "${GREEN}[+] Running directly on Proxmox VE Hypervisor Host!${NC}"
fi

create_dedicated_pve_user() {
    echo -e "\n${BLUE}--- [Security Wizard: Dedicated Least-Privilege MCP User] ---${NC}"
    echo -e "Best security practice is running an isolated service account (e.g. mcp-bot@pve)"
    echo -e "instead of granting full root@pam access to AI models.\n"

    read -rp "Create dedicated Proxmox API user and scoped role now? (y/n) [y]: " CREATE_USER
    CREATE_USER=${CREATE_USER:-y}

    if [[ "$CREATE_USER" =~ ^[Yy]$ ]]; then
        if [ "$IS_PVE_HOST" = true ]; then
            ROLE_NAME="MCPAgent"
            BOT_USER="mcp-bot@pve"
            TOKEN_ID="mcp-token"

            echo -e "${BLUE}[+] Creating scoped PVE Role '${ROLE_NAME}'...${NC}"
            pveum role add "${ROLE_NAME}" --privs "VM.Audit,VM.Console,VM.PowerMgmt,VM.Config.CPU,VM.Config.Memory,VM.Config.Disk,VM.Config.Network,VM.Config.Options,VM.Snapshot,VM.Snapshot.Rollback,VM.Clone,VM.Allocate,Datastore.Audit,Datastore.AllocateSpace,Sys.Audit,SDN.Audit" 2>/dev/null || true

            echo -e "${BLUE}[+] Creating PVE User '${BOT_USER}'...${NC}"
            pveum user add "${BOT_USER}" -comment "Dedicated AI Assistant MCP Service Account" 2>/dev/null || true

            echo -e "${BLUE}[+] Assigning ACL permissions (/ -> ${ROLE_NAME})...${NC}"
            pveum acl modify / --users "${BOT_USER}" --roles "${ROLE_NAME}"

            echo -e "${BLUE}[+] Generating API Token '${BOT_USER}!${TOKEN_ID}'...${NC}"
            # Extract token secret
            TOKEN_OUTPUT=$(pveum user token add "${BOT_USER}" "${TOKEN_ID}" -privsep 0 --output-format json 2>/dev/null || true)
            
            if [ -n "$TOKEN_OUTPUT" ]; then
                TOKEN_SECRET=$(echo "$TOKEN_OUTPUT" | grep -oP '(?<="value":\s*")[^"]+' || true)
            fi

            if [ -z "${TOKEN_SECRET:-}" ]; then
                # Fallback non-json parse
                TOKEN_SECRET=$(pveum user token add "${BOT_USER}" "${TOKEN_ID}" -privsep 0 2>&1 | grep -oP '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}' || true)
            fi

            if [ -n "${TOKEN_SECRET:-}" ]; then
                echo -e "${GREEN}[+] Successfully generated API Token Secret!${NC}"
                PVE_USER="${BOT_USER}!${TOKEN_ID}"
                PVE_TOKEN_SECRET="${TOKEN_SECRET}"
            else
                echo -e "${YELLOW}[!] User and Role created, but token secret was already generated or requires manual input.${NC}"
                read -rsp "Paste Token Secret UUID: " PVE_TOKEN_SECRET
                echo ""
                PVE_USER="${BOT_USER}!${TOKEN_ID}"
            fi
        else
            echo -e "${YELLOW}To create a dedicated user on your Proxmox host, run these commands in the Proxmox Shell:${NC}"
            echo -e "------------------------------------------------------------"
            echo "pveum role add MCPAgent --privs 'VM.Audit,VM.Console,VM.PowerMgmt,VM.Config.CPU,VM.Config.Memory,VM.Config.Disk,VM.Config.Network,VM.Config.Options,VM.Snapshot,VM.Snapshot.Rollback,VM.Clone,VM.Allocate,Datastore.Audit,Datastore.AllocateSpace,Sys.Audit,SDN.Audit'"
            echo "pveum user add mcp-bot@pve -comment 'AI MCP Service Account'"
            echo "pveum acl modify / --users mcp-bot@pve --roles MCPAgent"
            echo "pveum user token add mcp-bot@pve mcp-token -privsep 0"
            echo -e "------------------------------------------------------------"
            read -rp "Proxmox API User [mcp-bot@pve!mcp-token]: " PVE_USER
            PVE_USER=${PVE_USER:-mcp-bot@pve!mcp-token}
            read -rsp "Enter Generated Token Secret UUID: " PVE_TOKEN_SECRET
            echo ""
        fi
    else
        read -rp "Proxmox API User [root@pam!mcp]: " PVE_USER
        PVE_USER=${PVE_USER:-root@pam!mcp}
        read -rsp "Proxmox Token Secret UUID: " PVE_TOKEN_SECRET
        echo ""
    fi
}

prompt_env_vars() {
    if [ ! -f "${SCRIPT_DIR}/.env" ]; then
        echo -e "\n${YELLOW}[!] Configuring Proxmox Connection Settings:${NC}"
        read -rp "Proxmox Host / IP [127.0.0.1]: " PVE_HOST
        PVE_HOST=${PVE_HOST:-127.0.0.1}

        read -rp "Proxmox Port [8006]: " PVE_PORT
        PVE_PORT=${PVE_PORT:-8006}

        create_dedicated_pve_user

        read -rp "Verify SSL certificates? (true/false) [false]: " PVE_VERIFY_SSL
        PVE_VERIFY_SSL=${PVE_VERIFY_SSL:-false}

        read -rp "Protected VM/LXC IDs (comma-separated, cannot be deleted) [100,101]: " PVE_PROTECTED
        PVE_PROTECTED=${PVE_PROTECTED:-100,101}

        cat <<EOF > "${SCRIPT_DIR}/.env"
PVE_HOST=${PVE_HOST}
PVE_PORT=${PVE_PORT}
PVE_USER=${PVE_USER}
PVE_TOKEN_SECRET=${PVE_TOKEN_SECRET}
PVE_VERIFY_SSL=${PVE_VERIFY_SSL}
PVE_PROTECTED_VMIDS=${PVE_PROTECTED}
MCP_TRANSPORT=stdio
MCP_HOST=0.0.0.0
MCP_PORT=8000
EOF
        # Set strict secure permissions on credentials file
        chmod 600 "${SCRIPT_DIR}/.env"
        echo -e "${GREEN}[+] Created ${SCRIPT_DIR}/.env with strict 0600 permissions.${NC}"
    else
        echo -e "${GREEN}[+] Found existing ${SCRIPT_DIR}/.env configuration.${NC}"
    fi
}

install_local() {
    echo -e "\n${BLUE}--- [Mode 1: Local Python Environment Installation] ---${NC}"
    prompt_env_vars

    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}[!] python3 is required but not installed.${NC}"
        exit 1
    fi

    VENV_DIR="${SCRIPT_DIR}/.venv"
    if [ ! -d "${VENV_DIR}" ]; then
        echo -e "${BLUE}[+] Creating Python virtual environment in ${VENV_DIR}...${NC}"
        python3 -m venv "${VENV_DIR}"
    fi

    echo -e "${BLUE}[+] Installing unofficial-proxmox-mcp and dependencies...${NC}"
    "${VENV_DIR}/bin/pip" install --upgrade pip
    "${VENV_DIR}/bin/pip" install -e "${SCRIPT_DIR}"

    echo -e "\n${GREEN}[+] Installation complete! Running pre-flight diagnostic check...${NC}"
    "${VENV_DIR}/bin/unofficial-proxmox-mcp" --check || true

    echo -e "\n${GREEN}============================================================${NC}"
    echo -e "${GREEN}Claude Desktop Configuration Snippet (claude_desktop_config.json):${NC}"
    cat <<EOF
{
  "mcpServers": {
    "proxmox": {
      "command": "${VENV_DIR}/bin/unofficial-proxmox-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "PVE_HOST": "$(grep PVE_HOST "${SCRIPT_DIR}/.env" | cut -d= -f2)",
        "PVE_USER": "$(grep PVE_USER "${SCRIPT_DIR}/.env" | cut -d= -f2)",
        "PVE_TOKEN_SECRET": "$(grep PVE_TOKEN_SECRET "${SCRIPT_DIR}/.env" | cut -d= -f2)",
        "PVE_VERIFY_SSL": "$(grep PVE_VERIFY_SSL "${SCRIPT_DIR}/.env" | cut -d= -f2)"
      }
    }
  }
}
EOF
    echo -e "${GREEN}============================================================${NC}"
}

install_docker() {
    echo -e "\n${BLUE}--- [Mode 2: Docker / Docker Compose Deployment] ---${NC}"
    prompt_env_vars

    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}[!] docker command not found. Please install Docker first.${NC}"
        exit 1
    fi

    echo -e "${BLUE}[+] Building and launching container...${NC}"
    cd "${SCRIPT_DIR}"
    docker compose down 2>/dev/null || true
    docker compose up -d --build

    echo -e "${GREEN}[+] Unofficial-Proxmox-MCP Docker container is running!${NC}"
    echo -e "    Listening at: http://0.0.0.0:8000/sse"
    echo -e "    Container logs: docker compose logs -f"
}

install_pve_lxc() {
    echo -e "\n${BLUE}--- [Mode 3: Proxmox VE Host Turnkey LXC Container] ---${NC}"
    if [ "$IS_PVE_HOST" = false ]; then
        echo -e "${RED}[!] This mode must be run directly on a Proxmox VE hypervisor host.${NC}"
        exit 1
    fi

    read -rp "Enter new LXC Container ID [299]: " LXC_ID
    LXC_ID=${LXC_ID:-299}

    read -rp "Enter container hostname [proxmox-mcp]: " LXC_HOSTNAME
    LXC_HOSTNAME=${LXC_HOSTNAME:-proxmox-mcp}

    read -rp "Enter storage pool for rootfs [local-lvm]: " LXC_STORAGE
    LXC_STORAGE=${LXC_STORAGE:-local-lvm}

    create_dedicated_pve_user

    TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
    if ! pveam list local | grep -q "$TEMPLATE"; then
        echo -e "${BLUE}[+] Downloading Debian 12 LXC template...${NC}"
        pveam download local "$TEMPLATE" || true
    fi

    echo -e "${BLUE}[+] Creating unprivileged LXC container ${LXC_ID}...${NC}"
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

    echo -e "${BLUE}[+] Waiting for container network initialization...${NC}"
    sleep 8

    echo -e "${BLUE}[+] Provisioning Python & Unofficial-Proxmox-MCP inside LXC ${LXC_ID}...${NC}"
    pct exec "${LXC_ID}" -- apt-get update
    pct exec "${LXC_ID}" -- apt-get install -y python3 python3-pip python3-venv git curl

    pct exec "${LXC_ID}" -- mkdir -p /opt/unofficial-proxmox-mcp
    pct push "${LXC_ID}" "${SCRIPT_DIR}/pyproject.toml" /opt/unofficial-proxmox-mcp/pyproject.toml
    pct push "${LXC_ID}" "${SCRIPT_DIR}/README.md" /opt/unofficial-proxmox-mcp/README.md

    TAR_TMP="/tmp/pve_mcp_src.tar"
    tar -cf "${TAR_TMP}" -C "${SCRIPT_DIR}" src
    pct push "${LXC_ID}" "${TAR_TMP}" /tmp/pve_mcp_src.tar
    rm -f "${TAR_TMP}"
    pct exec "${LXC_ID}" -- tar -xf /tmp/pve_mcp_src.tar -C /opt/unofficial-proxmox-mcp/
    pct exec "${LXC_ID}" -- rm -f /tmp/pve_mcp_src.tar

    # Write self-protection marker inside container
    pct exec "${LXC_ID}" -- bash -c "echo '${LXC_ID}' > /etc/pve-self-vmid"

    # Configure environment with self-protection
    pct exec "${LXC_ID}" -- bash -c "cat << 'EOF' > /opt/unofficial-proxmox-mcp/.env
PVE_HOST=127.0.0.1
PVE_PORT=8006
PVE_USER=${PVE_USER}
PVE_TOKEN_SECRET=${PVE_TOKEN_SECRET}
PVE_VERIFY_SSL=false
PVE_SELF_VMID=${LXC_ID}
PVE_PROTECTED_VMIDS=100,101,${LXC_ID}
MCP_TRANSPORT=sse
MCP_HOST=0.0.0.0
MCP_PORT=8000
EOF"
    pct exec "${LXC_ID}" -- chmod 600 /opt/unofficial-proxmox-mcp/.env

    # Python virtualenv & dependencies
    pct exec "${LXC_ID}" -- python3 -m venv /opt/unofficial-proxmox-mcp/.venv
    pct exec "${LXC_ID}" -- /opt/unofficial-proxmox-mcp/.venv/bin/pip install --upgrade pip
    pct exec "${LXC_ID}" -- /opt/unofficial-proxmox-mcp/.venv/bin/pip install -e /opt/unofficial-proxmox-mcp

    # Systemd service
    pct exec "${LXC_ID}" -- bash -c "cat << 'EOF' > /etc/systemd/system/unofficial-proxmox-mcp.service
[Unit]
Description=Unofficial Proxmox Model Context Protocol Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/unofficial-proxmox-mcp
EnvironmentFile=/opt/unofficial-proxmox-mcp/.env
ExecStart=/opt/unofficial-proxmox-mcp/.venv/bin/unofficial-proxmox-mcp --transport sse --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

    pct exec "${LXC_ID}" -- systemctl daemon-reload
    pct exec "${LXC_ID}" -- systemctl enable --now unofficial-proxmox-mcp

    LXC_IP=$(pct exec "${LXC_ID}" -- ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "UNKNOWN")

    echo -e "\n${GREEN}============================================================${NC}"
    echo -e "${GREEN}[+] Unofficial-Proxmox-MCP LXC Successfully Deployed!${NC}"
    echo -e "    Container ID    : ${LXC_ID}"
    echo -e "    IP Address      : ${LXC_IP}"
    echo -e "    SSE Endpoint    : http://${LXC_IP}:8000/sse"
    echo -e "    Self-Protection : Active (VMID ${LXC_ID} locked against deletion)"
    echo -e "    Status Check    : pct exec ${LXC_ID} -- systemctl status unofficial-proxmox-mcp"
    echo -e "${GREEN}============================================================${NC}"
}

# Menu Router
echo -e "Select installation target:"
echo -e "  1) Local Machine (Client stdio mode for Claude Desktop / Antigravity / Cursor)"
echo -e "  2) Docker / Docker Compose (SSE HTTP Server)"
echo -e "  3) Proxmox VE Host LXC Container (Dedicated hypervisor co-pilot)"
read -rp "Enter choice [1-3]: " CHOICE

case "${CHOICE}" in
    1) install_local ;;
    2) install_docker ;;
    3) install_pve_lxc ;;
    *) echo -e "${RED}[!] Invalid choice. Aborting.${NC}"; exit 1 ;;
esac
