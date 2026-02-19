"""RHOSO MCP tools.

Available tools:
- openstack CLI tool
"""

import contextlib
import logging

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
import uvicorn

from rhos_ls_mcps import auth as auth_module
from rhos_ls_mcps import oc
from rhos_ls_mcps import osc
from rhos_ls_mcps import settings
from rhos_ls_mcps import logging as mcp_logging
from rhos_ls_mcps import utils


logger = logging.getLogger(__name__)


def initialize(config: settings.Settings) -> tuple[FastMCP, FastMCP]:
    """Initialize logging and the MCP server with the tools."""
    mcp_logging.init_logging(config)
    logger.info("Initializing RHOSO MCP server")
    utils.init_process_pool(config.processes_pool_size)

    security_cfg: auth_module.SecurityConfig = auth_module.get_auth_settings(config)

    # Use stateless_http=True to support multiple workers, otherwise a
    # session can go to a different worker and it will fail.
    mcp_osp = FastMCP(
        "rhoso-tools",
        stateless_http=True,
        auth_server_provider=security_cfg.auth_server_provider,
        auth=security_cfg.auth,
        token_verifier=security_cfg.token_verifier,
        transport_security=security_cfg.transport_security,
    )
    mcp_ocp = FastMCP(
        "ocp-tools",
        stateless_http=True,
        auth_server_provider=security_cfg.auth_server_provider,
        auth=security_cfg.auth,
        token_verifier=security_cfg.token_verifier,
        transport_security=security_cfg.transport_security,
    )
    mcp_osp.settings.streamable_http_path = "/"
    mcp_ocp.settings.streamable_http_path = "/"

    osc.initialize(mcp_osp, mcp_ocp)
    oc.initialize(mcp_osp, mcp_ocp)

    return mcp_osp, mcp_ocp


def create_app():
    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(mcp_osp.session_manager.run())
            await stack.enter_async_context(mcp_ocp.session_manager.run())
            yield

    config = settings.load_config()
    mcp_osp, mcp_ocp = initialize(config)

    starlette_app = Starlette(routes=[
        Mount("/openstack", app=mcp_osp.streamable_http_app()),
        Mount("/openshift", app=mcp_ocp.streamable_http_app()),
    ], lifespan=lifespan)

    # Wrap ASGI application with CORS middleware to allow browser-based clients to work
    app = CORSMiddleware(
        starlette_app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )

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