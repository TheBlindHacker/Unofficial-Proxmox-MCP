"""
End-to-End (E2E) Comprehensive Suite for Unofficial-Proxmox-MCP.
Tests the full lifecycle of all 19 MCP tools with simulated Proxmox REST API fixtures,
task polling (UPID), state transitions, self-protection, and confirmation safety gates.
"""

from __future__ import annotations
import json
from unittest.mock import MagicMock, patch
import pytest

from unofficial_proxmox_mcp.config import PVEConfig
from unofficial_proxmox_mcp.client import PVEClient
from unofficial_proxmox_mcp.server import (
    pve_list_nodes,
    pve_get_node_status,
    pve_list_storage_pools,
    pve_list_systems,
    pve_get_system,
    pve_get_guest_network,
    pve_lifecycle,
    pve_create_snapshot,
    pve_list_snapshots,
    pve_rollback_snapshot,
    pve_delete_snapshot,
    pve_edit_system,
    pve_set_cloudinit,
    pve_resize_disk,
    pve_create_lxc,
    pve_create_vm,
    pve_trigger_backup,
    pve_set_firewall_rule,
    pve_recommend_placement,
    pve_get_vnc_ticket,
    pve_export_terraform,
    pve_destroy_system,
)


@pytest.fixture
def e2e_harness():
    """Sets up a complete mock environment simulating an active 3-node Proxmox cluster."""
    cfg = PVEConfig(
        host="192.168.10.10",
        port=8006,
        user="mcp-bot@pve",
        token_name="mcp-token",
        token_secret="e2e-secret-uuid-12345",
        verify_ssl=False,
        default_node="pve-node1",
        protected_vmids=[100, 101, 200],
        self_vmid=299,
    )

    with patch("unofficial_proxmox_mcp.client.ProxmoxAPI"), \
         patch("unofficial_proxmox_mcp.server.get_client") as mock_server_get:

        client = PVEClient(cfg)
        mock_server_get.return_value = client

        # Mock API objects
        api = MagicMock()
        client._api = api

        # Setup cluster nodes
        api.nodes.get.return_value = [
            {"node": "pve-node1", "status": "online", "cpu": 0.15, "maxcpu": 16, "mem": 16 * 1024**3, "maxmem": 64 * 1024**3, "uptime": 120000},
            {"node": "pve-node2", "status": "online", "cpu": 0.05, "maxcpu": 32, "mem": 8 * 1024**3, "maxmem": 128 * 1024**3, "uptime": 85000},
            {"node": "pve-node3", "status": "offline", "cpu": 0, "maxcpu": 8, "mem": 0, "maxmem": 32 * 1024**3, "uptime": 0},
        ]

        # Setup node status and version
        api.version.get.return_value = {"version": "8.2.4", "release": "pve"}
        api.nodes("pve-node1").status.get.return_value = {
            "kversion": "Linux 6.8.8-2-pve #1 SMP PREEMPT_DYNAMIC",
            "uptime": 120000,
            "cpu": 0.15,
            "loadavg": [0.45, 0.50, 0.40],
            "cpuinfo": {"model": "AMD EPYC 7002", "cores": 16, "sockets": 1},
            "memory": {"used": 16 * 1024**3, "total": 64 * 1024**3, "free": 48 * 1024**3},
            "swap": {"used": 512 * 1024**2, "total": 8 * 1024**3, "free": 7.5 * 1024**3},
        }

        # Setup storage pools
        api.nodes("pve-node1").storage.get.return_value = [
            {"storage": "local", "type": "dir", "content": "iso,vztmpl,backup", "total": 500 * 1024**3, "used": 100 * 1024**3, "avail": 400 * 1024**3},
            {"storage": "local-zfs", "type": "zfspool", "content": "rootdir,images", "total": 2000 * 1024**3, "used": 500 * 1024**3, "avail": 1500 * 1024**3},
        ]

        # Setup VMs and LXCs
        api.nodes("pve-node1").qemu.get.return_value = [
            {"vmid": 101, "name": "prod-k8s-master", "status": "running", "cpus": 4, "maxmem": 8192 * 1024**2, "maxdisk": 50 * 1024**3, "uptime": 50000},
            {"vmid": 320, "name": "ubuntu-agent", "status": "stopped", "cpus": 4, "maxmem": 4096 * 1024**2, "maxdisk": 30 * 1024**3, "uptime": 0},
            {"vmid": 350, "name": "dev-sandbox-vm", "status": "stopped", "cpus": 2, "maxmem": 4096 * 1024**2, "maxdisk": 20 * 1024**3, "uptime": 0},
        ]
        api.nodes("pve-node1").lxc.get.return_value = [
            {"vmid": 200, "name": "dns-pihole", "status": "running", "cpus": 1, "maxmem": 512 * 1024**2, "maxdisk": 8 * 1024**3, "uptime": 99999},
            {"vmid": 299, "name": "proxmox-mcp-host", "status": "running", "cpus": 2, "maxmem": 1024 * 1024**2, "maxdisk": 8 * 1024**3, "uptime": 12345},
            {"vmid": 300, "name": "test-scratch-lxc", "status": "running", "cpus": 2, "maxmem": 2048 * 1024**2, "maxdisk": 10 * 1024**3, "uptime": 500},
        ]

        # Setup task UPID status polling (all return OK immediately)
        api.nodes("pve-node1").tasks(MagicMock()).status.get.return_value = {
            "status": "stopped",
            "exitstatus": "OK"
        }

        yield client


