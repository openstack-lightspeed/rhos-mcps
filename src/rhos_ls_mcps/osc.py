"""
# openstack CLI MCP tool

## Features:

- Run `openstack` commands as if they were run in a terminal
- Uses the OpenStackClient (OSC) code as a libray to simulate running commands from the command line
- Supported authentication mechanisms:
  * Config files on standard locations `clouds.yaml` and `secure.yaml`)
  * `OS_TOKEN` and `OS_URL` passed as MCP request headers
- SSL:
  * Support configuring insecure mode (`--osc-insecure`)
  * Explicit local certificates (`--osc-ca-cert`)
- Uses a whitelist mechanism to accept only those commands when running in read only mode
- Allows all commands when running in read/write mode (`--osc-allow-write`)
- Client defaults to the latest microversion for each service, but can be overridden by the caller by passing the appropriate `--os-XXXX-api-version` parameter

## DEV LINKS:
- https://github.com/openstack/python-openstackclient/blob/master/openstackclient/shell.py
- https://github.com/openstack/osc-lib/blob/master/osc_lib/shell.py
"""

from dataclasses import dataclass
from importlib.metadata import entry_points, EntryPoint
import io
import json
import logging
import os
import shlex
from typing import Any, Callable, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
import openstackclient.shell as osc_shell
from osc_lib import exceptions as osc_exceptions

from rhos_ls_mcps import mcp_base
from rhos_ls_mcps import settings
from rhos_ls_mcps.utils import tool_logger


ACCEPT_COMMANDS: set[str] = {
        # These are just verbs
        "get", "show", "list", "history", "alarm-history show", "alarm-history search",
        "capabilities list", "alarm show", "alarm quota show", "alarm state get",
        "search", "benchmark metric show", "alarming capabilities list", "simulate",
        "info", "collect", "benchmark measures show", "validate", "ping", "top",
        "stats", "alarm list", "contains", "homedoc", "query", "measures aggregation",
        "tail", "versions", "count",

        # These are full names
        "stack_resource_metadata", "database_configuration_default", "metric_aggregates",
        "optimize_strategy_state", "rca_status", "volume_summary", "stack_hook_poll",
        "database_configuration_instances",  "alarm metrics", "stack_check",
        "cluster_check", "baremetal_introspection_status", "rca_healthcheck",
        "appcontainer_logs", "appcontainer_quota_default", "metric_status",
        "metric_server_version", "messaging_health", "database_cluster_modules",
        "class-schema",
}

logger = logging.getLogger(__name__)


##########
# METHODS AND CLASSES CALLED FROM main.py

class LifecycleConfig(mcp_base.LifecycleConfigAbstract):
    """MCP server lifecycle configuration for the OpenStack MCP tool.

    Used in main.py:AppContext.osc and received by all the tools that have the
    `ctx: Context` parameter. Instance is accessible through
    `ctx.request_context.lifespan_context.osc`.
    """
    allow_write: bool
    allowed_commands: tuple[str]
    params: list[str]

    def __init__(self, config: settings.Settings) -> None:
        """Initialize the OpenStack MCP tool.

        This sets the global variables that tool calls will need.

        Called from main.py:initialize()
        """
        osc_config = config.openstack
        osc_params = ["--os-cacert", osc_config.ca_cert] if osc_config.ca_cert else []
        if osc_config.insecure:
            osc_params.append("--insecure")

        self.allow_write = osc_config.allow_write
        self.allowed_commands = osp_list_commands(ACCEPT_COMMANDS)[0]
        self.params = osc_params

    @staticmethod
    def add_tools(mcp: FastMCP) -> None:
        """Add the module's MCP tools to the server."""
        mcp.add_tool(openstack_cli_mcp_tool,
                    name="openstack-cli",
                    title="OpenStack Client MCP Tool")


##########
# MCP TOOLS AND SUPPORTING METHODS

def _clean_response(response: str) -> str:
    """Clear the response to remove 0x00 characters at the start."""
    return response.lstrip("\x00")

