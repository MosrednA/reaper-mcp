"""Read-only structural checks; these cannot certify an audible mix."""
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import reapy
from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project
from reaper_mcp.project_state import current_project_file

logger = logging.getLogger(__name__)


@dataclass
class Issue:
    code: str
    track_index: int
    message: str
    item_index: int | None = None


def register_tools(mcp):
    @mcp.tool()
    def check_project() -> dict:
        """Inspect missing media, empty MIDI, inactive instruments and mute/solo states.

        Warnings may be intentional. This is not a listening or audibility test.
        """
        try:
            project = get_project()
            filename = current_project_file()
            directory = Path(filename).parent if filename else Path(project.path)
            issues: list[Issue] = []
            items = 0
            notes = 0
            with reapy.inside_reaper():
                for index in range(project.n_tracks):
                    track = project.tracks[index]
                    for key, code in [("B_MUTE", "track_muted"), ("I_SOLO", "track_soloed")]:
                        if RPR.GetMediaTrackInfo_Value(track.id, key):
                            issues.append(Issue(code, index, track.name))
                    instrument = RPR.TrackFX_GetInstrument(track.id)
                    if instrument >= 0 and (
                        not RPR.TrackFX_GetEnabled(track.id, instrument)
                        or RPR.TrackFX_GetOffline(track.id, instrument)
                    ):
                        issues.append(Issue("inactive_instrument", index, track.name))
                    has_midi = False
                    for item_index in range(track.n_items):
                        item = track.items[item_index]
                        take = item.active_take
                        items += 1
                        if RPR.GetMediaItemInfo_Value(item.id, "B_MUTE"):
                            issues.append(Issue("item_muted", index, "Muted item", item_index))
                        if take.is_midi:
                            has_midi = True
                            count = RPR.MIDI_CountEvts(take.id, 0, 0, 0)
                            notes += count[2]
                            if count[2] == 0:
                                issues.append(Issue("empty_midi", index, "No MIDI notes", item_index))
                        else:
                            source = RPR.GetMediaItemTake_Source(take.id)
                            name = RPR.GetMediaSourceFileName(source, "", 4096)[1]
                            if name:
                                path = Path(name)
                                path = path if path.is_absolute() else directory / path
                                if not path.is_file():
                                    issues.append(Issue("missing_media", index, str(path), item_index))
                    if has_midi and instrument < 0:
                        issues.append(Issue("no_local_instrument", index,
                                            "MIDI track has no local instrument; check its routing"))
            return {"success": True, "project_path": filename, "track_count": project.n_tracks,
                    "item_count": items, "note_count": notes,
                    "issues": [asdict(issue) for issue in issues],
                    "audibility_verified": False}
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}