# ==============================================================================
# Phase 1: Cluster & System Discovery
# ==============================================================================
def test_e2e_phase1_cluster_and_systems(e2e_harness):
    # 1. Nodes overview
    nodes_res = json.loads(pve_list_nodes())
    assert nodes_res["status"] == "success"
    assert len(nodes_res["nodes"]) == 3
    assert nodes_res["nodes"][0]["node"] == "pve-node1"

    # 2. Node deep status
    node_stat = json.loads(pve_get_node_status("pve-node1"))
    assert node_stat["status"] == "success"
    assert node_stat["node_status"]["kernel_version"].startswith("Linux 6.8")
    assert node_stat["node_status"]["cpu_cores"] == 16

    # 3. Storage pools
    pools_res = json.loads(pve_list_storage_pools("pve-node1"))
    assert pools_res["status"] == "success"
    assert len(pools_res["storage_pools"]) == 2

    # 4. System fleet listing for pve-node1
    systems_res = json.loads(pve_list_systems(node="pve-node1"))
    assert systems_res["status"] == "success"
    assert systems_res["count"] == 6

    # Verify self-protection tags in list
    self_item = next(s for s in systems_res["systems"] if s["vmid"] == 299)
    assert self_item["is_self"] is True
    assert self_item["is_protected"] is True

    # 5. System detail
    e2e_harness._api.nodes("pve-node1").lxc(300).config.get.return_value = {"cores": 2, "memory": 2048, "net0": "bridge=vmbr0"}
    e2e_harness._api.nodes("pve-node1").lxc(300).status.current.get.return_value = {"status": "running", "cpu": 0.02}
    sys_detail = json.loads(pve_get_system(300))
    assert sys_detail["status"] == "success"
    assert sys_detail["system"]["type"] == "lxc"

    # 6. Guest network
    e2e_harness._api.nodes("pve-node1").lxc(300).interfaces.get.return_value = [
        {"name": "eth0", "inet": "192.168.10.150/24"}
    ]
    net_res = json.loads(pve_get_guest_network(300))
    assert net_res["status"] == "success"
    assert net_res["network"]["interfaces"][0]["inet"] == "192.168.10.150/24"


