"""Tests for FastMCP tool wrappers, error boundaries, and confirmation flows."""

import json
from unittest.mock import MagicMock, patch
import pytest
from unofficial_proxmox_mcp.server import (
    pve_list_nodes,
    pve_get_node_status,
    pve_list_storage_pools,
    pve_list_systems,
    pve_get_system,
    pve_get_guest_network,
    pve_lifecycle,
    pve_create_snapshot,
    pve_rollback_snapshot,
    pve_delete_snapshot,
    pve_edit_system,
    pve_set_cloudinit,
    pve_resize_disk,
    pve_trigger_backup,
    pve_list_backups,
    pve_get_firewall,
    pve_set_firewall_rule,
    pve_recommend_placement,
    pve_get_vnc_ticket,
    pve_export_terraform,
    pve_destroy_system,
)


@pytest.fixture
def mock_client():
    with patch("unofficial_proxmox_mcp.server.get_client") as mock_get:
        client_instance = MagicMock()
        mock_get.return_value = client_instance
        yield client_instance


def test_pve_list_nodes_success(mock_client):
    mock_client.list_nodes.return_value = [
        {"node": "pve", "status": "online", "cpu": 12.5, "mem_mb": 16384, "maxmem_mb": 65536}
    ]
    res_raw = pve_list_nodes()
    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["node"] == "pve"


def test_pve_trigger_backup_success(mock_client):
    mock_client.trigger_backup.return_value = {"success": True, "vmid": 101, "storage": "local"}
    res_raw = pve_trigger_backup(vmid=101, storage="local")
    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["result"]["vmid"] == 101


def test_pve_list_backups_success(mock_client):
    mock_client.list_backups.return_value = [
        {"volid": "local:backup/vzdump-qemu-101.vma.zst", "vmid": 101, "size_mb": 2048.5}
    ]
    res_raw = pve_list_backups(storage="local")
    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["count"] == 1


def test_pve_recommend_placement_success(mock_client):
    mock_client.recommend_placement.return_value = {
        "recommended_node": "pve-node2",
        "evaluations": [{"node": "pve-node2", "score": 85.0}],
    }
    res_raw = pve_recommend_placement(required_cores=4, required_mem_mb=8192)
    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["advisory"]["recommended_node"] == "pve-node2"


def test_pve_get_vnc_ticket_success(mock_client):
    mock_client.get_vnc_ticket.return_value = {
        "vmid": 101,
        "vnc_url": "https://pve:8006/?console=qemu&vmid=101",
        "ticket": "OK",
    }
    res_raw = pve_get_vnc_ticket(vmid=101)
    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert "vnc_url" in data["vnc"]


def test_pve_export_terraform_success(mock_client):
    mock_client.export_terraform.return_value = 'resource "proxmox_vm_qemu" "vm_101" {}'
    res_raw = pve_export_terraform(vmid=101)
    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert "proxmox_vm_qemu" in data["terraform_hcl"]


def test_pve_destroy_system_requires_confirmation(mock_client):
    mock_client.destroy_system.return_value = {
        "status": "confirmation_required",
        "action": "destroy_system",
        "vmid": 300,
        "message": "DESTRUCTION BLOCKED: Deletion of QEMU 300 requires explicit user confirmation.",
        "required_params": {"confirm_vmid": 300, "confirmation_phrase": "CONFIRM_DELETE_300"},
    }
    res_raw = pve_destroy_system(vmid=300, confirm_vmid=300, confirmation_phrase="")
    data = json.loads(res_raw)
    assert data["status"] == "confirmation_required"
    assert "required_params" in data
    assert data["required_params"]["confirmation_phrase"] == "CONFIRM_DELETE_300"
