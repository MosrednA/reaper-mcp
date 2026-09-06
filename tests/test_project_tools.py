from pathlib import Path
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
    monkeypatch.setattr(project_tools, "project_markers", lambda _: ([], []))
    monkeypatch.setattr(project_tools, "current_project_file", lambda: "C:/Song.rpp")
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


def test_save_as_and_copy_have_distinct_native_options(monkeypatch, tmp_path):
    state = {"path":""}
    calls = []
    monkeypatch.setattr(project_tools, "get_project", lambda: SimpleNamespace(id="project"))
    monkeypatch.setattr(project_tools, "current_project_file", lambda: state["path"])
    def save(project, name, options):
        calls.append(options)
        Path(name).write_text('<REAPER_PROJECT 0.1\n>\n')
        if options & 8:
            state["path"] = name
    monkeypatch.setattr(project_tools.RPR, "Main_SaveProjectEx", save)
    registry = ToolRegistry()
    project_tools.register_tools(registry)
    active = tmp_path / "song.rpp"
    assert registry.tools["save_project"](str(active))["success"]
    assert registry.tools["save_project_copy"](str(tmp_path/"copy.rpp"))["success"]
    assert state["path"] == str(active)
    assert calls == [8, 0]


def test_save_failure_does_not_report_existing_file_as_success(monkeypatch, tmp_path):
    monkeypatch.setattr(project_tools, "get_project", lambda: SimpleNamespace(id="project"))
    monkeypatch.setattr(project_tools, "current_project_file", lambda: "")
    monkeypatch.setattr(project_tools.RPR, "Main_SaveProjectEx", lambda *_: None)
    registry = ToolRegistry()
    project_tools.register_tools(registry)
    assert not registry.tools["save_project"](str(tmp_path/"missing.rpp"))["success"]


def test_region_names_use_string_api_not_broken_char_pointer(monkeypatch):
    rpr = SimpleNamespace(
        EnumProjectMarkers3=lambda project,index,*_: ((1, project,index,1,2.,4.,"",7,123)
                                                    if index == 0 else (0,)),
        GetRegionOrMarker=lambda *_: "region",
        GetSetRegionOrMarkerInfo_String=lambda *_: (1,"project","region","P_NAME","Hook",0),
    )
    monkeypatch.setattr(project_state,"RPR",rpr)
    markers, regions = project_state.project_markers("project")
    assert markers == []
    assert regions == [{"index":7,"name":"Hook","color":123,"start":2.,"end":4.}]


def test_noop_save_of_existing_project_is_not_success(monkeypatch,tmp_path):
    path=tmp_path/'existing.rpp'
    path.write_text('<REAPER_PROJECT 0.1\n>\n')
    monkeypatch.setattr(project_state.RPR,'Main_SaveProjectEx',lambda *_:None)
    try:
        project_state.write_project('project',path,8)
    except RuntimeError as error:
        assert 'refresh' in str(error)
    else:
        raise AssertionError('Unchanged old file was reported as a save')