# ==============================================================================
# Phase 2: Provisioning, Configuration & IaC
# ==============================================================================
def test_e2e_phase2_provision_and_iac(e2e_harness):
    # 1. Create LXC
    e2e_harness._api.nodes("pve-node1").lxc.post.return_value = "UPID:pve-node1:0001:create"
    lxc_res = json.loads(pve_create_lxc(
        vmid=310,
        hostname="ci-worker",
        ostemplate="local:vztmpl/debian-12.tar.zst",
        cores=2,
        memory_mb=2048,
        disk_gb=15
    ))
    assert lxc_res["status"] == "success"

    # 2. Create VM
    e2e_harness._api.nodes("pve-node1").qemu.post.return_value = "UPID:pve-node1:0002:create"
    vm_res = json.loads(pve_create_vm(
        vmid=320,
        name="ubuntu-agent",
        cores=4,
        memory_mb=4096,
        disk_gb=30
    ))
    assert vm_res["status"] == "success"

    # 3. Cloud-Init VM config
    e2e_harness._api.nodes("pve-node1").qemu(320).config.post.return_value = "OK"
    ci_res = json.loads(pve_set_cloudinit(
        vmid=320,
        ciuser="ubuntu",
        ipconfig0="ip=192.168.10.160/24,gw=192.168.10.1"
    ))
    assert ci_res["status"] == "success"
    assert ci_res["result"]["cloudinit"]["ciuser"] == "ubuntu"

    # 4. Edit hardware allocations
    e2e_harness._api.nodes("pve-node1").lxc(300).config.put.return_value = "OK"
    edit_res = json.loads(pve_edit_system(vmid=300, cores=4, memory_mb=4096, tags="ci;worker"))
    assert edit_res["status"] == "success"
    assert edit_res["result"]["updated"]["cores"] == 4

    # 5. Resize disk
    e2e_harness._api.nodes("pve-node1").lxc(300).resize.put.return_value = "UPID:pve-node1:0003:resize"
    resize_res = json.loads(pve_resize_disk(vmid=300, disk="rootfs", add_gb=5))
    assert resize_res["status"] == "success"

    # 6. Export Terraform HCL
    e2e_harness._api.nodes("pve-node1").lxc(300).config.get.return_value = {
        "hostname": "test-scratch-lxc",
        "cores": 4,
        "memory": 4096,
        "rootfs": "local-zfs:subvol-300-disk-0,size=15G"
    }
    e2e_harness._api.nodes("pve-node1").lxc(300).status.current.get.return_value = {"status": "running"}
    tf_res = json.loads(pve_export_terraform(300))
    assert tf_res["status"] == "success"
    assert 'resource "proxmox_lxc" "lxc_300"' in tf_res["terraform_hcl"]


# ==============================================================================
# Phase 3: Lifecycle, Snapshots & Backups
# ==============================================================================
def test_e2e_phase3_lifecycle_snapshots_backups(e2e_harness):
    # 1. Lifecycle start
    e2e_harness._api.nodes("pve-node1").lxc(300).status.start.post.return_value = "UPID:pve-node1:0004:start"
    life_res = json.loads(pve_lifecycle(vmid=300, action="start"))
    assert life_res["status"] == "success"

    # 2. Create snapshot
    e2e_harness._api.nodes("pve-node1").lxc(300).snapshot.post.return_value = "UPID:pve-node1:0005:snapshot"
    snap_res = json.loads(pve_create_snapshot(vmid=300, snapname="pre-e2e-patch", description="E2E Snapshot"))
    assert snap_res["status"] == "success"

    # 3. List snapshots
    e2e_harness._api.nodes("pve-node1").lxc(300).snapshot.get.return_value = [
        {"name": "pre-e2e-patch", "description": "E2E Snapshot", "snaptime": 1700000000}
    ]
    snaps_list = json.loads(pve_list_snapshots(300))
    assert snaps_list["status"] == "success"
    assert len(snaps_list["snapshots"]) == 1

    # 4. Rollback snapshot
    e2e_harness._api.nodes("pve-node1").lxc(300).snapshot("pre-e2e-patch").rollback.post.return_value = "UPID:pve-node1:0006:rollback"
    rb_res = json.loads(pve_rollback_snapshot(vmid=300, snapname="pre-e2e-patch", start_after=True))
    assert rb_res["status"] == "success"

    # 5. Delete snapshot without confirmation -> BLOCKED
    del_snap_block = json.loads(pve_delete_snapshot(vmid=300, snapname="pre-e2e-patch", confirmation_phrase=""))
    assert del_snap_block["status"] == "confirmation_required"
    assert del_snap_block["required_params"]["confirmation_phrase"] == "CONFIRM_DELETE_SNAPSHOT_pre-e2e-patch"

    # 6. Delete snapshot with confirmation -> PROCEEDS
    e2e_harness._api.nodes("pve-node1").lxc(300).snapshot("pre-e2e-patch").delete.return_value = "UPID:pve-node1:0007:delsnap"
    del_snap_ok = json.loads(pve_delete_snapshot(vmid=300, snapname="pre-e2e-patch", confirmation_phrase="CONFIRM_DELETE_SNAPSHOT_pre-e2e-patch"))
    assert del_snap_ok["success"] is True

    # 7. Backup trigger
    e2e_harness._api.nodes("pve-node1").vzdump.post.return_value = "UPID:pve-node1:0008:vzdump"
    bak_res = json.loads(pve_trigger_backup(vmid=300, storage="local"))
    assert bak_res["status"] == "success"