@tool_logger
def openstack_cli_mcp_tool(command_str: str, ctx: Context) -> str:
    """Run an OpenStackClient (OSC) CLI command

    Runs the `openstack` command as if it were run in a terminal.
    No need to provide credentials, they are already present.

    The `openstack` command replaces individual commands for example:
    - `cinder volume-list` is now `openstack volume list`
    - `glance image-list` is now `openstack image list`
    - `nova list` is now `openstack server list`

    DON'T EVER USE commands such as cinder, nova, glance. Use `openstack` instead.

    A complete list of commands is available using the help commands:
    - Global options and supported commands: `openstack --help` or `--help`
    - Options for a specific command:
      * `openstack <command> --help`
      * `openstack help <command>`

    Microversions default to latest version, can use older version with
    appropriate `--os-XXXX-api-version`parameter (eg:
    `--os-identity-api-version 3.26`)

    For specific format of the stdout result use
    `--format {table,csv,json,value,yaml}` (default: is table)

    Empty lists output depends on the format:
    - CSV: always have a headers line, when there are no elements that's the only line.
    - JSON: empty array []
    - Table: nothing

    Args:
       command_str: String with the openstack command to run. May start with "openstack"
                    or not, but it will *NEVER* be cinder, nova, glance, etc.
    """
    # TODO: Actually implement our own shell so we don't reload plugins and commands every time?
    #       https://github.com/openstack/python-openstackclient/blob/master/openstackclient/shell.py
    #       Which inherits from: https://github.com/openstack/osc-lib/blob/master/osc_lib/shell.py
    stdin = None
    stdout = io.StringIO()
    stderr = io.StringIO()

    shell = MyOpenStackShell(
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        osc_config=ctx.request_context.lifespan_context.osc,
    )

    # Build the command arguments list for the openstack command
    mcp_argv = (
        ctx.request_context.lifespan_context.osc.params +
        get_osp_credentials_args(ctx)
    )
    user_argv = split_command(command_str, ctx)

    ret_value = shell.run(mcp_argv, user_argv)

    # TODO; Redact values?
    result = {
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }

    if ret_value:
        raise ToolError("openstack failed with error code {}: {}".format(ret_value, result))

    return stdout.getvalue() or stderr.getvalue()


