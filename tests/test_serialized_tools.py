import inspect
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from reaper_mcp.serialized_tools import serialized


def test_requests_do_not_interleave_and_schema_signature_is_preserved():
    entered, release, second = Event(), Event(), Event()
    @serialized
    def operation(index: int) -> int:
        if index == 0:
            entered.set()
            assert release.wait(2)
        else:
            second.set()
        return index
    assert list(inspect.signature(operation).parameters) == ["index"]
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(operation, 0)
        assert entered.wait(1)
        other = pool.submit(operation, 1)
        try:
            assert not second.wait(.05)
        finally:
            release.set()
        assert first.result() == 0
        assert other.result() == 1