# ==============================================================================
# Phase 4: Cluster Intelligence & Advanced Tools
# ==============================================================================
def test_e2e_phase4_intelligence_and_firewall(e2e_harness):
    # 1. Cluster placement advisory (Node 2 has 120GB free RAM, Node 1 has 48GB free)
    place_res = json.loads(pve_recommend_placement(required_cores=4, required_mem_mb=16384))
    assert place_res["status"] == "success"
    # Node 2 has lower CPU (5%) and larger free RAM (120GB)
    assert place_res["advisory"]["recommended_node"] == "pve-node2"

    # 2. VNC console access ticket
    e2e_harness._api.nodes("pve-node1").lxc(300).vncproxy.post.return_value = {
        "ticket": "VNC_TEST_TICKET_999",
        "port": 5900
    }
    vnc_res = json.loads(pve_get_vnc_ticket(300))
    assert vnc_res["status"] == "success"
    assert "https://192.168.10.10:8006" in vnc_res["vnc"]["vnc_url"]

    # 3. Firewall rule management
    e2e_harness._api.nodes("pve-node1").lxc(300).firewall.rules.post.return_value = "OK"
    fw_res = json.loads(pve_set_firewall_rule(vmid=300, action="ACCEPT", proto="tcp", dport="80,443", comment="Web Traffic"))
    assert fw_res["status"] == "success"
    assert fw_res["result"]["rule"]["action"] == "ACCEPT"


# ==============================================================================
# Phase 5: Self-Protection & Destructive Safety Gates
# ==============================================================================
def test_e2e_phase5_safety_and_self_protection(e2e_harness):
    # 1. Attempt to stop self container (VMID 299) -> HARD BLOCKED
    self_stop = json.loads(pve_lifecycle(vmid=299, action="stop"))
    assert self_stop["status"] == "error"
    assert "Self-Protection Block" in self_stop["error"]

    # 2. Attempt to destroy self container (VMID 299) -> HARD BLOCKED
    self_destroy = json.loads(pve_destroy_system(vmid=299, confirm_vmid=299, confirmation_phrase="CONFIRM_DELETE_299"))
    assert self_destroy["status"] == "error"
    assert "Self-Protection Block" in self_destroy["error"]

    # 3. Attempt to destroy blacklisted VM 101 -> PERMISSION ERROR
    bl_destroy = json.loads(pve_destroy_system(vmid=101, confirm_vmid=101, confirmation_phrase="CONFIRM_DELETE_101"))
    assert bl_destroy["status"] == "error"
    assert "protected systems blacklist" in bl_destroy["error"]

    # 4. Attempt to destroy VM 300 without confirmation -> CONFIRMATION REQUIRED
    del_prompt = json.loads(pve_destroy_system(vmid=300, confirm_vmid=300, confirmation_phrase=""))
    assert del_prompt["status"] == "confirmation_required"
    assert del_prompt["required_params"]["confirmation_phrase"] == "CONFIRM_DELETE_300"

    # 5. Successfully destroy VM 300 with exact matching confirmation -> PROCEEDS
    e2e_harness._api.nodes("pve-node1").lxc(300).status.stop.post.return_value = "OK"
    e2e_harness._api.nodes("pve-node1").lxc(300).delete.return_value = "UPID:pve-node1:0009:destroy"
    del_ok = json.loads(pve_destroy_system(vmid=300, confirm_vmid=300, confirmation_phrase="CONFIRM_DELETE_300"))
    assert del_ok["success"] is True
    assert del_ok["destroyed_vmid"] == 300
