"""
FastMCP Server implementation exposing Proxmox VE tools.
Compatible with Antigravity, Claude Desktop, Cursor, Hermes Agent, and any MCP client.
"""

import json
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from .client import PVEClient
from .config import PVEConfig

# Initialize FastMCP Server
mcp = FastMCP("unofficial-proxmox-mcp")

# Lazy global client
_client: Optional[PVEClient] = None


def get_client() -> PVEClient:
    """Retrieve or initialize the singleton Proxmox API client."""
    global _client
    if _client is None:
        _client = PVEClient()
    return _client


# ------------------------------------------------------------------------------
# 1. Fleet Discovery & Cluster Telemetry
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_list_nodes() -> str:
    """
    List all cluster nodes, their online status, CPU usage %, memory allocation, and uptime.
    Returns JSON formatted overview.
    """
    try:
        nodes = get_client().list_nodes()
        return json.dumps({"status": "success", "nodes": nodes}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_get_node_status(node: str = "") -> str:
    """
    Get deep telemetry for a Proxmox node: PVE version, kernel version, CPU sockets/cores/model,
    load averages, and memory/swap utilization in MB.
    
    Args:
        node: Target node name (e.g. 'pve'). Defaults to cluster default node if empty.
    """
    try:
        status_info = get_client().get_node_status(node=node or None)
        return json.dumps({"status": "success", "node_status": status_info}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_list_storage_pools(node: str = "") -> str:
    """
    List all configured storage pools (ZFS, LVM-Thin, Directory, NFS, Ceph) on a node or cluster,
    including enabled content types (iso, vztmpl, images, backup), total space, used, and free GB.
    
    Args:
        node: Target node name. Defaults to cluster default node if empty.
    """
    try:
        storages = get_client().list_storage_pools(node=node or None)
        return json.dumps({"status": "success", "storage_pools": storages}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_list_systems(
    node: str = "all",
    type_filter: str = "all",
    status_filter: str = "all"
) -> str:
    """
    List virtual machines and LXC containers in the cluster.
    
    Args:
        node: Filter by specific node name (e.g. 'pve') or 'all' across cluster.
        type_filter: 'all', 'qemu' (VMs only), or 'lxc' (Containers only).
        status_filter: 'all', 'running', or 'stopped'.
    """
    try:
        systems = get_client().list_systems(
            node=node if node != "all" else None,
            type_filter=type_filter,
            status_filter=status_filter,
        )
        return json.dumps({"status": "success", "count": len(systems), "systems": systems}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_get_system(vmid: int, node: str = "") -> str:
    """
    Get detailed hardware configuration, network adapters, memory, disk layouts, and live status for a VM or LXC container.
    
    Args:
        vmid: Target VM or LXC Container ID (e.g. 101 or 204).
        node: Optional node name. If omitted, automatically locates the system across cluster nodes.
    """
    try:
        data = get_client().get_system(vmid=vmid, node=node or None)
        return json.dumps({"status": "success", "system": data}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_get_guest_network(vmid: int, node: str = "") -> str:
    """
    Retrieve live guest IP addresses (IPv4 & IPv6), MAC addresses, and network interfaces.
    Uses QEMU Guest Agent for VMs, or container interface discovery for LXC.
    
    Args:
        vmid: Target VM or LXC Container ID.
        node: Optional node name.
    """
    try:
        data = get_client().get_guest_network(vmid=vmid, node=node or None)
        return json.dumps({"status": "success", "network": data}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_exec_guest_command(
    vmid: int,
    command: str,
    node: str = "",
    timeout: int = 30
) -> str:
    """
    Execute a non-interactive shell command inside a QEMU VM via the QEMU Guest Agent.
    Returns exit code, stdout, and stderr.
    
    Args:
        vmid: Target QEMU Virtual Machine ID.
        command: Shell command string to execute (e.g. 'ip a', 'uptime', 'docker ps').
        node: Optional node name.
        timeout: Execution timeout in seconds (default: 30).
    """
    try:
        res = get_client().exec_guest_command(vmid=vmid, command=command, node=node or None, timeout=timeout)
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 2. Lifecycle Operations (Start, Stop, Reboot, etc.)
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_lifecycle(vmid: int, action: str, node: str = "") -> str:
    """
    Perform a lifecycle state transition on a VM or container.
    
    Args:
        vmid: Target VM or Container ID.
        action: One of: 'start', 'stop', 'shutdown', 'reboot', 'reset', 'suspend', 'resume'.
        node: Optional node name. Automatically discovers node if omitted.
    """
    try:
        res = get_client().manage_lifecycle(vmid=vmid, action=action, node=node or None)
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 3. Snapshot Operations (Create, List, Rollback, Delete)
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_create_snapshot(
    vmid: int,
    snapname: str,
    description: str = "",
    vmstate: bool = False,
    node: str = ""
) -> str:
    """
    Take a snapshot of a VM or LXC container.
    
    Args:
        vmid: Target VM or Container ID.
        snapname: Name for the snapshot (alphanumeric and dashes/underscores, e.g. 'pre-upgrade-v1').
        description: Informative description or changelog for the snapshot.
        vmstate: For QEMU VMs only. If True, saves running RAM state (live snapshot).
        node: Optional node name.
    """
    try:
        res = get_client().create_snapshot(
            vmid=vmid,
            snapname=snapname,
            description=description,
            vmstate=vmstate,
            node=node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_list_snapshots(vmid: int, node: str = "") -> str:
    """
    List all existing snapshots and hierarchy for a VM or LXC container.
    
    Args:
        vmid: Target VM or Container ID.
        node: Optional node name.
    """
    try:
        snapshots = get_client().list_snapshots(vmid=vmid, node=node or None)
        return json.dumps({"status": "success", "vmid": vmid, "snapshots": snapshots}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_rollback_snapshot(
    vmid: int,
    snapname: str,
    start_after: bool = False,
    node: str = ""
) -> str:
    """
    Revert a VM or LXC container to a previous snapshot state.
    
    Args:
        vmid: Target VM or Container ID.
        snapname: Name of the snapshot to restore.
        start_after: If True, automatically powers the system on after rollback completes.
        node: Optional node name.
    """
    try:
        res = get_client().rollback_snapshot(
            vmid=vmid,
            snapname=snapname,
            start_after=start_after,
            node=node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_delete_snapshot(
    vmid: int,
    snapname: str,
    confirmation_phrase: str = "",
    node: str = ""
) -> str:
    """
    Delete a snapshot from a VM or LXC container.
    
    SAFETY REQUIREMENT:
      Deleting a snapshot merges or purges historical states.
      If confirmation_phrase is not provided, this tool will safely block and ask you
      to confirm with confirmation_phrase='CONFIRM_DELETE_SNAPSHOT_<snapname>'.
    
    Args:
        vmid: Target VM or Container ID.
        snapname: Snapshot identifier to delete.
        confirmation_phrase: Explicit confirmation phrase (e.g. 'CONFIRM_DELETE_SNAPSHOT_pre-upgrade').
        node: Optional node name.
    """
    try:
        res = get_client().delete_snapshot(
            vmid=vmid,
            snapname=snapname,
            confirmation_phrase=confirmation_phrase,
            node=node or None,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 4. System Modification & Configuration Editing
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_edit_system(
    vmid: int,
    cores: Optional[int] = None,
    memory_mb: Optional[int] = None,
    description: Optional[str] = None,
    tags: Optional[str] = None,
    onboot: Optional[bool] = None,
    node: str = ""
) -> str:
    """
    Edit configuration parameters of an existing VM or container (CPU cores, RAM, notes, tags, onboot).
    
    Args:
        vmid: Target VM or Container ID.
        cores: Number of virtual CPU cores to assign.
        memory_mb: Allocated RAM in megabytes (e.g. 4096 for 4GB).
        description: Notes / documentation markdown string.
        tags: Semicolon or comma-separated tags (e.g. 'web;production;docker').
        onboot: Whether the system automatically starts on Proxmox node boot.
        node: Optional node name.
    """
    try:
        res = get_client().edit_system(
            vmid=vmid,
            cores=cores,
            memory_mb=memory_mb,
            description=description,
            tags=tags,
            onboot=onboot,
            node=node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_set_cloudinit(
    vmid: int,
    ciuser: Optional[str] = None,
    cipassword: Optional[str] = None,
    sshkeys: Optional[str] = None,
    ipconfig0: Optional[str] = None,
    nameserver: Optional[str] = None,
    searchdomain: Optional[str] = None,
    node: str = ""
) -> str:
    """
    Configure Cloud-Init parameters on a QEMU virtual machine.
    
    Args:
        vmid: Target VM ID.
        ciuser: Default cloud-init username (e.g. 'ubuntu' or 'debian').
        cipassword: User password.
        sshkeys: URL-encoded or raw OpenSSH public key string.
        ipconfig0: IP addressing config (e.g. 'ip=dhcp' or 'ip=192.168.1.50/24,gw=192.168.1.1').
        nameserver: DNS nameserver IP.
        searchdomain: DNS search domain.
        node: Optional node name.
    """
    try:
        res = get_client().set_cloudinit(
            vmid=vmid,
            ciuser=ciuser,
            cipassword=cipassword,
            sshkeys=sshkeys,
            ipconfig0=ipconfig0,
            nameserver=nameserver,
            searchdomain=searchdomain,
            node=node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_resize_disk(
    vmid: int,
    disk: str,
    add_gb: int,
    node: str = ""
) -> str:
    """
    Incrementally expand the storage capacity of a virtual disk.
    
    Args:
        vmid: Target VM or Container ID.
        disk: Disk device identifier (e.g. 'scsi0', 'virtio0', or 'rootfs').
        add_gb: Size in gigabytes to expand by (e.g. 10 adds 10GB).
        node: Optional node name.
    """
    try:
        res = get_client().resize_disk(
            vmid=vmid,
            disk=disk,
            add_gb=add_gb,
            node=node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 5. Provisioning & Creation (Clone, LXC, VM)
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_clone_system(
    source_vmid: int,
    new_vmid: int,
    new_name: str,
    full_clone: bool = True,
    target_storage: str = "",
    target_node: str = ""
) -> str:
    """
    Clone a new VM or LXC container from an existing template or system.
    
    Args:
        source_vmid: Source template or instance VMID.
        new_vmid: Unique ID for the newly created instance (e.g. 301).
        new_name: Hostname or display name for the new system.
        full_clone: If True, makes an independent full clone. If False, creates a linked clone.
        target_storage: Storage pool name (e.g. 'local-lvm', 'fast-tier'). Optional.
        target_node: Target node name. Optional.
    """
    try:
        res = get_client().clone_system(
            source_vmid=source_vmid,
            new_vmid=new_vmid,
            new_name=new_name,
            full_clone=full_clone,
            target_storage=target_storage or None,
            target_node=target_node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_create_lxc(
    vmid: int,
    hostname: str,
    ostemplate: str,
    cores: int = 2,
    memory_mb: int = 2048,
    disk_gb: int = 10,
    storage: str = "local-lvm",
    password: str = "",
    ssh_public_key: str = "",
    net0: str = "name=eth0,bridge=vmbr0,firewall=1,ip=dhcp",
    unprivileged: bool = True,
    node: str = ""
) -> str:
    """
    Create a new LXC container from an OS template tarball.
    
    Args:
        vmid: Unique Container ID (e.g. 255).
        hostname: Hostname for the container.
        ostemplate: Storage template path (e.g. 'local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst').
        cores: Number of assigned CPU cores.
        memory_mb: Memory in megabytes.
        disk_gb: Root filesystem disk size in gigabytes.
        storage: Target storage pool (e.g. 'local-lvm' or 'fast-tier').
        password: Root user password.
        ssh_public_key: Optional SSH public key to inject into /root/.ssh/authorized_keys.
        net0: Network interface configuration string.
        unprivileged: If True, provisions container in an unprivileged user namespace (recommended).
        node: Target node name.
    """
    try:
        res = get_client().create_lxc(
            vmid=vmid,
            hostname=hostname,
            ostemplate=ostemplate,
            cores=cores,
            memory_mb=memory_mb,
            disk_gb=disk_gb,
            storage=storage,
            password=password or None,
            ssh_public_key=ssh_public_key or None,
            net0=net0,
            unprivileged=unprivileged,
            node=node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_create_vm(
    vmid: int,
    name: str,
    cores: int = 2,
    memory_mb: int = 2048,
    disk_gb: int = 20,
    storage: str = "local-lvm",
    iso_image: str = "",
    net0: str = "virtio,bridge=vmbr0,firewall=1",
    node: str = ""
) -> str:
    """
    Create a new QEMU virtual machine.
    
    Args:
        vmid: Unique Virtual Machine ID (e.g. 150).
        name: Name / hostname of the virtual machine.
        cores: Number of virtual CPU cores.
        memory_mb: Memory in megabytes.
        disk_gb: Boot disk size in gigabytes.
        storage: Target storage pool (e.g. 'local-lvm', 'fast-tier').
        iso_image: Optional ISO image path (e.g. 'local:iso/ubuntu-24.04-live-server-amd64.iso').
        net0: Network interface configuration string.
        node: Target node name.
    """
    try:
        res = get_client().create_vm(
            vmid=vmid,
            name=name,
            cores=cores,
            memory_mb=memory_mb,
            disk_gb=disk_gb,
            storage=storage,
            iso_image=iso_image or None,
            net0=net0,
            node=node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 6. Backups (vzdump & PBS)
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_trigger_backup(
    vmid: int,
    storage: str = "local",
    mode: str = "snapshot",
    compression: str = "zstd",
    node: str = ""
) -> str:
    """
    Execute an immediate vzdump backup of a VM or container to a target storage pool.
    
    Args:
        vmid: Target VM or LXC Container ID.
        storage: Target backup storage pool (e.g. 'local', 'pbs-backup').
        mode: Backup mode: 'snapshot' (live, zero downtime), 'suspend', or 'stop'.
        compression: Compression algorithm: 'zstd', 'gzip', or 'none'.
        node: Optional node name.
    """
    try:
        res = get_client().trigger_backup(
            vmid=vmid,
            storage=storage,
            mode=mode,
            compression=compression,
            node=node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_list_backups(storage: str = "local", node: str = "") -> str:
    """
    List available backup archives stored in a designated storage pool.
    
    Args:
        storage: Storage pool identifier (e.g. 'local', 'vault-backups').
        node: Optional node name.
    """
    try:
        backups = get_client().list_backups(storage=storage, node=node or None)
        return json.dumps({"status": "success", "count": len(backups), "backups": backups}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 7. Firewall Management
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_get_firewall(vmid: int, node: str = "") -> str:
    """
    Inspect the firewall rules and security options active on a VM or container.
    
    Args:
        vmid: Target VM or LXC Container ID.
        node: Optional node name.
    """
    try:
        fw = get_client().get_firewall(vmid=vmid, node=node or None)
        return json.dumps({"status": "success", "firewall": fw}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


@mcp.tool()
def pve_set_firewall_rule(
    vmid: int,
    action: str,
    rule_type: str = "in",
    proto: str = "tcp",
    dport: str = "",
    comment: str = "",
    enable: bool = True,
    node: str = ""
) -> str:
    """
    Add or modify a firewall rule on a VM or container.
    
    Args:
        vmid: Target VM or LXC Container ID.
        action: 'ACCEPT', 'DROP', or 'REJECT'.
        rule_type: 'in' (inbound) or 'out' (outbound).
        proto: Protocol: 'tcp', 'udp', 'icmp', etc.
        dport: Destination port or port range (e.g. '80', '443', '8000:8050').
        comment: Brief description of the firewall rule.
        enable: Whether the rule is actively enabled.
        node: Optional node name.
    """
    try:
        res = get_client().set_firewall_rule(
            vmid=vmid,
            action=action,
            rule_type=rule_type,
            proto=proto,
            dport=dport,
            comment=comment,
            enable=enable,
            node=node or None,
        )
        return json.dumps({"status": "success", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 8. Placement & Overcommit Advisory
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_recommend_placement(
    required_cores: int = 2,
    required_mem_mb: int = 2048,
    required_disk_gb: int = 20
) -> str:
    """
    Analyze cluster resource congestion and recommend the optimal node for placing new workloads.
    
    Args:
        required_cores: Number of virtual CPU cores needed.
        required_mem_mb: RAM in megabytes required.
        required_disk_gb: Storage in gigabytes required.
    """
    try:
        rec = get_client().recommend_placement(
            required_cores=required_cores,
            required_mem_mb=required_mem_mb,
            required_disk_gb=required_disk_gb,
        )
        return json.dumps({"status": "success", "advisory": rec}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 9. VNC / Console Access Ticket
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_get_vnc_ticket(vmid: int, node: str = "") -> str:
    """
    Generate a time-limited NoVNC console ticket and URL for browser-based out-of-band management.
    
    Args:
        vmid: Target VM or LXC Container ID.
        node: Optional node name.
    """
    try:
        ticket = get_client().get_vnc_ticket(vmid=vmid, node=node or None)
        return json.dumps({"status": "success", "vnc": ticket}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 10. Infrastructure-as-Code (Terraform / OpenTofu) Exporter
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_export_terraform(vmid: int, node: str = "") -> str:
    """
    Export the complete live specification of a VM or container into a ready-to-run Terraform / OpenTofu (.tf) block.
    
    Args:
        vmid: Target VM or LXC Container ID.
        node: Optional node name.
    """
    try:
        hcl = get_client().export_terraform(vmid=vmid, node=node or None)
        return json.dumps({"status": "success", "vmid": vmid, "terraform_hcl": hcl}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


# ------------------------------------------------------------------------------
# 11. Destruction & Removal with Safety Guardrails & Mandatory Confirmation
# ------------------------------------------------------------------------------
@mcp.tool()
def pve_destroy_system(
    vmid: int,
    confirm_vmid: int = 0,
    confirmation_phrase: str = "",
    purge_data: bool = True,
    node: str = ""
) -> str:
    """
    Safely delete and remove a virtual machine or LXC container.
    
    MANDATORY CONFIRMATION SAFETY GATES:
      1. If confirm_vmid != vmid OR confirmation_phrase != 'CONFIRM_DELETE_<vmid>', this tool
         will SAFELY REFUSE destruction and return a confirmation request. You must ask the user
         explicitly to confirm deletion before calling with the matching confirmation phrase.
      2. Self-Protection: Cannot delete the container hosting this MCP server.
      3. The target vmid MUST NOT be included in PVE_PROTECTED_VMIDS blacklist.
      4. The instance will be cleanly stopped prior to deletion.
    
    Args:
        vmid: Target ID of the VM or container to destroy.
        confirm_vmid: Must equal vmid as an explicit confirmation gate.
        confirmation_phrase: Must equal 'CONFIRM_DELETE_<vmid>' (e.g. 'CONFIRM_DELETE_300').
        purge_data: Whether to purge and release all associated virtual disks and backup files.
        node: Optional node name.
    """
    try:
        res = get_client().destroy_system(
            vmid=vmid,
            confirm_vmid=confirm_vmid,
            confirmation_phrase=confirmation_phrase,
            purge=purge_data,
            node=node or None,
        )
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)
