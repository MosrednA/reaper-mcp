"""One ordered REAPER command stream per server; reapy's socket is not multiplexed."""
from collections.abc import Callable
from functools import wraps
from threading import RLock
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")
_lock = RLock()


def serialized(function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def call(*args: P.args, **kwargs: P.kwargs) -> T:
        with _lock:
            return function(*args, **kwargs)
    return call


class SerializedTools:
    def __init__(self, server):
        self.server = server

    def tool(self):
        def register(function):
            return self.server.tool()(serialized(function))
        return register
