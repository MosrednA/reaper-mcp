from dataclasses import dataclass

import pytest

from reaper_mcp import mastering_tools
from reaper_mcp.track_state import db_to_linear


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


@dataclass
class FakeParam:
    name: str
    normalized: float = 0.0


@dataclass
class FakeFx:
    index: int
    name: str
    n_params: int = 4

    def __post_init__(self):
        self.params = [FakeParam(f"Parameter {index}") for index in range(self.n_params)]


class FakeMasterTrack:
    def __init__(self):
        self.id = "master-id"
        self.fxs = []
        self.values = {"D_VOL": 1.0}

    def add_fx(self, name):
        fx = FakeFx(len(self.fxs), name)
        self.fxs.append(fx)
        return fx

    def get_info_value(self, name):
        return self.values[name]

    def set_info_value(self, name, value):
        self.values[name] = value


@pytest.fixture
def registered_tools(monkeypatch):
    master = FakeMasterTrack()
    project = type("Project", (), {"master_track": master})()
    monkeypatch.setattr(mastering_tools, "get_project", lambda: project)
    calls = []

    def set_parameter(track_id, fx_index, param_index, value):
        calls.append((track_id, fx_index, param_index, value))
        master.fxs[fx_index].params[param_index].normalized = value

    monkeypatch.setattr(mastering_tools.RPR, "TrackFX_SetParamNormalized", set_parameter)
    registry = ToolRegistry()
    mastering_tools.register_tools(registry)
    return registry.tools, master, calls


def test_master_fx_tools_use_fx_object_returned_by_reapy(registered_tools):
    tools, master, _ = registered_tools

    added = tools["add_master_fx"]("ReaEQ")
    limited = tools["apply_limiter"]()
    chained = tools["apply_mastering_chain"]("gentle")

    assert added["fx_index"] == 0
    assert limited["fx_index"] == 1
    assert [entry["fx_index"] for entry in chained["fx_chain"]] == [2, 3, 4]
    assert len(master.fxs) == 5


def test_set_master_volume_uses_reaper_linear_gain(registered_tools):
    tools, master, _ = registered_tools

    result = tools["set_master_volume"](-9.0)

    assert result["success"] is True
    assert result["volume_db"] == pytest.approx(-9.0)
    assert master.values["D_VOL"] == pytest.approx(db_to_linear(-9.0))


def test_set_master_fx_parameter_uses_reapy_normalized_property(registered_tools):
    tools, master, calls = registered_tools
    master.add_fx("ReaEQ")

    result = tools["set_master_fx_parameter"](0, 2, 0.6)

    assert result["success"] is True
    assert result["param_name"] == "Parameter 2"
    assert calls == [("master-id", 0, 2, 0.6)]
    assert master.fxs[0].params[2].normalized == 0.6
