"""Tests for PVEConfig settings, self-protection, and token parsing."""

import os
import pytest
from unofficial_proxmox_mcp.config import PVEConfig, detect_self_vmid


def test_default_config():
    cfg = PVEConfig()
    assert cfg.port == 8006
    assert cfg.default_node == "pve"
    assert cfg.verify_ssl is False
    assert cfg.protected_vmids == []


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
