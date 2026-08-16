from types import SimpleNamespace

import pytest

from reaper_mcp import connection


@pytest.fixture(autouse=True)
def reset_connection_state():
    connection._connected = False
    yield
    connection._connected = False


def test_connect_reloads_api_and_requires_enum_projects(monkeypatch):
    api = SimpleNamespace()
    reconnect_calls = []

    def reconnect():
        reconnect_calls.append(True)
        api.EnumProjects = lambda *_: ["project"]

    fake_reapy = SimpleNamespace(reascript_api=api, reconnect=reconnect)
    monkeypatch.setattr(connection, "reapy", fake_reapy)

    connection.ensure_connected()
    connection.ensure_connected()

    assert reconnect_calls == [True]
    assert connection._connected is True


def test_warning_only_connection_failure_is_not_cached(monkeypatch):
    fake_reapy = SimpleNamespace(reascript_api=SimpleNamespace(), reconnect=lambda: None)
    monkeypatch.setattr(connection, "reapy", fake_reapy)

    with pytest.raises(RuntimeError, match="did not expose EnumProjects"):
        connection.ensure_connected()

    assert connection._connected is False


def test_project_lookup_reconnects_once_after_reaper_restart(monkeypatch):
    api = SimpleNamespace(EnumProjects=lambda *_: ["project"])
    project_calls = []
    reconnect_calls = []

    def project():
        project_calls.append(True)
        if len(project_calls) == 1:
            raise ConnectionError("stale distant API session")
        return "current project"

    def reconnect():
        reconnect_calls.append(True)

    fake_reapy = SimpleNamespace(
        Project=project,
        reascript_api=api,
        reconnect=reconnect,
    )
    monkeypatch.setattr(connection, "reapy", fake_reapy)
    connection._connected = True

    assert connection.get_project() == "current project"
    assert len(project_calls) == 2
    assert reconnect_calls == [True]
