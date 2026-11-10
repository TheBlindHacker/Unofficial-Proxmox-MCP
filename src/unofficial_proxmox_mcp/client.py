"""
Proxmox VE REST API client wrapper with task polling, self-protection, and safety guardrails.
"""

from __future__ import annotations
import time
import warnings
from typing import Any, Dict, List, Optional, Tuple
import urllib3
from proxmoxer import ProxmoxAPI
from .config import PVEConfig


class PVEClient:
    """High-level client for Proxmox VE REST API interactions."""

    def __init__(self, config: Optional[PVEConfig] = None) -> None:
        self.config = config or PVEConfig.load()
        self._cached_node: Optional[str] = None
        if not self.config.verify_ssl:
            # Suppress InsecureRequestWarning to protect MCP stdio JSON-RPC streams
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

        self._api = self._init_api()

    def resolve_node(self, node: Optional[str] = None) -> str:
        """
        Resolve target node name. If node is provided, returns it.
        Otherwise, validates self.config.default_node against cluster nodes,
        auto-discovering the first online node if default_node is invalid or unset.
        """
        if node:
            return node
        if self._cached_node:
            return self._cached_node

        try:
            nodes = self.list_nodes()
            online_nodes = [n["node"] for n in nodes if n.get("status") == "online"]
            if self.config.default_node and self.config.default_node in online_nodes:
                self._cached_node = self.config.default_node
                return self._cached_node
            if online_nodes:
                self._cached_node = online_nodes[0]
                return self._cached_node
        except Exception:
            pass

        return self.config.default_node or "pve"

    def _init_api(self) -> ProxmoxAPI:
        """Initialize Proxmoxer API client with token or password authentication."""
        kwargs: Dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "verify_ssl": self.config.verify_ssl,
            "timeout": 30,
        }

        if self.config.token_name and self.config.token_secret:
            kwargs["token_name"] = self.config.token_name
            kwargs["token_value"] = self.config.token_secret
        elif self.config.password:
            kwargs["password"] = self.config.password
        else:
            raise ValueError(
                "No valid authentication credentials found. Provide either "
                "PVE_TOKEN_NAME & PVE_TOKEN_SECRET or PVE_PASSWORD in environment."
            )

        return ProxmoxAPI(**kwargs)

    # --------------------------------------------------------------------------
    # Task Polling
    # --------------------------------------------------------------------------
    def wait_for_task(self, node: str, upid: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Poll a Proxmox task UPID until it finishes or reaches timeout."""
        timeout_sec = timeout or self.config.task_timeout
        start_time = time.time()
        last_status: Dict[str, Any] = {}

        while time.time() - start_time < timeout_sec:
            try:
                task_data = self._api.nodes(node).tasks(upid).status.get()
                last_status = task_data
                if task_data.get("status") == "stopped":
                    exit_status = task_data.get("exitstatus", "")
                    if exit_status == "OK":
                        return {
                            "success": True,
                            "upid": upid,
                            "exitstatus": "OK",
                            "elapsed_seconds": round(time.time() - start_time, 2),
                        }
                    else:
                        return {
                            "success": False,
                            "upid": upid,
                            "error": exit_status or "Task failed without exitstatus details",
                            "elapsed_seconds": round(time.time() - start_time, 2),
                        }
            except Exception as e:
                last_status = {"error": str(e)}

            time.sleep(1.5)

        return {
            "success": False,
            "upid": upid,
            "error": f"Task timed out after {timeout_sec} seconds. Last status: {last_status}",
            "elapsed_seconds": round(time.time() - start_time, 2),
        }

    # --------------------------------------------------------------------------
    # System Discovery & Location Helpers
    # --------------------------------------------------------------------------
    def list_nodes(self) -> List[Dict[str, Any]]:
        """List all cluster nodes with online status and resource metrics."""
        raw_nodes = self._api.nodes.get()
        nodes: List[Dict[str, Any]] = []
        for n in raw_nodes:
            nodes.append({
                "node": n.get("node"),
                "status": n.get("status"),
                "cpu": round(n.get("cpu", 0) * 100, 2) if n.get("cpu") else 0.0,
                "maxcpu": n.get("maxcpu"),
                "mem_mb": round(n.get("mem", 0) / (1024 * 1024), 1) if n.get("mem") else 0,
                "maxmem_mb": round(n.get("maxmem", 0) / (1024 * 1024), 1) if n.get("maxmem") else 0,
                "uptime": n.get("uptime"),
                "ssl_fingerprint": n.get("ssl_fingerprint"),
            })
        return nodes

    def get_node_status(self, node: Optional[str] = None) -> Dict[str, Any]:
        """Fetch deep hardware, kernel, PVE version, and memory telemetry for a node."""
        target_node = self.resolve_node(node)
        status_data = self._api.nodes(target_node).status.get()
        version_data = self._api.version.get()
        return {
            "node": target_node,
            "pve_version": version_data.get("version", "unknown"),
            "pve_release": version_data.get("release", "unknown"),
            "kernel_version": status_data.get("kversion", "unknown"),
            "uptime_seconds": status_data.get("uptime", 0),
            "cpu_model": status_data.get("cpuinfo", {}).get("model", "unknown"),
            "cpu_cores": status_data.get("cpuinfo", {}).get("cores", 0),
            "cpu_sockets": status_data.get("cpuinfo", {}).get("sockets", 0),
            "cpu_usage_pct": round(status_data.get("cpu", 0) * 100, 2),
            "load_average": status_data.get("loadavg", []),
            "memory": {
                "used_mb": round(status_data.get("memory", {}).get("used", 0) / (1024 * 1024), 1),
                "total_mb": round(status_data.get("memory", {}).get("total", 0) / (1024 * 1024), 1),
                "free_mb": round(status_data.get("memory", {}).get("free", 0) / (1024 * 1024), 1),
            },
            "swap": {
                "used_mb": round(status_data.get("swap", {}).get("used", 0) / (1024 * 1024), 1),
                "total_mb": round(status_data.get("swap", {}).get("total", 0) / (1024 * 1024), 1),
                "free_mb": round(status_data.get("swap", {}).get("free", 0) / (1024 * 1024), 1),
            },
        }

    def list_storage_pools(self, node: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all cluster or node storage pools (ZFS, LVM, Directory, NFS) and capabilities."""
        target_node = self.resolve_node(node)
        raw_storage = self._api.nodes(target_node).storage.get()
        storage_list: List[Dict[str, Any]] = []
        for s in raw_storage:
            total_bytes = s.get("total", 0)
            used_bytes = s.get("used", 0)
            avail_bytes = s.get("avail", 0)
            storage_list.append({
                "storage": s.get("storage"),
                "type": s.get("type"),
                "node": target_node,
                "content": s.get("content", ""),
                "enabled": bool(s.get("enabled", 1)),
                "active": bool(s.get("active", 1)),
                "shared": bool(s.get("shared", 0)),
                "total_gb": round(total_bytes / (1024 ** 3), 2) if total_bytes else 0.0,
                "used_gb": round(used_bytes / (1024 ** 3), 2) if used_bytes else 0.0,
                "free_gb": round(avail_bytes / (1024 ** 3), 2) if avail_bytes else 0.0,
                "usage_pct": round((used_bytes / total_bytes) * 100, 1) if total_bytes else 0.0,
            })
        return storage_list

    def locate_system(self, vmid: int, node: Optional[str] = None) -> Tuple[str, str]:
        """
        Locate which node a VMID resides on and whether it is 'qemu' (VM) or 'lxc' (Container).
        Returns: (node_name, system_type)
        Raises: ValueError if system is not found.
        """
        nodes_to_search = [node] if node and node.lower() != "all" else [n["node"] for n in self.list_nodes()]

        for n in nodes_to_search:
            # Check QEMU VMs
            try:
                qemu_list = self._api.nodes(n).qemu.get()
                for vm in qemu_list:
                    if int(vm.get("vmid", -1)) == vmid:
                        return n, "qemu"
            except Exception:
                pass

            # Check LXC Containers
            try:
                lxc_list = self._api.nodes(n).lxc.get()
                for c in lxc_list:
                    if int(c.get("vmid", -1)) == vmid:
                        return n, "lxc"
            except Exception:
                pass

        raise ValueError(f"System with VMID {vmid} could not be found across cluster nodes {nodes_to_search}.")

    def list_systems(
        self,
        node: Optional[str] = None,
        type_filter: str = "all",
        status_filter: str = "all"
    ) -> List[Dict[str, Any]]:
        """List all virtual machines and LXC containers across nodes."""
        nodes_to_query = [node] if node and node.lower() != "all" else [n["node"] for n in self.list_nodes()]
        results: List[Dict[str, Any]] = []

        for n in nodes_to_query:
            # 1. QEMU VMs
            if type_filter.lower() in ("all", "qemu", "vm"):
                try:
                    for vm in self._api.nodes(n).qemu.get():
                        status = vm.get("status", "unknown")
                        if status_filter.lower() != "all" and status != status_filter.lower():
                            continue
                        vmid_int = int(vm.get("vmid"))
                        results.append({
                            "vmid": vmid_int,
                            "name": vm.get("name", "unnamed"),
                            "type": "qemu",
                            "node": n,
                            "status": status,
                            "cpus": vm.get("cpus"),
                            "memory_mb": round(vm.get("maxmem", 0) / (1024 * 1024), 1) if vm.get("maxmem") else 0,
                            "disk_gb": round(vm.get("maxdisk", 0) / (1024 * 1024 * 1024), 2) if vm.get("maxdisk") else 0,
                            "uptime_seconds": vm.get("uptime", 0),
                            "tags": vm.get("tags", ""),
                            "is_template": bool(vm.get("template", 0)),
                            "is_protected": self.config.is_protected(vmid_int),
                            "is_self": self.config.is_self(vmid_int),
                        })
                except Exception:
                    pass

            # 2. LXC Containers
            if type_filter.lower() in ("all", "lxc", "container"):
                try:
                    for c in self._api.nodes(n).lxc.get():
                        status = c.get("status", "unknown")
                        if status_filter.lower() != "all" and status != status_filter.lower():
                            continue
                        vmid_int = int(c.get("vmid"))
                        results.append({
                            "vmid": vmid_int,
                            "name": c.get("name", "unnamed"),
                            "type": "lxc",
                            "node": n,
                            "status": status,
                            "cpus": c.get("cpus"),
                            "memory_mb": round(c.get("maxmem", 0) / (1024 * 1024), 1) if c.get("maxmem") else 0,
                            "disk_gb": round(c.get("maxdisk", 0) / (1024 * 1024 * 1024), 2) if c.get("maxdisk") else 0,
                            "uptime_seconds": c.get("uptime", 0),
                            "tags": c.get("tags", ""),
                            "is_template": bool(c.get("template", 0)),
                            "is_protected": self.config.is_protected(vmid_int),
                            "is_self": self.config.is_self(vmid_int),
                        })
                except Exception:
                    pass

        results.sort(key=lambda x: x["vmid"])
        return results

    def get_system(self, vmid: int, node: Optional[str] = None) -> Dict[str, Any]:
        """Fetch full configuration and current status of a specific VM or LXC container."""
        target_node, system_type = self.locate_system(vmid, node)

        if system_type == "qemu":
            config = self._api.nodes(target_node).qemu(vmid).config.get()
            status = self._api.nodes(target_node).qemu(vmid).status.current.get()
        else:
            config = self._api.nodes(target_node).lxc(vmid).config.get()
            status = self._api.nodes(target_node).lxc(vmid).status.current.get()

        return {
            "vmid": vmid,
            "type": system_type,
            "node": target_node,
            "is_protected": self.config.is_protected(vmid),
            "is_self": self.config.is_self(vmid),
            "status": status,
            "config": config,
        }

    def get_guest_network(self, vmid: int, node: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve live IP addresses and network interfaces (via Guest Agent or container config)."""
        target_node, system_type = self.locate_system(vmid, node)

        if system_type == "qemu":
            try:
                res = self._api.nodes(target_node).qemu(vmid).agent("network-get-interfaces").get()
                interfaces = res.get("result", [])
                return {
                    "vmid": vmid,
                    "type": "qemu",
                    "agent_active": True,
                    "interfaces": interfaces,
                }
            except Exception as e:
                config = self._api.nodes(target_node).qemu(vmid).config.get()
                return {
                    "vmid": vmid,
                    "type": "qemu",
                    "agent_active": False,
                    "agent_error": str(e),
                    "configured_net": {k: v for k, v in config.items() if k.startswith("net")},
                }
        else:
            try:
                res = self._api.nodes(target_node).lxc(vmid).interfaces.get()
                return {
                    "vmid": vmid,
                    "type": "lxc",
                    "interfaces": res,
                }
            except Exception as e:
                config = self._api.nodes(target_node).lxc(vmid).config.get()
                return {
                    "vmid": vmid,
                    "type": "lxc",
                    "interfaces_error": str(e),
                    "configured_net": {k: v for k, v in config.items() if k.startswith("net")},
                }

    def exec_guest_command(
        self,
        vmid: int,
        command: str,
        node: Optional[str] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Execute a non-interactive shell command inside a QEMU VM via QEMU Guest Agent."""
        target_node, system_type = self.locate_system(vmid, node)

        if system_type != "qemu":
            raise ValueError(f"Guest agent execution via REST API is supported for QEMU VMs. System {vmid} is LXC.")

        parts = ["/bin/sh", "-c", command]
        exec_init = self._api.nodes(target_node).qemu(vmid).agent.exec.post(command=parts)
        pid = exec_init.get("pid")
        if not pid:
            return {"success": False, "error": f"Failed to get PID from agent execution: {exec_init}"}

        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self._api.nodes(target_node).qemu(vmid).agent("exec-status").get(pid=pid)
            if status.get("exited", 0) == 1:
                return {
                    "success": status.get("exitcode", 0) == 0,
                    "exitcode": status.get("exitcode", 0),
                    "out_data": status.get("out-data", ""),
                    "err_data": status.get("err-data", ""),
                    "elapsed_seconds": round(time.time() - start_time, 2),
                }
            time.sleep(1.0)

        return {"success": False, "error": f"Agent command timed out after {timeout} seconds", "pid": pid}

    # --------------------------------------------------------------------------
    # Lifecycle Management (with Self-Protection)
    # --------------------------------------------------------------------------
    def manage_lifecycle(self, vmid: int, action: str, node: Optional[str] = None) -> Dict[str, Any]:
        """Execute lifecycle action on a system."""
        valid_actions = {"start", "stop", "shutdown", "reboot", "reset", "suspend", "resume"}
        action_clean = action.lower().strip()
        if action_clean not in valid_actions:
            raise ValueError(f"Invalid lifecycle action '{action}'. Must be one of: {sorted(list(valid_actions))}")

        # Self-Protection check
        if self.config.is_self(vmid) and action_clean in ("stop", "shutdown", "reset", "suspend"):
            raise PermissionError(
                f"Self-Protection Block: Cannot execute '{action_clean}' on VMID {vmid} because it hosts this MCP server."
            )

        target_node, system_type = self.locate_system(vmid, node)

        if system_type == "qemu":
            endpoint = getattr(self._api.nodes(target_node).qemu(vmid).status, action_clean)
        else:
            endpoint = getattr(self._api.nodes(target_node).lxc(vmid).status, action_clean)

        upid = endpoint.post()
        if isinstance(upid, str) and upid.startswith("UPID:"):
            return self.wait_for_task(target_node, upid)

        return {"success": True, "action": action_clean, "vmid": vmid, "response": upid}

    # --------------------------------------------------------------------------
    # Snapshot Management
    # --------------------------------------------------------------------------
    def create_snapshot(
        self,
        vmid: int,
        snapname: str,
        description: str = "",
        vmstate: bool = False,
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a snapshot of a VM or container."""
        target_node, system_type = self.locate_system(vmid, node)
        payload: Dict[str, Any] = {"snapname": snapname, "description": description}

        if system_type == "qemu" and vmstate:
            payload["vmstate"] = 1

        if system_type == "qemu":
            upid = self._api.nodes(target_node).qemu(vmid).snapshot.post(**payload)
        else:
            upid = self._api.nodes(target_node).lxc(vmid).snapshot.post(**payload)

        if isinstance(upid, str) and upid.startswith("UPID:"):
            task_res = self.wait_for_task(target_node, upid)
            task_res["snapname"] = snapname
            task_res["vmid"] = vmid
            return task_res

        return {"success": True, "vmid": vmid, "snapname": snapname, "response": upid}

    def list_snapshots(self, vmid: int, node: Optional[str] = None) -> List[Dict[str, Any]]:
        """List snapshots for a VM or container."""
        target_node, system_type = self.locate_system(vmid, node)
        if system_type == "qemu":
            return self._api.nodes(target_node).qemu(vmid).snapshot.get()
        return self._api.nodes(target_node).lxc(vmid).snapshot.get()

    def rollback_snapshot(
        self,
        vmid: int,
        snapname: str,
        start_after: bool = False,
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Roll back a VM or container to a specific snapshot."""
        target_node, system_type = self.locate_system(vmid, node)
        payload: Dict[str, Any] = {"start": 1 if start_after else 0}

        if system_type == "qemu":
            upid = self._api.nodes(target_node).qemu(vmid).snapshot(snapname).rollback.post(**payload)
        else:
            upid = self._api.nodes(target_node).lxc(vmid).snapshot(snapname).rollback.post(**payload)

        if isinstance(upid, str) and upid.startswith("UPID:"):
            task_res = self.wait_for_task(target_node, upid)
            task_res["rollback_target"] = snapname
            task_res["vmid"] = vmid
            return task_res

        return {"success": True, "vmid": vmid, "rollback_target": snapname, "response": upid}

    def delete_snapshot(
        self,
        vmid: int,
        snapname: str,
        confirmation_phrase: str = "",
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delete a snapshot with mandatory confirmation safety gate."""
        required_phrase = f"CONFIRM_DELETE_SNAPSHOT_{snapname}"
        if confirmation_phrase != required_phrase:
            return {
                "status": "confirmation_required",
                "action": "delete_snapshot",
                "vmid": vmid,
                "snapname": snapname,
                "message": (
                    f"SNAPSHOT DELETION BLOCKED: Confirmation required. "
                    f"Please ask user to confirm and re-invoke with confirmation_phrase='{required_phrase}'."
                ),
                "required_params": {
                    "confirmation_phrase": required_phrase
                }
            }

        target_node, system_type = self.locate_system(vmid, node)

        if system_type == "qemu":
            upid = self._api.nodes(target_node).qemu(vmid).snapshot(snapname).delete()
        else:
            upid = self._api.nodes(target_node).lxc(vmid).snapshot(snapname).delete()

        if isinstance(upid, str) and upid.startswith("UPID:"):
            task_res = self.wait_for_task(target_node, upid)
            task_res["deleted_snapshot"] = snapname
            task_res["vmid"] = vmid
            return task_res

        return {"success": True, "vmid": vmid, "deleted_snapshot": snapname, "response": upid}

    # --------------------------------------------------------------------------
    # Backup Operations (vzdump & PBS)
    # --------------------------------------------------------------------------
    def trigger_backup(
        self,
        vmid: int,
        storage: str = "local",
        mode: str = "snapshot",
        compression: str = "zstd",
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute an immediate vzdump backup of a VM or container."""
        target_node, _ = self.locate_system(vmid, node)
        payload: Dict[str, Any] = {
            "vmid": vmid,
            "storage": storage,
            "mode": mode,
            "compress": compression,
        }
        upid = self._api.nodes(target_node).vzdump.post(**payload)
        if isinstance(upid, str) and upid.startswith("UPID:"):
            task_res = self.wait_for_task(target_node, upid, timeout=900)
            task_res["vmid"] = vmid
            task_res["storage"] = storage
            return task_res

        return {"success": True, "vmid": vmid, "response": upid}

    def list_backups(self, storage: str = "local", node: Optional[str] = None) -> List[Dict[str, Any]]:
        """List backup archive files stored in a designated storage pool."""
        target_node = self.resolve_node(node)
        raw_content = self._api.nodes(target_node).storage(storage).content.get(content="backup")
        backups: List[Dict[str, Any]] = []
        for b in raw_content:
            backups.append({
                "volid": b.get("volid"),
                "vmid": b.get("vmid"),
                "format": b.get("format"),
                "size_mb": round(b.get("size", 0) / (1024 * 1024), 2),
                "ctime": b.get("ctime"),
                "notes": b.get("notes", ""),
            })
        backups.sort(key=lambda x: x.get("ctime", 0), reverse=True)
        return backups

    # --------------------------------------------------------------------------
    # Firewall Operations
    # --------------------------------------------------------------------------
    def get_firewall(self, vmid: int, node: Optional[str] = None) -> Dict[str, Any]:
        """Get firewall rules and options for a VM or container."""
        target_node, system_type = self.locate_system(vmid, node)
        if system_type == "qemu":
            rules = self._api.nodes(target_node).qemu(vmid).firewall.rules.get()
            options = self._api.nodes(target_node).qemu(vmid).firewall.options.get()
        else:
            rules = self._api.nodes(target_node).lxc(vmid).firewall.rules.get()
            options = self._api.nodes(target_node).lxc(vmid).firewall.options.get()

        return {
            "vmid": vmid,
            "type": system_type,
            "firewall_enabled": bool(options.get("enable", 0)),
            "options": options,
            "rules": rules,
        }

    def set_firewall_rule(
        self,
        vmid: int,
        action: str,
        rule_type: str = "in",
        proto: str = "tcp",
        dport: str = "",
        comment: str = "",
        enable: bool = True,
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add or update a firewall rule on a VM or container."""
        target_node, system_type = self.locate_system(vmid, node)
        payload: Dict[str, Any] = {
            "action": action.upper(),
            "type": rule_type.lower(),
            "proto": proto.lower(),
            "enable": 1 if enable else 0,
        }
        if dport:
            payload["dport"] = dport
        if comment:
            payload["comment"] = comment

        if system_type == "qemu":
            res = self._api.nodes(target_node).qemu(vmid).firewall.rules.post(**payload)
        else:
            res = self._api.nodes(target_node).lxc(vmid).firewall.rules.post(**payload)

        return {"success": True, "vmid": vmid, "rule": payload, "response": res}

    # --------------------------------------------------------------------------
    # Placement & Resource Advisory
    # --------------------------------------------------------------------------
    def recommend_placement(
        self,
        required_cores: int = 2,
        required_mem_mb: int = 2048,
        required_disk_gb: int = 20
    ) -> Dict[str, Any]:
        """Analyze cluster nodes and recommend optimal placement based on CPU and RAM congestion."""
        nodes = self.list_nodes()
        candidates: List[Dict[str, Any]] = []

        for n in nodes:
            node_name = n["node"]
            if n["status"] != "online":
                continue

            free_mem = n["maxmem_mb"] - n["mem_mb"]
            score = 100.0 - n["cpu"] - ((n["mem_mb"] / n["maxmem_mb"]) * 100 if n["maxmem_mb"] else 0)

            has_capacity = free_mem >= required_mem_mb
            candidates.append({
                "node": node_name,
                "score": round(score, 1),
                "cpu_usage_pct": n["cpu"],
                "free_mem_mb": round(free_mem, 1),
                "eligible": has_capacity,
            })

        candidates.sort(key=lambda x: (x["eligible"], x["score"]), reverse=True)
        recommended = candidates[0]["node"] if candidates and candidates[0]["eligible"] else None

        return {
            "recommended_node": recommended,
            "required": {
                "cores": required_cores,
                "memory_mb": required_mem_mb,
                "disk_gb": required_disk_gb,
            },
            "evaluations": candidates,
        }

    # --------------------------------------------------------------------------
    # VNC & Console Access Ticket
    # --------------------------------------------------------------------------
    def get_vnc_ticket(self, vmid: int, node: Optional[str] = None) -> Dict[str, Any]:
        """Generate a time-limited NoVNC / SPICE terminal ticket and direct access URL."""
        target_node, system_type = self.locate_system(vmid, node)

        if system_type == "qemu":
            ticket_data = self._api.nodes(target_node).qemu(vmid).vncproxy.post()
        else:
            ticket_data = self._api.nodes(target_node).lxc(vmid).vncproxy.post()

        ticket = ticket_data.get("ticket", "")
        port = ticket_data.get("port", "")
        vnc_url = f"https://{self.config.host}:{self.config.port}/?console={system_type}&novnc=1&vmid={vmid}&node={target_node}"

        return {
            "vmid": vmid,
            "type": system_type,
            "node": target_node,
            "vnc_url": vnc_url,
            "port": port,
            "ticket": ticket,
        }

    # --------------------------------------------------------------------------
    # Terraform / OpenTofu Infrastructure-as-Code Exporter
    # --------------------------------------------------------------------------
    def export_terraform(self, vmid: int, node: Optional[str] = None) -> str:
        """Export an existing running VM or container into a clean Terraform / OpenTofu HCL block."""
        system_info = self.get_system(vmid, node)
        target_node = system_info["node"]
        sys_type = system_info["type"]
        cfg = system_info["config"]

        if sys_type == "qemu":
            hcl = f'''# Terraform / OpenTofu Configuration for VM {vmid}
resource "proxmox_vm_qemu" "vm_{vmid}" {{
  vmid        = {vmid}
  name        = "{cfg.get("name", f"vm-{vmid}")}"
  target_node = "{target_node}"
  cores       = {cfg.get("cores", 2)}
  sockets     = {cfg.get("sockets", 1)}
  memory      = {cfg.get("memory", 2048)}
  scsihw      = "{cfg.get("scsihw", "virtio-scsi-pci")}"
  boot        = "{cfg.get("boot", "order=scsi0")}"
  onboot      = {bool(cfg.get("onboot", 0))}

  network {{
    model  = "virtio"
    bridge = "vmbr0"
  }}
}}
'''
        else:
            hcl = f'''# Terraform / OpenTofu Configuration for LXC {vmid}
resource "proxmox_lxc" "lxc_{vmid}" {{
  vmid         = {vmid}
  hostname     = "{cfg.get("hostname", f"lxc-{vmid}")}"
  target_node  = "{target_node}"
  cores        = {cfg.get("cores", 2)}
  memory       = {cfg.get("memory", 1024)}
  swap         = {cfg.get("swap", 512)}
  unprivileged = {bool(cfg.get("unprivileged", 1))}
  onboot       = {bool(cfg.get("onboot", 0))}

  rootfs {{
    storage = "local-lvm"
    size    = "{cfg.get("rootfs", "8G").split("size=")[-1] if "size=" in str(cfg.get("rootfs")) else "8G"}"
  }}

  network {{
    name   = "eth0"
    bridge = "vmbr0"
    ip     = "dhcp"
  }}
}}
'''
        return hcl

    # --------------------------------------------------------------------------
    # System Modification & Resource Editing
    # --------------------------------------------------------------------------
    def edit_system(
        self,
        vmid: int,
        cores: Optional[int] = None,
        memory_mb: Optional[int] = None,
        description: Optional[str] = None,
        tags: Optional[str] = None,
        onboot: Optional[bool] = None,
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update system resource allocations, notes, tags, or onboot configuration."""
        target_node, system_type = self.locate_system(vmid, node)
        payload: Dict[str, Any] = {}

        if cores is not None:
            payload["cores"] = cores
        if memory_mb is not None:
            payload["memory"] = memory_mb
        if description is not None:
            payload["description"] = description
        if tags is not None:
            payload["tags"] = tags
        if onboot is not None:
            payload["onboot"] = 1 if onboot else 0

        if not payload:
            return {"success": True, "vmid": vmid, "message": "No parameters provided to update"}

        if system_type == "qemu":
            res = self._api.nodes(target_node).qemu(vmid).config.post(**payload)
        else:
            res = self._api.nodes(target_node).lxc(vmid).config.put(**payload)

        return {"success": True, "vmid": vmid, "updated": payload, "response": res}

    def set_cloudinit(
        self,
        vmid: int,
        ciuser: Optional[str] = None,
        cipassword: Optional[str] = None,
        sshkeys: Optional[str] = None,
        ipconfig0: Optional[str] = None,
        nameserver: Optional[str] = None,
        searchdomain: Optional[str] = None,
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Configure Cloud-Init credentials, SSH public keys, and network addressing for a VM."""
        target_node, system_type = self.locate_system(vmid, node)
        if system_type != "qemu":
            raise ValueError(f"Cloud-Init configuration is supported on QEMU VMs. System {vmid} is LXC.")

        payload: Dict[str, Any] = {}
        if ciuser:
            payload["ciuser"] = ciuser
        if cipassword:
            payload["cipassword"] = cipassword
        if sshkeys:
            payload["sshkeys"] = sshkeys
        if ipconfig0:
            payload["ipconfig0"] = ipconfig0
        if nameserver:
            payload["nameserver"] = nameserver
        if searchdomain:
            payload["searchdomain"] = searchdomain

        if not payload:
            return {"success": True, "vmid": vmid, "message": "No Cloud-Init parameters provided"}

        res = self._api.nodes(target_node).qemu(vmid).config.post(**payload)
        return {"success": True, "vmid": vmid, "cloudinit": payload, "response": res}

    def resize_disk(
        self,
        vmid: int,
        disk: str,
        add_gb: int,
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Incrementally resize a virtual disk."""
        target_node, system_type = self.locate_system(vmid, node)
        size_str = f"+{add_gb}G"
        payload = {"disk": disk, "size": size_str}

        if system_type == "qemu":
            upid = self._api.nodes(target_node).qemu(vmid).resize.put(**payload)
        else:
            upid = self._api.nodes(target_node).lxc(vmid).resize.put(**payload)

        if isinstance(upid, str) and upid.startswith("UPID:"):
            task_res = self.wait_for_task(target_node, upid)
            task_res["disk"] = disk
            task_res["added_gb"] = add_gb
            return task_res

        return {"success": True, "vmid": vmid, "disk": disk, "added_gb": add_gb, "response": upid}

    # --------------------------------------------------------------------------
    # Creation & Cloning
    # --------------------------------------------------------------------------
    def clone_system(
        self,
        source_vmid: int,
        new_vmid: int,
        new_name: str,
        full_clone: bool = True,
        target_storage: Optional[str] = None,
        target_node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clone an existing VM or LXC template/instance."""
        source_node, system_type = self.locate_system(source_vmid, target_node)
        payload: Dict[str, Any] = {
            "newid": new_vmid,
            "name": new_name,
            "full": 1 if full_clone else 0,
        }
        if target_storage:
            payload["storage"] = target_storage

        if system_type == "qemu":
            upid = self._api.nodes(source_node).qemu(source_vmid).clone.post(**payload)
        else:
            upid = self._api.nodes(source_node).lxc(source_vmid).clone.post(**payload)

        if isinstance(upid, str) and upid.startswith("UPID:"):
            task_res = self.wait_for_task(source_node, upid, timeout=600)
            task_res["new_vmid"] = new_vmid
            task_res["new_name"] = new_name
            return task_res

        return {"success": True, "new_vmid": new_vmid, "new_name": new_name, "response": upid}

    def create_lxc(
        self,
        vmid: int,
        hostname: str,
        ostemplate: str,
        cores: int = 2,
        memory_mb: int = 2048,
        disk_gb: int = 10,
        storage: str = "local-lvm",
        password: Optional[str] = None,
        ssh_public_key: Optional[str] = None,
        net0: str = "name=eth0,bridge=vmbr0,firewall=1,ip=dhcp",
        unprivileged: bool = True,
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Provision a new LXC container from an OS template tarball."""
        target_node = self.resolve_node(node)
        payload: Dict[str, Any] = {
            "vmid": vmid,
            "hostname": hostname,
            "ostemplate": ostemplate,
            "cores": cores,
            "memory": memory_mb,
            "rootfs": f"{storage}:{disk_gb}",
            "net0": net0,
            "unprivileged": 1 if unprivileged else 0,
            "start": 0,
        }
        if password:
            payload["password"] = password
        if ssh_public_key:
            payload["ssh-public-keys"] = ssh_public_key

        upid = self._api.nodes(target_node).lxc.post(**payload)
        if isinstance(upid, str) and upid.startswith("UPID:"):
            task_res = self.wait_for_task(target_node, upid, timeout=300)
            task_res["vmid"] = vmid
            task_res["hostname"] = hostname
            return task_res

        return {"success": True, "vmid": vmid, "hostname": hostname, "response": upid}

    def create_vm(
        self,
        vmid: int,
        name: str,
        cores: int = 2,
        memory_mb: int = 2048,
        disk_gb: int = 20,
        storage: str = "local-lvm",
        iso_image: Optional[str] = None,
        net0: str = "virtio,bridge=vmbr0,firewall=1",
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Provision a new QEMU virtual machine."""
        target_node = self.resolve_node(node)
        payload: Dict[str, Any] = {
            "vmid": vmid,
            "name": name,
            "cores": cores,
            "memory": memory_mb,
            "scsihw": "virtio-scsi-pci",
            "scsi0": f"{storage}:{disk_gb}",
            "net0": net0,
        }
        if iso_image:
            payload["cdrom"] = iso_image
            payload["boot"] = "order=scsi0;ide2"
        else:
            payload["boot"] = "order=scsi0"

        upid = self._api.nodes(target_node).qemu.post(**payload)
        if isinstance(upid, str) and upid.startswith("UPID:"):
            task_res = self.wait_for_task(target_node, upid, timeout=300)
            task_res["vmid"] = vmid
            task_res["name"] = name
            return task_res

        return {"success": True, "vmid": vmid, "name": name, "response": upid}

    # --------------------------------------------------------------------------
    # System Deletion / Destruction (with Safety Rails, Self-Protection & Confirmation)
    # --------------------------------------------------------------------------
    def destroy_system(
        self,
        vmid: int,
        confirm_vmid: int,
        confirmation_phrase: str = "",
        purge: bool = True,
        node: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Safely destroy and delete a VM or LXC container.
        GUARDRAILS:
          1. Self-Protection Check: Rejects deletion if vmid hosts this server.
          2. Blacklist Check: Rejects deletion if vmid is in PVE_PROTECTED_VMIDS.
          3. Confirmation Gate: Requires confirm_vmid == vmid AND confirmation_phrase == 'CONFIRM_DELETE_<vmid>'.
          4. Graceful Stop: Automatically halts the instance prior to purging.
        """
        # Safety Check 1: Self-Protection Block
        if self.config.is_self(vmid):
            raise PermissionError(
                f"Self-Protection Block: Cannot destroy VMID {vmid} because it is the host container running this MCP server."
            )

        # Safety Check 2: Protected Blacklist check
        if self.config.is_protected(vmid):
            raise PermissionError(
                f"Destruction blocked: VMID {vmid} is in the protected systems blacklist "
                f"({self.config.protected_vmids}). Modify PVE_PROTECTED_VMIDS to allow deletion."
            )

        # Safety Check 3: Mandatory Two-Step Confirmation Gate
        required_phrase = f"CONFIRM_DELETE_{vmid}"
        if confirm_vmid != vmid or confirmation_phrase != required_phrase:
            target_node, system_type = self.locate_system(vmid, node)
            return {
                "status": "confirmation_required",
                "action": "destroy_system",
                "vmid": vmid,
                "node": target_node,
                "type": system_type,
                "message": (
                    f"DESTRUCTION BLOCKED: Deletion of {system_type.upper()} {vmid} requires explicit user confirmation. "
                    f"To proceed, please ask the user for confirmation and re-invoke with "
                    f"confirm_vmid={vmid} and confirmation_phrase='{required_phrase}'."
                ),
                "required_params": {
                    "confirm_vmid": vmid,
                    "confirmation_phrase": required_phrase,
                }
            }

        target_node, system_type = self.locate_system(vmid, node)

        # Stop system first if currently running
        try:
            self.manage_lifecycle(vmid, "stop", node=target_node)
            time.sleep(2)
        except Exception:
            pass

        payload: Dict[str, Any] = {"purge": 1 if purge else 0}

        if system_type == "qemu":
            upid = self._api.nodes(target_node).qemu(vmid).delete(**payload)
        else:
            upid = self._api.nodes(target_node).lxc(vmid).delete(**payload)

        if isinstance(upid, str) and upid.startswith("UPID:"):
            task_res = self.wait_for_task(target_node, upid, timeout=180)
            task_res["destroyed_vmid"] = vmid
            task_res["type"] = system_type
            return task_res

        return {"success": True, "destroyed_vmid": vmid, "type": system_type, "response": upid}
