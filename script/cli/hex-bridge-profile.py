"""Manage HEX-Bridge profiles; compatibility CLI entry point."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hexbridge_profile import *
from mcp_transport import MCPTransport

if __name__ == "__main__":
    try:
        main(transport_factory=MCPTransport)
    except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error) as exc:
        sys.exit(str(exc))
