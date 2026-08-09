from dataclasses import dataclass

import pytest

from reaper_mcp import track_tools
from reaper_mcp.track_state import db_to_linear, linear_to_db


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


@dataclass
class FakeTake:
    name: str


class FakeItem:
    def __init__(self, name: str, position: float = 0.0, length: float = 1.0):
        self.position = position
        self.length = length
        self.n_takes = 1 if name else 0
        self.active_take = FakeTake(name)


@dataclass
class FakeFx:
    name: str
    is_enabled: bool = True


class FakeTrack:
    def __init__(self, name: str, items=None, fxs=None):
        self.name = name
        self.items = list(items or [])
        self.fxs = list(fxs or [])
        self.values = {
            "D_VOL": db_to_linear(-6.0),
            "D_PAN": 0.25,
            "B_MUTE": 1.0,
            "I_SOLO": 0.0,
        }

    @property
    def n_items(self):
        return len(self.items)

    @property
    def n_fxs(self):
        return len(self.fxs)

    def get_info_value(self, name):
        return self.values[name]

    def set_info_value(self, name, value):
        self.values[name] = value


class FakeProject:
    def __init__(self, tracks):
        self.tracks = tracks

    @property
    def n_tracks(self):
        return len(self.tracks)


@pytest.fixture
def registered_tools(monkeypatch):
    track = FakeTrack(
        "Mosynth",
        items=[FakeItem("Chord", position=1.5, length=2.0), FakeItem("")],
        fxs=[FakeFx("VST3i: Mosynth")],
    )
    monkeypatch.setattr(track_tools, "get_project", lambda: FakeProject([track]))
    registry = ToolRegistry()
    track_tools.register_tools(registry)
    return registry.tools, track


def test_list_tracks_uses_supported_reapy_track_info(registered_tools):
    tools, _ = registered_tools

    result = tools["list_tracks"]()

    assert result["success"] is True
    assert result["tracks"] == [
        {
            "index": 0,
            "name": "Mosynth",
            "volume_db": pytest.approx(-6.0),
            "pan": 0.25,
            "muted": True,
            "soloed": False,
            "fx_count": 1,
            "item_count": 2,
        }
    ]


def test_get_track_info_uses_active_take_name(registered_tools):
    tools, _ = registered_tools

    result = tools["get_track_info"](0)

    assert result["success"] is True
    assert result["items"] == [
        {"index": 0, "position": 1.5, "length": 2.0, "name": "Chord"},
        {"index": 1, "position": 0.0, "length": 1.0, "name": ""},
    ]


def test_track_setters_use_reaper_info_values(registered_tools):
    tools, track = registered_tools

    assert tools["set_track_volume"](0, -12.0)["volume_db"] == pytest.approx(-12.0)
    assert tools["set_track_pan"](0, -0.5)["pan"] == -0.5
    assert tools["set_track_mute"](0, False)["muted"] is False
    assert tools["set_track_solo"](0, True)["soloed"] is True
    assert linear_to_db(track.values["D_VOL"]) == pytest.approx(-12.0)
    assert track.values["D_PAN"] == -0.5
    assert track.values["B_MUTE"] == 0.0
    assert track.values["I_SOLO"] == 1.0


def test_invalid_pan_and_non_finite_volume_are_rejected(registered_tools):
    tools, _ = registered_tools

    assert tools["set_track_pan"](0, 1.5) == {
        "success": False,
        "error": "pan must be finite and between -1.0 and 1.0",
    }
    assert tools["set_track_volume"](0, float("nan")) == {
        "success": False,
        "error": "volume_db must be finite",
    }