class MyOpenStackShell(osc_shell.OpenStackShell):
    """OpenStack shell implementation without a subprocess shell.

    Necessary because the osc shell doesn't accept stdin, stdout, and stderr as arguments,
    as it assumes it's always called from a terminal.  We need to capture the command's
    stdout and stderr to return them to the MCP client.

    Also ensures that plugins and commands are loaded only once.
    """
    # Class variables shared by all instances
    original_ancestor: Callable | None = None
    versions_initialized: bool = False
    # TODO: Figure out why we need to reload everytime otherwise the commands dissapear and we fail
    #loaded_plugins: bool = False
    #loaded_commands: bool = False

    def __init__(
        self,
        description: str | None = None,
        version: str | None = None,
        stdin: osc_shell.shell.ty.TextIO | None = None,
        stdout: osc_shell.shell.ty.TextIO | None = None,
        stderr: osc_shell.shell.ty.TextIO | None = None,
        interactive_app_factory: type['interactive.InteractiveApp'] | None = None,
        deferred_help: Optional[bool] = None,
        osc_config: LifecycleConfig | None = None,
    ) -> None:
        description = description or osc_shell.__doc__.strip()
        version = version or osc_shell.openstackclient.__version__
        # Our custom command manager blocks commands that are not allowed
        command_manager = MyCommandManager('openstack.cli',
                                           stderr=stderr,
                                           osc_config=osc_config)
        deferred_help = True if deferred_help is None else deferred_help

        ##########
        # TEMPORARY WORKAROUND FOR osc-lib BUG
        #
        # TODO: Submit a fix for osc-lib so it passes stdin and stdout to cliff's app init method.
        #       It's currently not passing stdin and stdout received arguments:
        #       https://github.com/openstack/osc-lib/blob/feba9b91ae663288d5075e4e554377a39eb732d2/osc_lib/shell.py#L121
        #       Until then we monkey patch the great-grandparent class here:
        #       MRO: [MyOpenStackShell, osc_shell.OpenStackShell, osc_lib.shell.OpenStackShell, cliff.app.App, ...]
        if MyOpenStackShell.original_ancestor is None:
            great_grandparent = self.__class__.__mro__[3]
            MyOpenStackShell.original_ancestor = great_grandparent.__init__
        self.__class__.__mro__[3].__init__ = lambda self, *args, **kwargs: MyOpenStackShell.original_ancestor(
            self, stdin=stdin, stdout=stdout, stderr=stderr, interactive_app_factory=interactive_app_factory, *args, **kwargs)

        super(osc_shell.OpenStackShell, self).__init__(
           description=description,
           version=version,
           command_manager=command_manager,
           stdin=stdin,
           stdout=stdout,
           stderr=stderr,
           interactive_app_factory=interactive_app_factory,
           deferred_help=deferred_help,
        )

        self.api_version = {}

        # ?: This doesn't seem to be used
        self.verify = True

        # ignore warnings from openstacksdk since our users can't do anything
        # about them
        osc_shell.warnings.filterwarnings('ignore', module='openstack')

    # TODO: Figure out why we need to reload everytime otherwise the commands dissapear and we fail
    # def _load_plugins(self) -> None:
    #     """Only load plugins once."""
    #     if not self.loaded_plugins:
    #         super()._load_plugins()
    #         MyOpenStackShell.loaded_plugins = True

    # def _load_commands(self) -> None:
    #     """Only load commands once."""
    #     if not self.loaded_commands:
    #         super()._load_commands()
    #         MyOpenStackShell.loaded_commands = True

    # # From https://specs.openstack.org/openstack/service-types-authority/_downloads/e1997ad174a98e6705a285ae2a24dff8/service-types.yaml
    @staticmethod
    def _get_version_arg_name_from_service_type(service_type: str) -> str:
        API_NAME_MAPPING: dict[str, str] = {
            "block-storage": "volume",
            "volumev3": "volume",
            "volumev2": "volume",
            "metric-storage": "metric",
            "operator-policy": "congressclient",
            "alarm": "alarming",  # alarming is also an alias that doesn't need to be mapped
            "resource-cluster": "clustering",  # Clustering is the real service type and doesn't need to be mapped
            "cluster": "clustering",
            "application-container": "container",
            "message": "messaging",  # messaging is also an alias that doesn't need to be mapped
            "resource-optimization": "infra-optim",
            "root-cause-analysis": "rca",  # rca is also an alias that doesn't need to be mapped
            "workflow": "workflow_engine",
            "workflowv2": "workflow_engine",
        }

        api_name = API_NAME_MAPPING.get(service_type, service_type.replace("-", "_"))
        return f"os_{api_name}_api_version"

    def _clean_stds(self) -> None:
        """Clean the stdout and stderr buffers."""
        self.stdout.seek(0)
        self.stdout.truncate(0)
        self.stderr.seek(0)
        self.stderr.truncate(0)

    def _initialize_api_versions(self, mcp_argv: list[str]) -> None:
        """Initialize the api_version dictionary with the latest API version for each service.

        This makes a call to OpenStack to get the versions.

        Args:
            mcp_argv: Argumments for credentials and certificates.
        """
        if self.versions_initialized:
            return

        # Make sure we start with a clean stdout and stderr
        self._clean_stds()

        versions_varg = ["versions", "show", "--format", "json"]
        response = super().run(mcp_argv + versions_varg)
        if response:
            raise ToolError(f"Failed to get API versions ({response}):\n{self.stdout.getvalue()}\n{self.stderr.getvalue()}")
        # For some reason stdout has 0x00 characters at the start, clean it
        api_versions = json.loads(_clean_response(self.stdout.getvalue()))

        version_defaults = {}

        for version_info in api_versions:
            # We only care about the latest API version
            if version_info["Status"] == "CURRENT":
                # Some services reportt microversions, others only report the version
                arg_name = self._get_version_arg_name_from_service_type(version_info["Service Type"])
                version = version_info["Max Microversion"] or version_info["Version"]
                # Keystone is weird, it reports 3.14 but doesn't accept it :-(
                if arg_name == "os_identity_api_version":
                    version = version.split(".")[0]
                version_defaults[arg_name] = version

        # Change the default values for the api versions in the parser, that way
        # the user can override them if needed and we don't need to actually
        # pass them all on the command line.
        self.parser.set_defaults(**version_defaults)

        # Leave a clean stdout and stderr for the real user call
        self._clean_stds()
        MyOpenStackShell.versions_initialized = True

    def run(self, mcp_argv: list[str], user_argv: list[str]) -> int:
        """Run the OpenStack shell.

        Ensures that the API versions are initialized to the latest version for each service.

        Args:
            mcp_argv: Argumments for credentials and certificates.
            user_argv: Arguments for the OpenStack command.
        """
        self._initialize_api_versions(mcp_argv)
        return super().run(mcp_argv + user_argv)


def get_osp_credentials_args(ctx: Context) -> list[str]:
    """Get arguments for OpenStack credentials.

    Priority from highest to lowest:
    - `OS_TOKEN` and `OS_URL` in request headers
    - `clouds.yaml` and `secure.yaml` in
      * current directory
      * ~/.config/openstack
      * /etc/openstack

    Returns:
       list[str]: The arguments for the OpenStack credentials.
    Raises:
      - ToolError: If no credentials are found
    """

    # Check if we have connection information on the request headers
    headers = ctx.request_context.request.headers
    logger.debug(f"Headers: {headers}")

    token_header = headers.get('OS_TOKEN')
    url_header = headers.get('OS_URL')
    if token_header and url_header:
        logger.debug(f"Using token and URL from request headers for credentials: {url_header}")
        return ["--os-token", token_header, "--os-url", url_header]

    # Check that we actually have the credential files in a known location
    for config_dir in ["./", os.path.expanduser("~/.config/openstack"), "/etc/openstack"]:
        if os.path.exists(os.path.join(config_dir, "clouds.yaml")) and os.path.exists(os.path.join(config_dir, "secure.yaml")):
            logger.debug(f"Using clouds.yaml and secure.yaml from {config_dir} for credentials")
            return []

    raise ToolError("Missing OpenStack credentials")


