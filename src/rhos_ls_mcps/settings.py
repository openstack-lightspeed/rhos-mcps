import logging
import os
import yaml
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


logger = logging.getLogger(__name__)

class OpenStackSettings(BaseSettings):
    allow_write: bool = Field(default=False, description="Allow write operations (default: false)")
    ca_cert: Optional[str] = Field(default=None, description="CA certificate bundle file (Env: OS_CACERT)")
    insecure: bool = Field(default=False, description="Allow insecure SSL connections (Env: OS_INSECURE)")


class TransportSecuritySettings(BaseSettings):
    enable_dns_rebinding_protection: bool = Field(default=False, description="Enable DNS rebinding protection")
    allowed_hosts: list[str] = Field(default=["*:*"], description="Allowed hosts")
    allowed_origins: list[str] = Field(default=["http://*:*"], description="Allowed origins")


class Settings(BaseSettings):
    ip: str = Field(default="0.0.0.0", description="IP address to bind to")
    port: int = Field(default=8080, description="Port to bind to")
    debug: bool = Field(default=False, description="Enable debug logging")
    workers: int = Field(default=10, description="Number of workers to use")
    log_format: str = Field(default="%(asctime)s.%(msecs)03d %(process)d \033[32m%(levelname)s:\033[0m [%(request_id)s|%(client_id)s] %(name)s %(message)s", description="Log format")
    unicorn_log_format: str = Field(default="%(asctime)s.%(msecs)03d %(process)d \033[32m%(levelname)s:\033[0m [-|-] %(name)s %(message)s", description="Unicorn log format")
    openstack: OpenStackSettings = Field(default=OpenStackSettings(), description="OpenStack settings")
    mcp_transport_security: TransportSecuritySettings = Field(default=TransportSecuritySettings(), description="Transport security settings")


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