# Unofficial-Proxmox-MCP 🚀
### Production-Grade, Drop-In Model Context Protocol (MCP) Server for Proxmox VE

**License**: MIT | **Python**: 3.10+ | **Protocol**: MCP 1.0+ | **Linter**: Ruff Clean

**Unofficial-Proxmox-MCP** bridges AI assistants (Antigravity, Claude Desktop, Cursor, Hermes Agent, Open-WebUI, LibreChat) directly with your Proxmox Virtual Environment (PVE) cluster via the official Model Context Protocol.

Manage your virtualization infrastructure conversationally: inspect nodes, provision VMs and LXC containers, resize disks, manage snapshots, configure Cloud-Init, trigger vzdump backups, manage firewall rules, evaluate node placement, query guest IPs, and run guest commands—with **mandatory two-step confirmation guardrails** and **container self-protection**.

---

## ⚡ Deployment Modes: Where Should You Run It?

> **"Are we using Docker locally, running it directly on the system, or hosting it inside an LXC on Proxmox?"**

You have complete flexibility:

```
┌─────────────────────────────────┐
│        AI Assistants & IDEs     │
│ (Claude, Antigravity, Cursor)   │
└───────────────┬─────────────────┘
                │
        ┌───────┼─────────────────────────┐
        ▼       ▼                         ▼
   [Mode 1]  [Mode 2]                  [Mode 3]
  Local Venv  Local Docker          Proxmox Host LXC
  (stdio)     (SSE on :8000)      (SSE Co-Pilot on :8000)
        │       │                         │
        └───────┴───────────┬─────────────┘
                            ▼ HTTPS (:8006)
             ┌───────────────────────────────┐
             │   Proxmox VE Cluster Node     │
             │  (QEMU VMs, LXC Containers)   │
             └───────────────────────────────┘
```

| Deployment Mode | Transport | Pros | Cons | Ideal For |
|---|---|---|---|---|
| **Mode 1: Local System (.venv)** | `stdio` | Zero hypervisor footprint; fastest IPC response; direct Claude/Antigravity integration. | Requires Python on local machine. | Solo developers, daily driver workstations. |
| **Mode 2: Local / LAN Docker** | `sse` | Clean isolation; no Python dependency on host; one-command lifecycle. | Requires Docker running. | Homelab servers, microservices. |
| **Mode 3: Proxmox Host LXC** | `sse` | 24/7 dedicated hypervisor co-pilot; shared across team; auto-self-protection. | Consumes ~1GB RAM on Proxmox. | Multi-agent clusters, team labs. |

---

## 🛡️ Enterprise Security & Self-Protection Architecture

### 1. LXC Container Self-Protection
When deployed inside an LXC container on Proxmox (Mode 3), the server **automatically detects its own host VMID** (via `/etc/pve-self-vmid` or `PVE_SELF_VMID`):
- It permanently binds its own ID into `protected_vmids`.
- Any command instructing an agent to `stop`, `shutdown`, `reset`, or `destroy` the container running the MCP server is **hard-blocked**:
  ```
  PermissionError: Self-Protection Block: Cannot destroy VMID 299 because it is the host container running this MCP server.
  ```

### 2. Mandatory Two-Step Confirmation Gates
AI models cannot accidentally wipe your fleet:
- **System Deletion (`pve_destroy_system`)**:
  Calling the tool without confirmation safely aborts and returns:
  ```json
  {
    "status": "confirmation_required",
    "action": "destroy_system",
    "vmid": 300,
    "message": "DESTRUCTION BLOCKED: Deletion requires explicit user confirmation...",
    "required_params": {
      "confirm_vmid": 300,
      "confirmation_phrase": "CONFIRM_DELETE_300"
    }
  }
  ```
  The agent must ask the human operator for confirmation. Only re-invoking with `confirm_vmid=300` AND `confirmation_phrase="CONFIRM_DELETE_300"` permits deletion.
- **Snapshot Deletion (`pve_delete_snapshot`)**: Requires `confirmation_phrase="CONFIRM_DELETE_SNAPSHOT_<snapname>"`.
- **Immune Blacklist (`PVE_PROTECTED_VMIDS`)**: Nodes listed here (e.g. your router, primary storage, domain controllers) can never be destroyed via MCP.

### 3. Dedicated Least-Privilege Account Creation
The installer provides an interactive wizard to create an isolated service account (`mcp-bot@pve`) with a scoped role (`MCPAgent`) instead of using `root@pam`.

---

## 📋 Comprehensive MCP Tool Suite (19 Drop-In Tools)

### 1. Fleet Discovery & Telemetry
- `pve_list_nodes()`: Overview of cluster nodes, online status, CPU %, memory allocation, and uptime.
- `pve_get_node_status(node)`: Deep telemetry (PVE version, Linux kernel, CPU model/sockets/cores, load averages, memory/swap breakdown).
- `pve_list_storage_pools(node)`: Storage pools (ZFS, LVM, Directory, NFS) with content types (iso, vztmpl, backup, images) and free/used GB.
- `pve_list_systems(node, type_filter, status_filter)`: Filtered VM and container fleet listing.
- `pve_get_system(vmid, node)`: Full configuration and live telemetry for a specific instance.
- `pve_get_guest_network(vmid, node)`: Live IP addresses (IPv4 & IPv6) and MACs via QEMU Guest Agent or LXC network stack.
- `pve_exec_guest_command(vmid, command, node, timeout)`: Executes a non-interactive shell command inside a QEMU VM via QEMU Guest Agent and returns exit code, stdout, and stderr.

