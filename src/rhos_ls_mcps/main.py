"""RHOSO MCP tools.

Available tools:
- openstack CLI tool
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
import os
import sys
import yaml

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from pydantic_settings import BaseSettings
import uvicorn

from rhos_ls_mcps import osc


logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context with typed dependencies.

    This is received by all the tools that have the `ctx: Context` parameter.
    Instance is accessible through `ctx.request_context.lifespan_context`.
    """
    osc: osc.LifecycleConfig


class Settings(BaseSettings):
    ip: str = Field(default="0.0.0.0", description="IP address to bind to")
    port: int = Field(default=8080, description="Port to bind to")
    debug: bool = Field(default=False, description="Enable debug logging")
    workers: int = Field(default=10, description="Number of workers to use")
    log_format: str = Field(default="%(asctime)s.%(msecs)03d %(process)d \033[32m%(levelname)s:\033[0m %(name)s %(message)s", description="Log format")
    openstack: osc.Settings = Field(default=osc.Settings(), description="OpenStack settings")


def load_config():
    """Load the configuration from the file."""
    config_file = os.environ.get("RHOS_MCPS_CONFIG") or "config.yaml"
    if not os.path.exists(config_file):
        logger.warning("Config file not found, using default values")
        config = {}
    else:
        try:
            with open("config.yaml", "r") as f:
                config = yaml.safe_load(f.read())
        except FileNotFoundError as error:
            message = "Error: yml config file not found."
            logger.exception(message)
            raise FileNotFoundError(error, message) from error

    settings = Settings(**config)
    return settings


def initialize(config: Settings) -> FastMCP:
    """Initialize logging and the MCP server with the tools."""
    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        """Manage application lifecycle with type-safe context."""
        osc_config = osc.LifecycleConfig(config)
        app_context: AppContext= AppContext(osc=osc_config)
        logger.debug("Application lifespan initialized")
        yield app_context

    log_level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format=config.log_format,
        stream=sys.stderr,
        force=True,
    )
    logger.setLevel(log_level)
    logger.info("Initializing RHOSO MCP server")

    # Use stateless_http=True to support multiple workers, otherwise a
    # session can go to a different worker and it will fail.
    mcp = FastMCP("rhoso-tools", lifespan=app_lifespan, stateless_http=True)

    osc.LifecycleConfig.add_tools(mcp)
    return mcp


def create_app():
    settings = load_config()
    mcp = initialize(settings)
    mcp_app = mcp.streamable_http_app()
    return mcp_app


def main():
    settings = load_config()

    # Configure uvicorn logging
    uvicorn_log_level = "debug" if settings.debug else "info"
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = settings.log_format
    log_config["formatters"]["default"]["fmt"] = settings.log_format

    # Pass string instead of an instance to support multiple workers.
    # Pass the factory=True argument to use a function (create_app) instead of a variable.
    uvicorn.run(
        "rhos_ls_mcps.main:create_app",
        host=settings.ip,
        port=settings.port,
        log_level=uvicorn_log_level,
        workers=settings.workers,
        timeout_keep_alive=5,
        access_log=False,
        factory=True,
        log_config=log_config,
    )


if __name__ == "__main__":
    main()
