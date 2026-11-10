"""Tests for PVEConfig settings, self-protection, and token parsing."""

from unofficial_proxmox_mcp.config import PVEConfig


def test_default_config(monkeypatch):
    monkeypatch.delenv("PVE_NODE", raising=False)
    monkeypatch.delenv("PVE_PORT", raising=False)
    monkeypatch.delenv("PVE_VERIFY_SSL", raising=False)
    cfg = PVEConfig()
    assert cfg.port == 8006
    assert cfg.default_node == "pve"
    assert cfg.verify_ssl is False
    assert cfg.protected_vmids == []


def test_token_parsing_strips_user_part(monkeypatch):
    monkeypatch.setenv("PVE_USER", "mcp-bot@pve!mcp-token")
    monkeypatch.setenv("PVE_TOKEN_NAME", "mcp-token")
    monkeypatch.setenv("PVE_TOKEN_SECRET", "11111111-2222-3333-4444-555555555555")
    cfg = PVEConfig.load()
    assert cfg.user == "mcp-bot@pve"
    assert cfg.token_name == "mcp-token"
    assert cfg.auth_summary() == "API Token (mcp-bot@pve!mcp-token)"


def test_protected_vmids_parsing(monkeypatch):
    monkeypatch.setenv("PVE_PROTECTED_VMIDS", "100, 101, 204, abc, 205")
    cfg = PVEConfig.load()
    assert cfg.protected_vmids == [100, 101, 204, 205]
    assert cfg.is_protected(101) is True
    assert cfg.is_protected(204) is True
    assert cfg.is_protected(999) is False


def test_self_vmid_detection_and_auto_protect(monkeypatch):
    monkeypatch.setenv("PVE_SELF_VMID", "299")
    monkeypatch.setenv("PVE_PROTECTED_VMIDS", "100, 101")
    cfg = PVEConfig.load()
    assert cfg.self_vmid == 299
    assert cfg.is_self(299) is True
    assert cfg.is_protected(299) is True
    assert 299 in cfg.protected_vmids


def test_user_token_decomposition(monkeypatch):
    monkeypatch.setenv("PVE_USER", "mcp-bot@pve!mcp-token")
    monkeypatch.delenv("PVE_TOKEN_NAME", raising=False)
    cfg = PVEConfig.load()
    assert cfg.user == "mcp-bot@pve"
    assert cfg.token_name == "mcp-token"


def test_auth_summary_no_secret_leak():
    cfg = PVEConfig(
        user="mcp-bot@pve",
        token_name="mcp-token",
        token_secret="super-secret-uuid-1234",
    )
    summary = cfg.auth_summary()
    assert "mcp-bot@pve!mcp-token" in summary
    assert "super-secret" not in summary
