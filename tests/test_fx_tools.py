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
class FakeFx:
    index: int
    name: str
    n_params: int = 3
    preset: str = "Init"


class FakeTrack:
    def __init__(self):
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
    registry = ToolRegistry()
    fx_tools.register_tools(registry)
    return registry.tools, track


def test_add_fx_uses_fx_object_returned_by_reapy(registered_tools):
    tools, track = registered_tools

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
    tools, track = registered_tools
    track.add_fx("VST3i: Mosynth")

    result = tools["load_fx_preset"](0, 0, "PWM Pad")

    assert result["success"] is True
    assert result["preset"] == "PWM Pad"
    assert track.fxs[0].preset == "PWM Pad"
