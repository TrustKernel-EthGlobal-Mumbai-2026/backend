"""Optional official MCP SDK wrapper; stdout belongs exclusively to stdio MCP."""
import sys
from importlib.metadata import PackageNotFoundError, version

from .sdk import Client, OPERATIONS

MCP_REQUIREMENT = "mcp>=1.28,<2"


def build_server(client: Client | None = None):
    try:
        installed = version("mcp")
    except PackageNotFoundError:
        raise RuntimeError("Optional MCP dependency missing; install " + MCP_REQUIREMENT) from None
    parts = installed.split(".")
    if len(parts) < 2 or parts[0] != "1" or not parts[1].isdigit() or int(parts[1]) < 28:
        raise RuntimeError("Unsupported MCP dependency version; install " + MCP_REQUIREMENT)
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise RuntimeError("Optional MCP dependency missing; install " + MCP_REQUIREMENT) from None
    server = FastMCP("TrustKernel continuous verification")
    sdk = client or Client()

    def register(operation):
        def invoke(request: dict) -> dict:
            return sdk.call(operation, request)
        invoke.__name__ = operation
        invoke.__doc__ = (
            f"{operation}: requires trusted {OPERATIONS[operation]} permission and run scope. "
            "Request is inline JSON, never a server path. Results are scoped; ok is not clearance."
        )
        server.tool(name=operation)(invoke)

    for operation in OPERATIONS:
        register(operation)
    return server


def main() -> int:
    try:
        server = build_server()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 3
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
