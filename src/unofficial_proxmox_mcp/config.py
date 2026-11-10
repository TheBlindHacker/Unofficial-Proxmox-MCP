"""
Configuration loader for Unofficial-Proxmox-MCP.
Reads from environment variables, optional .env files, and self-container detection.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Automatically load .env if present in current directory or project root
load_dotenv()


def detect_self_vmid() -> Optional[int]:
    """
    Attempt to auto-detect if this process is executing inside an LXC container on Proxmox.
    Checks PVE_SELF_VMID env, /etc/pve-self-vmid marker, or hostname patterns.
    """
    # 1. Direct env variable
    env_self = os.getenv("PVE_SELF_VMID", "").strip()
    if env_self.isdigit():
        return int(env_self)

    # 2. File written by installer inside container
    marker_file = Path("/etc/pve-self-vmid")
    if marker_file.exists():
        try:
            content = marker_file.read_text(encoding="utf-8").strip()
            if content.isdigit():
                return int(content)
        except Exception:
            pass

    return None


class PVEConfig(BaseModel):
    """Proxmox VE Connection, Safety Settings, and Self-Protection."""
    host: str = Field(default_factory=lambda: os.getenv("PVE_HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.getenv("PVE_PORT", "8006")))
    user: str = Field(default_factory=lambda: os.getenv("PVE_USER", "root@pam"))
    token_name: Optional[str] = Field(default_factory=lambda: os.getenv("PVE_TOKEN_NAME", None))
    token_secret: Optional[str] = Field(default_factory=lambda: os.getenv("PVE_TOKEN_SECRET", None))
    password: Optional[str] = Field(default_factory=lambda: os.getenv("PVE_PASSWORD", None))
    verify_ssl: bool = Field(
        default_factory=lambda: os.getenv("PVE_VERIFY_SSL", "false").lower() in ("1", "true", "yes")
    )
    default_node: str = Field(default_factory=lambda: os.getenv("PVE_NODE", "pve"))
    task_timeout: int = Field(default_factory=lambda: int(os.getenv("PVE_TASK_TIMEOUT", "300")))
    protected_vmids: List[int] = Field(default_factory=list)
    self_vmid: Optional[int] = Field(default_factory=detect_self_vmid)

    @classmethod
    def load(cls) -> "PVEConfig":
        """Instantiate settings with parsed protected VMIDs, token decomposition, and self-protection."""
        raw_protected = os.getenv("PVE_PROTECTED_VMIDS", "")
        protected_list: List[int] = []
        if raw_protected:
            for item in raw_protected.split(","):
                cleaned = item.strip()
                if cleaned.isdigit():
                    protected_list.append(int(cleaned))

        self_detected = detect_self_vmid()
        if self_detected and self_detected not in protected_list:
            protected_list.append(self_detected)

        user_str = os.getenv("PVE_USER", "root@pam")
        token_name = os.getenv("PVE_TOKEN_NAME", None)

        # Support user@realm!token format directly in PVE_USER (strip token if already present)
        if "!" in user_str:
            user_part, token_part = user_str.split("!", 1)
            user_str = user_part
            if not token_name:
                token_name = token_part

        return cls(
            host=os.getenv("PVE_HOST", "127.0.0.1"),
            port=int(os.getenv("PVE_PORT", "8006")),
            user=user_str,
            token_name=token_name,
            token_secret=os.getenv("PVE_TOKEN_SECRET", None),
            password=os.getenv("PVE_PASSWORD", None),
            verify_ssl=os.getenv("PVE_VERIFY_SSL", "false").lower() in ("1", "true", "yes"),
            default_node=os.getenv("PVE_NODE", "pve"),
            task_timeout=int(os.getenv("PVE_TASK_TIMEOUT", "300")),
            protected_vmids=protected_list,
            self_vmid=self_detected,
        )

    def is_protected(self, vmid: int) -> bool:
        """Check whether a VMID is marked protected against deletion."""
        return (vmid in self.protected_vmids) or self.is_self(vmid)

    def is_self(self, vmid: int) -> bool:
        """Check whether a VMID matches this server's own host container."""
        return self.self_vmid is not None and vmid == self.self_vmid

    def auth_summary(self) -> str:
        """Return a non-leaking diagnostic summary of authentication mode."""
        if self.token_name and self.token_secret:
            return f"API Token ({self.user}!{self.token_name})"
        elif self.password:
            return f"Password Auth ({self.user})"
        return "Unconfigured / Missing Credentials"