def split_command(command_str: str, ctx: Context) -> list[str]:
    """Basic command validation and return it as a list.

    Args:
       command_str: String with the openstack command to run.
                    May start with "openstack" or not, but cannot just be "openstack"
                    to prevent interactive mode.
       ctx: The MCP request context
    Returns:
       list[str]: The argv list without the initial "openstack".
    """
    command_str = command_str.strip()

    if not command_str:
        raise ToolError("No command provided")

    if command_str == "openstack":
        raise ToolError("openstack interactive mode is not available")

    # Use shlex to do a proper split (honoring quotes and escapes)
    argv = shlex.split(command_str)
    if argv[0] == "openstack":
        argv = argv[1:]
    return argv


def osp_list_commands(verbs: set[str]) -> tuple[list[str], list[str]]:
    """List commands that match and don't match the given verbs"""
    # Use sets because some commands exist in multiple groups
    # eg: dataprocessing_cluster_show exists in openstack.data_processing.v1 and
    # openstack.data_processing.v2
    result_commands: set[str] = set[str]()
    result_other_commands: set[str] = set[str]()

    all_entry_points = entry_points()
    for group in all_entry_points.groups:
        if group.startswith("openstack."):
            for ep in all_entry_points.select(group=group):
                name = ep.name
                cmd = name.split("_")
                if verbs.intersection(cmd) or name in verbs:
                    result_commands.add(name + "_")
                else:
                    result_other_commands.add(name + "_")
    return list(result_commands), list(result_other_commands)


##########
# CLASSES TO CONTROL ALLOWED COMMANDS AT RUNTIME
#
# Approach is to use a custom CommandManager that replaces entry points found
# that don't match our allowed commands with a custom EntryPoint class that
# rejects the request.
#
# This way we can differentiate between blocked and wrong commands efficiently
# since we don't have to check the command on each request.

class RejectedEntryPoint(EntryPoint):
    """Entry point that rejects the request."""
    # Parent is inmutable, so we have to define our additiona slots and then
    # bypass the protections on the immutable base to set additional
    # attributes using the __setattr__ method.
    __slots__ = ('stderr',)

    def __init__(self, name, value, group, stderr: io.StringIO):
        super().__init__(name, value, group)
        # Bypass protections on the immutable base to set additional attributes
        object.__setattr__(self, 'stderr', stderr)

    def take_action(self, *args, **kwargs) -> Any:
        """Called when the entrypoint command is executed."""
        # raise ToolError("Command is rejected: {}".format(self.name))
        msg = f"Command {self.name} is currently blocked for LLM use as it could modify the deployment."
        # Manually print to stderr because for some reason the CommandError, or
        # even ToolError, doesn't show up in stderr.
        self.stderr.write(msg)
        raise osc_exceptions.CommandError(msg)

    def load(self) -> Any:
        """Load the entrypoint command replacing the action."""
        res = super().load()
        res.take_action = self.take_action
        return res


class MyCommandManager(osc_shell.commandmanager.CommandManager):
    """Custom command manager to replace entry points for commands that are not allowed."""
    def __init__(self, *args, **kwargs):
        self.osc_config: Optional[LifecycleConfig] = kwargs.pop('osc_config', None)
        self.stderr: Optional[io.StringIO] = kwargs.pop('stderr', None)
        if not self.osc_config or not self.stderr:
            raise ToolError("osc_config and stderr are required to initialize the command manager")
        super().__init__(*args, **kwargs)

    def load_commands(self, namespace: str) -> None:
        # Detect commands that were added since the last load so we only act on new ones
        previous_commands = set(self.commands)
        super().load_commands(namespace)
        new_commands = set(self.commands) - previous_commands

        # Replace entry points for commands that are not allowed with our custom
        # class that rejects the request.
        for command in new_commands:
            if not self._is_command_allowed(command.split()):
                # Using `self.commands.pop(command)` would be simpler, but wouldn't let us differentiate
                # between blocked and wrong commands
                entry_point = self.commands[command]
                self.commands[command] = RejectedEntryPoint(
                    name=entry_point.name,
                    value=entry_point.value,
                    group=entry_point.group,
                    stderr=self.stderr)

    def _is_command_allowed(self, argv: list[str]) -> bool:
        if self.osc_config.allow_write:
            return True
        user_cmd = '_'.join(argv) + "_"
        return any(user_cmd.startswith(cmd) for cmd in self.osc_config.allowed_commands)