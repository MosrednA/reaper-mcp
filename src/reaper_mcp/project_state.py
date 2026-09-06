from pathlib import Path
from typing import Protocol, TypedDict

from reapy import reascript_api as RPR


class ProjectInfo(Protocol):
    id: str
    bpm: float


def current_project_file() -> str:
    return str(RPR.EnumProjects(-1, "", 4096)[2])


class MarkerEntry(TypedDict):
    index: int
    name: str
    color: int
    position: float


class RegionEntry(TypedDict):
    index: int
    name: str
    color: int
    start: float
    end: float


def project_markers(project_id: str) -> tuple[list[MarkerEntry], list[RegionEntry]]:
    markers: list[MarkerEntry] = []
    regions: list[RegionEntry] = []
    index = 0
    while True:
        result = RPR.EnumProjectMarkers3(project_id, index, False, 0., 0., "", 0, 0)
        if not result[0]:
            break
        _, _, _, region, start, end, _, number, color = result
        handle = RPR.GetRegionOrMarker(project_id, index, "")
        named = RPR.GetSetRegionOrMarkerInfo_String(project_id, handle, "P_NAME", "", False)
        if not named[0]:
            raise RuntimeError("REAPER failed to read a region/marker name")
        name = named[4]
        entry = {"index": number, "name": name, "color": color}
        if region:
            regions.append({**entry, "start": start, "end": end})
        else:
            markers.append({**entry, "position": start})
        index += 1
    return markers, regions


def verify_project_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"REAPER did not write the project: {path}")
    with path.open("rb") as stream:
        if not stream.read(64).lstrip().startswith(b"<REAPER_PROJECT"):
            raise RuntimeError(f"Not a REAPER project: {path}")


def write_project(project_id: str, path: Path, options: int) -> None:
    before = path.stat().st_mtime_ns if path.exists() else None
    RPR.Main_SaveProjectEx(project_id, str(path), options)
    verify_project_file(path)
    if before is not None and path.stat().st_mtime_ns == before:
        raise RuntimeError("REAPER did not refresh the existing project file")


def get_project_time_signature(project: ProjectInfo) -> tuple[int, int]:
    result = RPR.TimeMap_GetTimeSigAtTime(project.id, 0.0, 0, 0, 0.0)
    return int(result[2]), int(result[3])


def set_project_time_signature(
    project: ProjectInfo, numerator: int, denominator: int
) -> tuple[int, int]:
    if numerator <= 0 or denominator <= 0:
        raise ValueError("numerator and denominator must be greater than zero")

    marker_index = int(RPR.FindTempoTimeSigMarker(project.id, 0.0))
    succeeded = RPR.SetTempoTimeSigMarker(
        project.id,
        marker_index,
        0.0,
        -1,
        -1.0,
        project.bpm,
        numerator,
        denominator,
        False,
    )
    if not succeeded:
        raise RuntimeError("REAPER failed to set the project time signature")
    return get_project_time_signature(project)
