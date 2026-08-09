import base64
from pathlib import Path

from reaper_mcp import render_tools


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


class FakeTrack:
    def __init__(self, name, solo_state):
        self.name = name
        self.values = {"I_SOLO": float(solo_state)}

    def get_info_value(self, name):
        return self.values[name]

    def set_info_value(self, name, value):
        self.values[name] = value


class FakeProject:
    def __init__(self):
        self.tracks = [FakeTrack("Lead", 2), FakeTrack("Bass", 0)]
        self.length = 8.0
        self.time_selection = (1.0, 3.0)

    @property
    def n_tracks(self):
        return len(self.tracks)


class FakeRpr:
    def __init__(self):
        self.strings = {
            key: f"original:{key}" for key in render_tools._STRING_RENDER_KEYS
        }
        self.numbers = {
            key: float(index + 10)
            for index, key in enumerate(render_tools._NUMERIC_RENDER_KEYS)
        }
        self.string_writes = []
        self.number_writes = []

    def get_set_string(self, project, key, value, set_value):
        if set_value:
            self.strings[key] = value
            self.string_writes.append((key, value))
        return [1, project, key, self.strings[key], set_value]

    def get_set_number(self, project, key, value, set_value):
        if set_value:
            self.numbers[key] = value
            self.number_writes.append((key, value))
        return self.numbers[key]


def _registered_tools(monkeypatch, render_command):
    project = FakeProject()
    monkeypatch.setattr(render_tools, "get_project", lambda: project)
    monkeypatch.setattr(render_tools, "_set_render_settings", lambda *_, **__: None)
    monkeypatch.setattr(render_tools.RPR, "Main_OnCommand", render_command)
    registry = ToolRegistry()
    render_tools.register_tools(registry)
    return registry.tools, project


def test_wav_render_settings_use_reaper_string_contract(monkeypatch, tmp_path):
    rpr = FakeRpr()
    monkeypatch.setattr(render_tools.RPR, "GetSetProjectInfo_String", rpr.get_set_string)
    monkeypatch.setattr(render_tools.RPR, "GetSetProjectInfo", rpr.get_set_number)

    output = render_tools._set_render_settings(
        str(tmp_path / "pad.anything"),
        "wav",
        48_000,
        24,
        2,
        render_tools.BOUNDS_ENTIRE_PROJECT,
    )

    assert output == (tmp_path / "pad.wav").resolve()
    assert rpr.strings["RENDER_FILE"] == str(tmp_path.resolve())
    assert rpr.strings["RENDER_PATTERN"] == "pad"
    assert base64.b64decode(rpr.strings["RENDER_FORMAT"]) == b"evaw\x18\x00\x01"
    assert rpr.strings["RENDER_FORMAT2"] == ""
    assert rpr.numbers["RENDER_SETTINGS"] == 0.0
    assert rpr.numbers["RENDER_SRATE"] == 48_000.0
    assert rpr.numbers["RENDER_CHANNELS"] == 2.0
    assert rpr.numbers["RENDER_BOUNDSFLAG"] == 1.0
    assert rpr.numbers["RENDER_ADDTOPROJ"] == 0.0
    assert rpr.numbers["RENDER_NORMALIZE"] == 0.0
    assert rpr.numbers["RENDER_DITHER"] == 0.0


def test_sink_formats_use_reaper_fourcc_contract():
    assert base64.b64decode(render_tools._sink_configuration("mp3", 24)) == b"l3pm"
    assert base64.b64decode(render_tools._sink_configuration("ogg", 24)) == b"ggOv"
    assert base64.b64decode(render_tools._sink_configuration("flac", 24)) == b"calf"


def test_render_file_restores_all_user_render_settings(monkeypatch, tmp_path):
    project = FakeProject()
    rpr = FakeRpr()
    initial_strings = dict(rpr.strings)
    initial_numbers = dict(rpr.numbers)
    monkeypatch.setattr(render_tools, "get_project", lambda: project)
    monkeypatch.setattr(render_tools.RPR, "GetSetProjectInfo_String", rpr.get_set_string)
    monkeypatch.setattr(render_tools.RPR, "GetSetProjectInfo", rpr.get_set_number)

    output = tmp_path / "analysis.wav"

    def render(*_):
        output.write_bytes(b"RIFFtest")

    monkeypatch.setattr(render_tools.RPR, "Main_OnCommand", render)

    result = render_tools._render_file(
        str(output), "wav", 48_000, 24, 2, render_tools.BOUNDS_ENTIRE_PROJECT
    )

    assert result == output.resolve()
    assert rpr.strings == initial_strings
    assert rpr.numbers == initial_numbers


def test_render_stems_restores_exact_solo_states(monkeypatch, tmp_path):
    tools, project = _registered_tools(monkeypatch, lambda *_: None)
    monkeypatch.setattr(
        render_tools,
        "_render_file",
        lambda output_path, *_args: Path(output_path),
    )

    result = tools["render_stems"](str(tmp_path))

    assert result["success"] is True
    assert [track.values["I_SOLO"] for track in project.tracks] == [2.0, 0.0]


def test_render_stems_restores_solo_states_on_failure(monkeypatch, tmp_path):
    tools, project = _registered_tools(monkeypatch, lambda *_: None)

    def fail_render(*_args):
        raise RuntimeError("render failed")

    monkeypatch.setattr(render_tools, "_render_file", fail_render)

    result = tools["render_stems"](str(tmp_path))

    assert result == {"success": False, "error": "render failed"}
    assert [track.values["I_SOLO"] for track in project.tracks] == [2.0, 0.0]


def test_time_selection_render_restores_original_selection(monkeypatch, tmp_path):
    project = FakeProject()
    monkeypatch.setattr(render_tools, "get_project", lambda: project)
    output = tmp_path / "selection.wav"
    output.write_bytes(b"RIFFtest")
    monkeypatch.setattr(render_tools, "_render_file", lambda *_args: output)
    registry = ToolRegistry()
    render_tools.register_tools(registry)

    result = registry.tools["render_time_selection"](
        str(output), 4.0, 6.0, sample_rate=48_000
    )

    assert result["success"] is True
    assert project.time_selection == (1.0, 3.0)
