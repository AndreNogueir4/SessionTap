from sessiontap.cli.base import Command
from sessiontap.cli.commands.mcp import Mcp
from sessiontap.cli.commands.blocklist import Blocklist
from sessiontap.cli.commands.capture import Capture, Purge
from sessiontap.cli.commands.exports import Bundle, OpenApi
from sessiontap.cli.commands.transfer import Export, Import
from sessiontap.cli.commands.secrets import CookieHeader, Secret
from sessiontap.cli.commands.host import InstallHost, UninstallHost
from sessiontap.cli.commands.daemon import Open, Start, Status, Stop, Token

COMMANDS: list[type[Command]] = [
    Start,
    Stop,
    Status,
    Open,
    Token,
    InstallHost,
    UninstallHost,
    Capture,
    Purge,
    Blocklist,
    CookieHeader,
    Secret,
    Export,
    Import,
    OpenApi,
    Bundle,
    Mcp,
]
