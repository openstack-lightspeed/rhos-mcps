from typing import Any, Callable
from functools import wraps
import logging
import traceback


logger = logging.getLogger(__name__)


def tool_logger(func: Callable[..., Any]) -> Callable[..., Any]:
    """Logger for MCP tools."""
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.debug(f"Running {func.__name__} with args: {args} and kwargs: {kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"Result: {result}")
        except Exception as exc:
            # Show full traceback
            logger.error(f"Error running {func.__name__}: {exc}")
            logger.error(traceback.format_exc())
            raise 
        return result
    return wrapper