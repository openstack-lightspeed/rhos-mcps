"""RHOSO MCP tools.

Available tools:
- openstack CLI tool
"""

import logging

from mcp.server.fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
import uvicorn

from rhos_ls_mcps import auth as auth_module
from rhos_ls_mcps import osc
from rhos_ls_mcps import settings
from rhos_ls_mcps import logging as mcp_logging
from rhos_ls_mcps import utils


logger = logging.getLogger(__name__)


def initialize(config: settings.Settings) -> FastMCP:
    """Initialize logging and the MCP server with the tools."""
    mcp_logging.init_logging(config)
    logger.info("Initializing RHOSO MCP server")
    utils.init_process_pool(config.processes_pool_size)

    security_cfg: auth_module.SecurityConfig = auth_module.get_auth_settings(config)

    # Use stateless_http=True to support multiple workers, otherwise a
    # session can go to a different worker and it will fail.
    mcp = FastMCP(
        "rhoso-tools",
        stateless_http=True,
        auth_server_provider=security_cfg.auth_server_provider,
        auth=security_cfg.auth,
        token_verifier=security_cfg.token_verifier,
        transport_security=security_cfg.transport_security,
    )

    osc.initialize(mcp)

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