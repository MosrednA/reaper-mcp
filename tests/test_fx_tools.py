from dataclasses import dataclass

import pytest

from reaper_mcp import fx_tools


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
    normalized: float
    formatted: str


@dataclass
class FakeFx:
    index: int
    name: str
    n_params: int = 3
    preset: str = "Init"

    def __post_init__(self):
        self.params = [
            FakeParam("Cutoff", 0.25, "440 Hz"),
            FakeParam("Resonance", 0.1, "0.1"),
            FakeParam("Drive", 0.0, "0.0"),
        ]


class FakeTrack:
    def __init__(self):
        self.id = "track-id"
        self.fxs = []

    def add_fx(self, name):
        fx = FakeFx(len(self.fxs), name)
        self.fxs.append(fx)
        return fx


@pytest.fixture
def registered_tools(monkeypatch):
    track = FakeTrack()
    project = type("Project", (), {"tracks": [track]})()
    monkeypatch.setattr(fx_tools, "get_project", lambda: project)
    calls = []

    def set_parameter(track_id, fx_index, param_index, value):
        calls.append((track_id, fx_index, param_index, value))
        track.fxs[fx_index].params[param_index].normalized = value

    monkeypatch.setattr(fx_tools.RPR, "TrackFX_SetParamNormalized", set_parameter)
    registry = ToolRegistry()
    fx_tools.register_tools(registry)
    return registry.tools, track, calls


def test_add_fx_uses_fx_object_returned_by_reapy(registered_tools):
    tools, track, _ = registered_tools

    result = tools["add_fx"](0, "VST3i: Mosynth")

    assert result == {
        "success": True,
        "fx_index": 0,
        "name": "VST3i: Mosynth",
        "n_params": 3,
        "track_index": 0,
    }
    assert len(track.fxs) == 1


def test_load_fx_preset_uses_reapy_preset_property(registered_tools):
    tools, track, _ = registered_tools
    track.add_fx("VST3i: Mosynth")

    result = tools["load_fx_preset"](0, 0, "PWM Pad")

    assert result["success"] is True
    assert result["preset"] == "PWM Pad"
    assert track.fxs[0].preset == "PWM Pad"


def test_fx_parameters_use_reapy_normalized_and_formatted_properties(registered_tools):
    tools, track, calls = registered_tools
    track.add_fx("VST3i: Mosynth")

    listed = tools["get_fx_parameters"](0, 0)
    updated = tools["set_fx_parameter"](0, 0, 1, 0.75)

    assert listed["parameters"][0] == {
        "index": 0,
        "name": "Cutoff",
        "normalized_value": 0.25,
        "formatted_value": "440 Hz",
    }
    assert updated["success"] is True
    assert updated["param_name"] == "Resonance"
    assert calls == [("track-id", 0, 1, 0.75)]
    assert track.fxs[0].params[1].normalized == 0.75
