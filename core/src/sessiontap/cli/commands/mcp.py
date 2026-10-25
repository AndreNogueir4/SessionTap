import argparse
from sessiontap.cli.base import Command, CommandError


class Mcp(Command):
    name = "mcp"
    help = "run the MCP server (stdio) for AI agents"

    def run(self, args: argparse.Namespace) -> None:
        try:
            from sessiontap.mcp_server import run
        except ImportError as e:
            raise CommandError(
                "The MCP server needs the mcp extra. In the SessionTap folder run: "
                'uv tool install --reinstall "./core[server,mcp]"'
            ) from e
        run()
