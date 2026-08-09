from types import SimpleNamespace

from reaper_mcp import project_state, project_tools


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


class FakeRPR:
    def __init__(self):
        self.numerator = 4
        self.denominator = 4
        self.marker_index = -1
        self.set_calls = []

    def TimeMap_GetTimeSigAtTime(self, project_id, time, numerator, denominator, tempo):
        return [project_id, time, self.numerator, self.denominator, 120.0]

    def FindTempoTimeSigMarker(self, project_id, time):
        return self.marker_index

    def SetTempoTimeSigMarker(self, *args):
        self.set_calls.append(args)
        self.numerator = args[6]
        self.denominator = args[7]
        return True


def test_project_time_signature_uses_complete_reaper_api(monkeypatch):
    rpr = FakeRPR()
    project = SimpleNamespace(id="project", bpm=128.0)
    monkeypatch.setattr(project_state, "RPR", rpr)

    assert project_state.get_project_time_signature(project) == (4, 4)
    assert project_state.set_project_time_signature(project, 7, 8) == (7, 8)
    assert rpr.set_calls == [("project", -1, 0.0, -1, -1.0, 128.0, 7, 8, False)]


def test_project_info_reports_numerator_and_denominator(monkeypatch):
    project = SimpleNamespace(
        id="project",
        name="Song",
        path="C:/Song.rpp",
        bpm=120.0,
        length=8.0,
        n_tracks=2,
        n_markers=0,
        n_regions=0,
    )
    monkeypatch.setattr(project_tools, "get_project", lambda: project)
    monkeypatch.setattr(project_tools, "get_project_time_signature", lambda _: (6, 8))
    registry = ToolRegistry()
    project_tools.register_tools(registry)

    result = registry.tools["get_project_info"]()

    assert result["success"] is True
    assert result["time_signature"] == "6/8"


def test_invalid_time_signature_is_failure_atomic(monkeypatch):
    rpr = FakeRPR()
    project = SimpleNamespace(id="project", bpm=120.0)
    monkeypatch.setattr(project_state, "RPR", rpr)

    try:
        project_state.set_project_time_signature(project, 4, 0)
    except ValueError as error:
        assert str(error) == "numerator and denominator must be greater than zero"
    else:
        raise AssertionError("invalid time signature was accepted")

    assert rpr.set_calls == []
