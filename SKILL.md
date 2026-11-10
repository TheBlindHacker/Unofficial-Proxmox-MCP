---
name: proxmox-mcp
description: Manage Proxmox VE hypervisor clusters, QEMU VMs, LXC containers, snapshots, Cloud-Init, firewalls, and vzdump backups via conversational AI with mandatory safety guardrails.
compatibility: Claude Code, Gemini CLI, Cursor, Antigravity, Hermes Agent, Codex CLI, VS Code Copilot
metadata:
  author: Joe Brinkley (The Blind Hacker)
  version: 1.0.0
  tags:
    - proxmox
    - homelab
    - virtualization
    - devops
    - mcp
    - claude
    - gemini
---

# Proxmox VE MCP Management Skill (`proxmox-mcp`)

Connect your AI agent (Claude Code, Gemini CLI, Cursor, Antigravity, Hermes Agent) directly to your Proxmox Virtual Environment (PVE) cluster via the official Model Context Protocol (MCP).

This skill guides the AI assistant on how and when to inspect nodes, provision QEMU VMs and LXC containers, execute in-guest commands via QEMU Guest Agent, take and rollback snapshots, configure Cloud-Init, trigger vzdump backups, manage firewall rules, and export infrastructure to Terraform—all protected by **mandatory two-step confirmation gates** and **LXC container self-protection**.

---

## 🛠️ MCP Tool Reference (19 Core Tools)

### 1. Fleet Discovery & Telemetry
- `pve_list_nodes()`: High-level cluster overview: node status, CPU load %, RAM usage, and uptime.
- `pve_get_node_status(node)`: Deep hardware telemetry: PVE kernel, CPU sockets/cores, load averages, memory/swap breakdown.
- `pve_list_storage_pools(node)`: Storage backend audit: ZFS pools, LVM-thin, NFS, Ceph, Directory storage, free/used GB.
- `pve_list_systems(node, type_filter, status_filter)`: Comprehensive inventory of QEMU VMs and LXC containers.
- `pve_get_system(vmid, node)`: Detailed live configuration, assigned hardware, network interfaces, and tags.
- `pve_get_guest_network(vmid, node)`: Retrieves live guest IPv4, IPv6, and MAC addresses via QEMU Guest Agent or LXC network stack.
- `pve_exec_guest_command(vmid, command, node, timeout)`: Runs a non-interactive shell command inside a guest VM via QEMU Guest Agent and returns stdout, stderr, and exit code.

### 2. Lifecycle & Snapshot Management
- `pve_lifecycle(vmid, action, node)`: Manages instance state transitions: `start`, `stop`, `shutdown`, `reboot`, `reset`, `suspend`, `resume` with automatic UPID task monitoring.
- `pve_create_snapshot(vmid, snapname, description, vmstate, node)`: Captures instantaneous VM or container state (including live RAM).
- `pve_list_snapshots(vmid, node)`: Retrieves tree hierarchy of snapshots for an instance.
- `pve_rollback_snapshot(vmid, snapname, start_after, node)`: Reverts guest state to a specified snapshot.
- `pve_delete_snapshot(vmid, snapname, confirmation_phrase, node)`: Deletes snapshot and merges delta storage (**requires confirmation phrase**).

### 3. Provisioning & Hardware Configuration
- `pve_edit_system(vmid, cores, memory_mb, description, tags, onboot, node)`: Modifies CPU cores, memory limits, description, tags, and boot order.
- `pve_resize_disk(vmid, disk, add_gb, node)`: Safely increments storage allocation on virtual disks (`scsi0`, `rootfs`, etc.).
- `pve_set_cloudinit(vmid, ciuser, cipassword, sshkeys, ipconfig0, nameserver, searchdomain, node)`: Configures Cloud-Init credentials, networking, and SSH keys.
- `pve_clone_system(source_vmid, new_vmid, new_name, full_clone, target_storage, target_node)`: Clones templates or live systems.
- `pve_create_lxc(vmid, hostname, ostemplate, cores, memory_mb, disk_gb, storage, password, ssh_public_key, unprivileged, node)`: Provisions a new Linux container.
- `pve_create_vm(vmid, name, cores, memory_mb, disk_gb, storage, iso_image, node)`: Provisions a new QEMU virtual machine.
- `pve_destroy_system(vmid, confirm_vmid, confirmation_phrase, purge_data, node)`: Safely purges an instance (**requires confirmation phrase + blacklist clearance**).

### 4. Backups, Security & IaC
- `pve_trigger_backup(vmid, storage, mode, compression, node)`: Initiates immediate `vzdump` backup job.
- `pve_list_backups(storage, node)`: Lists backup archives and sizes in a storage pool.
- `pve_get_firewall(vmid, node)`: Inspects active guest or cluster firewall rules.
- `pve_set_firewall_rule(vmid, action, rule_type, proto, dport, comment, enable, node)`: Creates or updates firewall security rules.
- `pve_recommend_placement(required_cores, required_mem_mb, required_disk_gb)`: Analyzes cluster CPU and memory pressure to recommend optimal node deployment.
- `pve_get_vnc_ticket(vmid, node)`: Generates time-limited NoVNC console URL and tickets.
- `pve_export_terraform(vmid, node)`: Reverse-engineers live VM/LXC configurations into ready-to-deploy Terraform / OpenTofu `.tf` code.

---

## 🔒 Safety Guardrails & Operational Rules

1. **Mandatory Destruction Confirmation**:
   - `pve_destroy_system` and `pve_delete_snapshot` can never be executed in a single automatic shot.
   - When requested, the agent must inspect the parameters, warn the operator, and request explicit verification phrase `CONFIRM_DELETE_<vmid>`.
2. **Container Self-Protection**:
   - The MCP server automatically detects its own host VMID (via `/etc/pve-self-vmid` or `PVE_SELF_VMID`). Any attempt to stop, reboot, or destroy the server container itself is hard-blocked.
3. **Protected VMID Blacklist**:
   - Critical infrastructure (routers, primary NAS, domain controllers) listed in `PVE_PROTECTED_VMIDS` are immune to destructive actions.

---

## 🚀 Setup & Agent Integration

### Claude Code / Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "proxmox": {
      "command": "uvx",
      "args": ["unofficial-proxmox-mcp"],
      "env": {
        "PVE_HOST": "192.168.1.100",
        "PVE_USER": "mcp-bot@pve!mcp-token",
        "PVE_TOKEN_SECRET": "your-token-uuid-here",
        "PVE_VERIFY_SSL": "false",
        "PVE_PROTECTED_VMIDS": "100,101,200"
      }
    }
  }
}
```

### Gemini CLI / Cursor / Antigravity
```json
{
  "mcpServers": {
    "proxmox": {
      "command": "python",
      "args": ["-m", "unofficial_proxmox_mcp"],
      "env": {
        "PVE_HOST": "192.168.1.100",
        "PVE_USER": "mcp-bot@pve!mcp-token",
        "PVE_TOKEN_SECRET": "your-token-uuid-here",
        "PVE_VERIFY_SSL": "false"
      }
    }
  }
}
```
