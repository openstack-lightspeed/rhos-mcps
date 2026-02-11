import asyncio
from concurrent.futures import ProcessPoolExecutor
from functools import wraps
import multiprocessing
from typing import Any, Callable


class ProcessPool:
    def __init__(self, pool_size: int):
        self.pool_size = pool_size
        self.pool = ProcessPoolExecutor(max_workers=pool_size)
        self.loop = asyncio.get_running_loop()

    async def run_function(self, func: Callable[..., Any], *args: Any) -> Any:
        result = await self.loop.run_in_executor(
            self.pool, func, *args)
        return result


EXECUTOR: ProcessPool | None = None


def init_process_pool(pool_size: int) -> None:
    global EXECUTOR
    EXECUTOR = ProcessPool(pool_size)