"""RHOSO MCP tools.

Available tools:
- openstack CLI tool
"""

import argparse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from ipaddress import ip_address
import logging
import sys

from mcp.server.fastmcp import FastMCP

from rhos_ls_mcps import osc


logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context with typed dependencies.

    This is received by all the tools that have the `ctx: Context` parameter. 
    Instance is accessible through `ctx.request_context.lifespan_context`.
    """
    osc: osc.LifecycleConfig


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Here we define the common arguments for the MCP server and also call the
    modules with tools to add their arguments to the parser.
    """
    # Define the parser
    parser = argparse.ArgumentParser(
        description="RHOSO MCP server tools"
    )

    # Add common arguments
    parser.add_argument(
        "--ip",
        required=False,
        type=ip_address,
        default="0.0.0.0",
        help="IP address to bind to",
    )
    parser.add_argument(
        "--port",
        required=False,
        type=int,
        default=8902,
        help="Port to bind to",
    )
    parser.add_argument(
        "--debug",
        required=False,
        default=False,
        action="store_true",
        help="Enable debug logging",
    )

    # Add modules' arguments to the parser
    osc.LifecycleConfig.add_arg_options(parser)

    # Do the parsing and return the args
    args = parser.parse_args()
    return args


def initialize(args: argparse.Namespace) -> FastMCP:
    """Initialize logging and the MCP server with the tools."""
    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        """Manage application lifecycle with type-safe context."""
        osc_config = osc.LifecycleConfig(args)
        app_context: AppContext= AppContext(osc=osc_config)
        logger.debug("Application lifespan initialized")
        yield app_context

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="\033[32m%(levelname)s:\033[0m %(message)s",
        stream=sys.stderr,
        force=True,
    )
    logger.setLevel(log_level)
    logger.info("Initializing RHOSO MCP server")

    mcp = FastMCP("rhoso-tools", lifespan=app_lifespan)
    mcp.settings.host = str(args.ip)
    mcp.settings.port = int(args.port)

    osc.LifecycleConfig.add_tools(mcp)
    return mcp


def main():
    args: argparse.Namespace = parse_args()
    mcp = initialize(args)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
