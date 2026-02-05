"""RHOSO MCP tools.

Available tools:
- openstack CLI tool
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
import uvicorn

from rhos_ls_mcps import osc
from rhos_ls_mcps import settings
from rhos_ls_mcps import utils


logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context with typed dependencies.

    This is received by all the tools that have the `ctx: Context` parameter.
    Instance is accessible through `ctx.request_context.lifespan_context`.
    """
    osc: osc.LifecycleConfig


def initialize(config: settings.Settings) -> FastMCP:
    """Initialize logging and the MCP server with the tools."""
    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        """Manage application lifecycle with type-safe context."""
        osc_config = osc.LifecycleConfig(config)
        app_context: AppContext= AppContext(osc=osc_config)
        logger.debug("Application lifespan initialized")
        yield app_context

    utils.init_logging(config)
    logger.info("Initializing RHOSO MCP server")

    # Use stateless_http=True to support multiple workers, otherwise a
    # session can go to a different worker and it will fail.
    mcp = FastMCP(
        "rhoso-tools",
        lifespan=app_lifespan,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=config.mcp_transport_security.enable_dns_rebinding_protection,
            allowed_hosts=config.mcp_transport_security.allowed_hosts,
            allowed_origins=config.mcp_transport_security.allowed_origins,
        ),
    )

    osc.LifecycleConfig.add_tools(mcp)
    return mcp


def create_app():
    config = settings.load_config()
    mcp = initialize(config)
    mcp_app = mcp.streamable_http_app()

    # Wrap ASGI application with CORS middleware to allow browser-based clients to work
    app = CORSMiddleware(
        mcp_app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )

    # return mcp_app
    return app


def main():
    config = settings.load_config()

    # Configure uvicorn logging
    uvicorn_log_level = "debug" if config.debug else "info"
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = config.unicorn_log_format
    log_config["formatters"]["default"]["fmt"] = config.unicorn_log_format

    # Pass string instead of an instance to support multiple workers.
    # Pass the factory=True argument to use a function (create_app) instead of a variable.
    uvicorn.run(
        "rhos_ls_mcps.main:create_app",
        host=config.ip,
        port=config.port,
        log_level=uvicorn_log_level,
        workers=config.workers,
        timeout_keep_alive=5,
        access_log=False,
        factory=True,
        log_config=log_config,
    )


if __name__ == "__main__":
    main()