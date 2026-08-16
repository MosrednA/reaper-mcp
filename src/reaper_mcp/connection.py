import logging
import reapy

logger = logging.getLogger("reaper_mcp.connection")

_connected = False


def _has_required_api() -> bool:
    return callable(getattr(reapy.reascript_api, "EnumProjects", None))


def _connection_error(error: Exception | str) -> RuntimeError:
    return RuntimeError(
        f"Cannot connect to REAPER: {error}. "
        "Make sure REAPER is running and the distant API is enabled. "
        "To enable it: run the setup script (scripts/enable_reapy.py) or "
        "in REAPER go to Actions > Run ReaScript, then run: "
        "import reapy; reapy.config.enable_dist_api()"
    )


def ensure_connected() -> None:
    global _connected
    if _connected and _has_required_api():
        return

    _connected = False
    try:
        # reapy.connect() may only emit DisabledDistAPIWarning after a failed
        # initial import, leaving reascript_api without functions while still
        # returning normally. reconnect() reloads that module; the capability
        # check below makes a warning-only failure observable to callers.
        reapy.reconnect()
    except Exception as e:
        raise _connection_error(e) from e

    if not _has_required_api():
        raise _connection_error("the distant API did not expose EnumProjects")

    _connected = True
    logger.info("Connected to REAPER")


def get_project() -> reapy.Project:
    global _connected
    ensure_connected()
    try:
        return reapy.Project()
    except Exception as first_error:
        # A running MCP process can outlive REAPER. Refresh the distant API and
        # retry this read-only lookup once instead of pinning a stale session.
        _connected = False
        try:
            ensure_connected()
            return reapy.Project()
        except Exception as retry_error:
            raise _connection_error(retry_error) from first_error
