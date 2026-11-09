"""Tests for PVEClient logic, guardrails, task polling, self-protection, and confirmations."""

from unittest.mock import MagicMock, patch
import pytest
from unofficial_proxmox_mcp.config import PVEConfig
from unofficial_proxmox_mcp.client import PVEClient


@pytest.fixture
def mock_config():
    return PVEConfig(
        host="192.168.1.50",
        port=8006,
        user="root@pam",
        token_name="test_token",
        token_secret="test_secret",
        verify_ssl=False,
        default_node="pve",
        protected_vmids=[101, 204],
        self_vmid=299,
    )


def test_destroy_guardrail_confirmation_prompt(mock_config):
    with patch("unofficial_proxmox_mcp.client.ProxmoxAPI"):
        client = PVEClient(mock_config)
        client.locate_system = MagicMock(return_value=("pve", "lxc"))
        
        res = client.destroy_system(vmid=300, confirm_vmid=300, confirmation_phrase="")
        assert res["status"] == "confirmation_required"
        assert "DESTRUCTION BLOCKED" in res["message"]
        assert res["required_params"]["confirmation_phrase"] == "CONFIRM_DELETE_300"


def test_destroy_self_protection_block(mock_config):
    """Ensure attempting to destroy the self-hosting container is strictly refused."""
    with patch("unofficial_proxmox_mcp.client.ProxmoxAPI"):
        client = PVEClient(mock_config)
        with pytest.raises(PermissionError, match="Self-Protection Block.*Cannot destroy VMID 299"):
            client.destroy_system(
                vmid=299,
                confirm_vmid=299,
                confirmation_phrase="CONFIRM_DELETE_299",
            )


def test_lifecycle_self_protection_block(mock_config):
    """Ensure attempting to stop/shutdown the self-hosting container is blocked."""
    with patch("unofficial_proxmox_mcp.client.ProxmoxAPI"):
        client = PVEClient(mock_config)
        with pytest.raises(PermissionError, match="Self-Protection Block.*Cannot execute 'stop' on VMID 299"):
            client.manage_lifecycle(vmid=299, action="stop")


def test_destroy_guardrail_protected_blacklist(mock_config):
    with patch("unofficial_proxmox_mcp.client.ProxmoxAPI"):
        client = PVEClient(mock_config)
        with pytest.raises(PermissionError, match="in the protected systems blacklist"):
            client.destroy_system(
                vmid=101,
                confirm_vmid=101,
                confirmation_phrase="CONFIRM_DELETE_101",
            )


def test_delete_snapshot_confirmation_prompt(mock_config):
    with patch("unofficial_proxmox_mcp.client.ProxmoxAPI"):
        client = PVEClient(mock_config)
        res = client.delete_snapshot(vmid=200, snapname="backup-v1", confirmation_phrase="")
        assert res["status"] == "confirmation_required"
        assert res["required_params"]["confirmation_phrase"] == "CONFIRM_DELETE_SNAPSHOT_backup-v1"


def test_invalid_lifecycle_action(mock_config):
    with patch("unofficial_proxmox_mcp.client.ProxmoxAPI"):
        client = PVEClient(mock_config)
        with pytest.raises(ValueError, match="Invalid lifecycle action"):
            client.manage_lifecycle(vmid=300, action="explode")


def test_missing_credentials_error():
    cfg = PVEConfig(
        host="192.168.1.50",
        user="root@pam",
        token_name=None,
        token_secret=None,
        password=None,
    )
    with pytest.raises(ValueError, match="No valid authentication credentials found"):
        PVEClient(cfg)