### 2. Lifecycle & Snapshots
- `pve_lifecycle(vmid, action, node)`: Executes state transitions: `start`, `stop`, `shutdown`, `reboot`, `reset`, `suspend`, `resume` with automatic `UPID` task polling.
- `pve_create_snapshot(vmid, snapname, description, vmstate, node)`: Captures instantaneous VM/LXC state (including live RAM).
- `pve_list_snapshots(vmid, node)`: Snapshot hierarchy and trees.
- `pve_rollback_snapshot(vmid, snapname, start_after, node)`: Restores system to a prior snapshot.
- `pve_delete_snapshot(vmid, snapname, confirmation_phrase, node)`: Deletes snapshot and merges delta storage (**requires confirmation phrase**).

### 3. Configuration & Provisioning
- `pve_edit_system(vmid, cores, memory_mb, description, tags, onboot, node)`: Modifies CPU cores, RAM limits, notes, tags, and auto-start.
- `pve_resize_disk(vmid, disk, add_gb, node)`: Incremental storage expansion (`scsi0`, `rootfs`, etc.).
- `pve_set_cloudinit(vmid, ciuser, cipassword, sshkeys, ipconfig0, nameserver, searchdomain, node)`: Configures Cloud-Init drive on a VM.
- `pve_clone_system(source_vmid, new_vmid, new_name, full_clone, target_storage, target_node)`: Clones templates/instances (full or linked clone).
- `pve_create_lxc(vmid, hostname, ostemplate, cores, memory_mb, disk_gb, storage, password, ssh_public_key, unprivileged, node)`: Provisions new container from template.
- `pve_create_vm(vmid, name, cores, memory_mb, disk_gb, storage, iso_image, node)`: Provisions new QEMU virtual machine.
- `pve_destroy_system(vmid, confirm_vmid, confirmation_phrase, purge_data, node)`: Safely purges an instance (**requires confirmation phrase + blacklist clearance**).

### 4. Advanced Management & IaC
- `pve_trigger_backup(vmid, storage, mode, compression, node)`: Triggers immediate `vzdump` backup.
- `pve_list_backups(storage, node)`: Lists backup archives and sizes in a storage pool.
- `pve_get_firewall(vmid, node)`: Inspects active firewall rules and security options.
- `pve_set_firewall_rule(vmid, action, rule_type, proto, dport, comment, enable, node)`: Adds or updates a firewall rule.
- `pve_recommend_placement(required_cores, required_mem_mb, required_disk_gb)`: Analyzes cluster CPU and memory congestion to recommend the optimal node.
- `pve_get_vnc_ticket(vmid, node)`: Generates time-limited NoVNC console URL and tickets.
- `pve_export_terraform(vmid, node)`: Generates ready-to-run Terraform / OpenTofu `.tf` configurations.

---

## 🚀 Interactive Installation

### Linux / macOS:
```bash
git clone https://github.com/your-username/Unofficial-Proxmox-MCP.git
cd Unofficial-Proxmox-MCP
chmod +x install.sh
./install.sh
```
*Prompts for deployment mode (Local, Docker, or Host LXC), offers to auto-generate the dedicated `mcp-bot@pve` user, and verifies connectivity.*

### Windows (PowerShell):
```powershell
git clone https://github.com/your-username/Unofficial-Proxmox-MCP.git
cd Unofficial-Proxmox-MCP
.\install.ps1 -Target Local
# or .\install.ps1 -Target Docker
```

### Proxmox VE Host Turnkey LXC:
Run directly on your Proxmox hypervisor shell:
```bash
bash pve-lxc-deploy.sh
```

---

## 🤖 Drop-In AI Configuration

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "proxmox": {
      "command": "uvx",
      "args": ["unofficial-proxmox-mcp"],
      "env": {
        "PVE_HOST": "192.168.1.100",
        "PVE_USER": "mcp-bot@pve!mcp-token",
        "PVE_TOKEN_SECRET": "your-token-secret-uuid",
        "PVE_VERIFY_SSL": "false",
        "PVE_PROTECTED_VMIDS": "100,101,200"
      }
    }
  }
}
```

### Antigravity / Cursor / LibreChat
```json
{
  "mcpServers": {
    "proxmox": {
      "command": "python",
      "args": ["-m", "unofficial_proxmox_mcp"],
      "env": {
        "PVE_HOST": "192.168.1.100",
        "PVE_USER": "mcp-bot@pve!mcp-token",
        "PVE_TOKEN_SECRET": "your-token-secret-uuid",
        "PVE_VERIFY_SSL": "false"
      }
    }
  }
}
```

---

## 🧪 Testing & Verification

```bash
pytest tests -v
# 19 passed in 1.25s
```

## 📄 License
Released under the [MIT License](LICENSE).
