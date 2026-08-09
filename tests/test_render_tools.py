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

    @property
    def n_tracks(self):
        return len(self.tracks)


def _registered_tools(monkeypatch, render_command):
    project = FakeProject()
    monkeypatch.setattr(render_tools, "get_project", lambda: project)
    monkeypatch.setattr(render_tools, "_set_render_settings", lambda *_, **__: None)
    monkeypatch.setattr(render_tools.RPR, "Main_OnCommand", render_command)
    registry = ToolRegistry()
    render_tools.register_tools(registry)
    return registry.tools, project


def test_render_stems_restores_exact_solo_states(monkeypatch, tmp_path):
    tools, project = _registered_tools(monkeypatch, lambda *_: None)

    result = tools["render_stems"](str(tmp_path))

    assert result["success"] is True
    assert [track.values["I_SOLO"] for track in project.tracks] == [2.0, 0.0]


def test_render_stems_restores_solo_states_on_failure(monkeypatch, tmp_path):
    def fail_render(*_):
        raise RuntimeError("render failed")

    tools, project = _registered_tools(monkeypatch, fail_render)

    result = tools["render_stems"](str(tmp_path))

    assert result == {"success": False, "error": "render failed"}
    assert [track.values["I_SOLO"] for track in project.tracks] == [2.0, 0.0]
