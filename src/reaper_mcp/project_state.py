from typing import Protocol

from reapy import reascript_api as RPR


class ProjectInfo(Protocol):
    id: str
    bpm: float


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
