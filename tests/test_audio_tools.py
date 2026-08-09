import pytest

from reaper_mcp import audio_tools


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


class FakeTake:
    def __init__(self):
        self.values = {"D_STARTOFFS": 0.25, "D_PITCH": 0.0, "D_PLAYRATE": 1.0}

    def get_info_value(self, name):
        return self.values[name]

    def set_info_value(self, name, value):
        self.values[name] = value


class FakeItem:
    def __init__(self):
        self.position = 1.0
        self.length = 4.0
        self.active_take = FakeTake()
        self.values = {"D_FADEINLEN": 0.0, "D_FADEOUTLEN": 0.0}

    def get_info_value(self, name):
        return self.values[name]

    def set_info_value(self, name, value):
        self.values[name] = value


class FakeTrack:
    def __init__(self):
        self.items = [FakeItem()]
        self.values = {"I_RECARM": 0.0}

    def get_info_value(self, name):
        return self.values[name]

    def set_info_value(self, name, value):
        self.values[name] = value


@pytest.fixture
def registered_tools(monkeypatch):
    track = FakeTrack()
    project = type("Project", (), {"tracks": [track]})()
    monkeypatch.setattr(audio_tools, "get_project", lambda: project)
    monkeypatch.setattr(audio_tools.RPR, "Main_OnCommand", lambda *_: None)
    registry = ToolRegistry()
    audio_tools.register_tools(registry)
    return registry.tools, track


def test_record_arm_and_media_edits_use_reaper_info_values(registered_tools):
    tools, track = registered_tools
    item = track.items[0]

    assert tools["start_recording"](0)["success"] is True
    edited = tools["edit_audio_item"](0, 0, start_trim=0.5, fade_in=0.1, fade_out=0.2)

    assert edited["success"] is True
    assert track.values["I_RECARM"] == 1.0
    assert item.position == 1.5
    assert item.length == 3.5
    assert item.active_take.values["D_STARTOFFS"] == pytest.approx(0.75)
    assert item.values["D_FADEINLEN"] == 0.1
    assert item.values["D_FADEOUTLEN"] == 0.2


def test_pitch_and_playback_rate_use_take_info_values(registered_tools):
    tools, track = registered_tools
    take = track.items[0].active_take

    pitch = tools["adjust_pitch"](0, 0, -7.0)
    rate = tools["adjust_playback_rate"](0, 0, 0.5)

    assert pitch["pitch_semitones"] == -7.0
    assert rate["playback_rate"] == 0.5
    assert take.values["D_PITCH"] == -7.0
    assert take.values["D_PLAYRATE"] == 0.5


def test_invalid_playback_rate_is_rejected(registered_tools):
    tools, _ = registered_tools

    assert tools["adjust_playback_rate"](0, 0, 0.0) == {
        "success": False,
        "error": "rate must be greater than zero",
    }
