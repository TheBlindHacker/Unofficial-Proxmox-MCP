"""
CLI entrypoint for Unofficial-Proxmox-MCP.
Supports stdio transport (for AI IDEs) and SSE/HTTP transport (for container/network deployment).
"""

from __future__ import annotations
import argparse
import sys
import os
from .config import PVEConfig
from .client import PVEClient
from .server import mcp
from . import __version__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="unofficial-proxmox-mcp",
        description="Unofficial Proxmox VE Model Context Protocol (MCP) Server"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="MCP Transport protocol to run (default: stdio, use sse for remote daemon / container)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="Host interface to bind SSE server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8000")),
        help="Port to bind SSE server to (default: 8000)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Test connection to Proxmox VE cluster and exit immediately",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


def run_check() -> int:
    """Validate credentials and test connection to Proxmox VE."""
    config = PVEConfig.load()
    print("=" * 65)
    print("Unofficial-Proxmox-MCP Connectivity Pre-Flight Check")
    print("=" * 65)
    print(f"Target Host       : https://{config.host}:{config.port}")
    print(f"Auth Mode         : {config.auth_summary()}")
    print(f"Verify SSL        : {config.verify_ssl}")
    print(f"Self Container ID : {config.self_vmid or 'None (External/Client Mode)'}")
    print(f"Protected VMIDs   : {config.protected_vmids or 'None'}")
    print("-" * 65)

    try:
        client = PVEClient(config)
        nodes = client.list_nodes()
        print(f"[OK] Connection Successful! Found {len(nodes)} cluster node(s):")
        for n in nodes:
            print(f"     * Node: {n['node']:<12} | Status: {n['status']:<8} | CPU: {n['cpu']}% | Mem: {n['mem_mb']}MB / {n['maxmem_mb']}MB")

        # Query default node storages
        try:
            storages = client.list_storage_pools()
            print(f"[OK] Found {len(storages)} storage pool(s) on node '{config.default_node}':")
            for s in storages[:4]:
                print(f"     * Pool: {s['storage']:<15} | Type: {s['type']:<10} | Free: {s['free_gb']} GB")
        except Exception:
            pass

        print("=" * 65)
        print("Ready to serve AI assistant requests via Model Context Protocol.")
        print("=" * 65)
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to connect to Proxmox cluster: {e}", file=sys.stderr)
        print("=" * 65)
        return 1


def main() -> None:
    args = parse_args()

    if args.check:
        sys.exit(run_check())

    if args.transport == "sse":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        print(f"Starting Unofficial-Proxmox-MCP SSE Server on {args.host}:{args.port}...", file=sys.stderr)
        mcp.run(transport="sse")
    else:
        # Default: stdio transport for Claude Desktop, Antigravity, Cursor, etc.
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
