import logging
import math

import reapy
from pydantic import BaseModel, ConfigDict, Field
from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project

logger = logging.getLogger("reaper_mcp.midi_tools")


class MidiNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pitch: int = Field(ge=0, le=127, strict=True)
    start: float = Field(ge=0, allow_inf_nan=False)
    length: float = Field(gt=0, allow_inf_nan=False)
    velocity: int = Field(default=100, ge=1, le=127, strict=True)
    channel: int = Field(default=0, ge=0, le=15, strict=True)


def _insert_notes(item, notes: list[MidiNote]) -> int:
    """Validate first, append unsorted, verify count, roll back new notes on failure."""
    notes = [MidiNote.model_validate(note) for note in notes]
    if not 1 <= len(notes) <= 8192:
        raise ValueError("Provide 1 to 8192 notes")
    if any(note.start + note.length > item.length + 1e-7 for note in notes):
        raise ValueError("Notes must fit inside the MIDI item")
    take = item.active_take
    if not take.is_midi:
        raise ValueError("Item is not a MIDI item")
    with reapy.inside_reaper():
        count = RPR.MIDI_CountEvts(take.id, 0, 0, 0)
        before = count[2]
        try:
            for note in notes:
                start = RPR.MIDI_GetPPQPosFromProjTime(take.id, item.position + note.start)
                end = RPR.MIDI_GetPPQPosFromProjTime(
                    take.id, item.position + note.start + note.length
                )
                if not RPR.MIDI_InsertNote(
                    take.id, False, False, start, end,
                    note.channel, note.pitch, note.velocity, True,
                )[0]:
                    raise RuntimeError("REAPER rejected a MIDI note")
            after = RPR.MIDI_CountEvts(take.id, 0, 0, 0)[2]
            if after - before != len(notes):
                raise RuntimeError("MIDI note count does not match the requested batch")
        except Exception:
            after = RPR.MIDI_CountEvts(take.id, 0, 0, 0)[2]
            for index in range(after - 1, before - 1, -1):
                RPR.MIDI_DeleteNote(take.id, index)
            raise
        finally:
            RPR.MIDI_Sort(take.id)
            RPR.UpdateItemInProject(item.id)
    return len(notes)


def _new_item(track, start: float, length: float):
    if not math.isfinite(start) or start < 0 or not math.isfinite(length) or length <= 0:
        raise ValueError("start_position must be finite/nonnegative and length finite/positive")
    result = RPR.CreateNewMIDIItemInProj(track.id, start, start + length, False)
    item = reapy.Item(result[0])
    if not item.active_take.is_midi:
        raise RuntimeError("REAPER did not create a valid MIDI take")
    return item


def _create_notes(track, start: float, length: float, notes: list[MidiNote]):
    item = _new_item(track, start, length)
    try:
        _insert_notes(item, notes)
    except Exception:
        RPR.DeleteTrackMediaItem(track.id, item.id)
        raise
    return item

# GM standard drum MIDI notes
DRUM_MAPPINGS = {
    "k": 36,  # kick  - C1
    "s": 38,  # snare - D1
    "h": 42,  # hihat closed - F#1
    "o": 46,  # hihat open   - A#1
    "t": 41,  # tom low  - F1
    "m": 45,  # tom mid  - A1
    "f": 48,  # tom high - C2
    "c": 49,  # crash - C#2
    "r": 51,  # ride  - D#2
}

CHORD_TYPES = {
    "maj":   [0, 4, 7],
    "min":   [0, 3, 7],
    "m":     [0, 3, 7],
    "dim":   [0, 3, 6],
    "aug":   [0, 4, 8],
    "maj7":  [0, 4, 7, 11],
    "min7":  [0, 3, 7, 10],
    "m7":    [0, 3, 7, 10],
    "7":     [0, 4, 7, 10],
    "dom7":  [0, 4, 7, 10],
    "dim7":  [0, 3, 6, 9],
    "hdim7": [0, 3, 6, 10],
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
}

NOTE_TO_NUMBER = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def _parse_chord(chord_str: str):
    """Return (intervals_list, root_semitone) for a chord string like 'Cm7', 'G', 'F#maj7'."""
    chord_str = chord_str.strip()
    if len(chord_str) >= 2 and chord_str[1] in ("#", "b"):
        root = chord_str[:2]
        chord_type = chord_str[2:] or "maj"
    else:
        root = chord_str[:1]
        chord_type = chord_str[1:] or "maj"
    if chord_type not in CHORD_TYPES or root not in NOTE_TO_NUMBER:
        raise ValueError(f"Unknown chord: {chord_str}")
    intervals = CHORD_TYPES[chord_type]
    root_num = NOTE_TO_NUMBER[root]
    return intervals, root_num


def register_tools(mcp):

    @mcp.tool()
    def create_midi_item(track_index: int, start_position: float, length: float) -> dict:
        """Create an empty MIDI item on a track. Returns item_id for use with add_midi_note."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            item = _new_item(track, start_position, length)
            return {
                "success": True,
                "item_id": item.id,
                "item_index": int(RPR.GetMediaItemInfo_Value(item.id, "IP_ITEMNUMBER")),
                "position": item.position,
                "length": item.length,
                "track_index": track_index,
            }
        except Exception as e:
            logger.exception("create_midi_item failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def add_midi_note(
        track_index: int,
        item_index: int,
        pitch: int,
        start: float,
        length: float,
        velocity: int = 100,
        channel: int = 0,
    ) -> dict:
        """
        Add a MIDI note to an existing MIDI item.
        pitch: MIDI note number 0–127 (60 = middle C, 69 = A4).
        start/length: seconds, relative to the item's start.
        channel: MIDI channel 0–15 (use 9 for drums).
        """
        try:
            project = get_project()
            track = project.tracks[track_index]
            item = track.items[item_index]
            _insert_notes(item, [MidiNote(start=start, length=length, pitch=pitch,
                                         velocity=velocity, channel=channel)])
            return {
                "success": True,
                "track_index": track_index,
                "item_index": item_index,
                "pitch": pitch,
                "start": start,
                "length": length,
                "velocity": velocity,
                "channel": channel,
            }
        except Exception as e:
            logger.exception("add_midi_note failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def add_midi_notes(track_index: int, item_index: int, notes: list[MidiNote]) -> dict:
        """Add 1–8192 notes atomically; start/length are seconds relative to the item."""
        try:
            if track_index < 0 or item_index < 0:
                raise ValueError("Track/item indices must be nonnegative")
            item = get_project().tracks[track_index].items[item_index]
            return {"success": True, "notes_added": _insert_notes(item, notes)}
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def create_midi_part(
        track_index: int, start_position: float, length: float, notes: list[MidiNote]
    ) -> dict:
        """Create a complete MIDI clip. Note times are seconds relative to the new clip."""
        try:
            if track_index < 0:
                raise ValueError("track_index must be nonnegative")
            validated = [MidiNote.model_validate(note) for note in notes]
            track = get_project().tracks[track_index]
            item = _create_notes(track, start_position, length, validated)
            return {"success": True, "item_id": item.id,
                    "item_index": int(RPR.GetMediaItemInfo_Value(item.id, "IP_ITEMNUMBER")),
                    "notes_added": len(validated)}
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def create_chord_progression(
        track_index: int,
        chords: str,
        start_position: float,
        beats_per_chord: int = 4,
    ) -> dict:
        """
        Create a chord progression on a track as a single MIDI item.
        chords: comma-separated chord names, e.g. "C,G,Am,F" or "Cm7,Fm7,Bb7,Ebmaj7".
        Supports: maj, min/m, dim, aug, maj7, min7/m7, dom7/7, dim7, hdim7, sus2, sus4.
        All chords are voiced around middle C (MIDI 60).
        """
        try:
            project = get_project()
            track = project.tracks[track_index]
            chord_list = [c.strip() for c in chords.split(",")]
            seconds_per_beat = 60.0 / project.bpm
            chord_length = seconds_per_beat * beats_per_chord
            total_length = chord_length * len(chord_list)

            parsed = [_parse_chord(c) for c in chord_list]
            if beats_per_chord <= 0:
                raise ValueError("beats_per_chord must be positive")
            notes = []
            added_chords = []

            for i, chord_str in enumerate(chord_list):
                try:
                    intervals, root_num = parsed[i]
                    chord_start = i * chord_length
                    for interval in intervals:
                        note_num = 60 + root_num + interval
                        notes.append(MidiNote(
                            start=chord_start,
                            length=chord_length * 0.95,
                            pitch=note_num,
                            velocity=80,
                            channel=0,
                        ))
                    added_chords.append({
                        "chord": chord_str,
                        "position": chord_start,
                        "length": chord_length,
                    })
                except Exception as e:
                    logger.exception("REAPER operation failed")
                    raise ValueError(f"Invalid chord '{chord_str}': {e}") from e

            item = _create_notes(track, start_position, total_length, notes)

            return {
                "success": True,
                "item_id": item.id,
                "chords": added_chords,
                "start_position": start_position,
                "total_length": total_length,
            }
        except Exception as e:
            logger.exception("create_chord_progression failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def create_drum_pattern(
        track_index: int,
        pattern: str,
        start_position: float,
        beats: int = 4,
        repeats: int = 1,
    ) -> dict:
        """
        Create a drum pattern on a track using a step-sequencer string.
        Each character = one step. Characters: k=kick, s=snare, h=hihat(closed),
        o=hihat(open), t=tom(low), m=tom(mid), f=tom(high), c=crash, r=ride, .=rest.
        Example 4/4 rock beat (16 steps): "k...h...s...h..."
        All drum notes are placed on MIDI channel 9 (GM standard).
        """
        try:
            project = get_project()
            track = project.tracks[track_index]
            seconds_per_beat = 60.0 / project.bpm
            pattern_length = seconds_per_beat * beats
            total_length = pattern_length * repeats

            if not pattern or any(c not in DRUM_MAPPINGS and c != "." for c in pattern):
                raise ValueError("Pattern must contain drum symbols or dots")
            if beats <= 0 or repeats <= 0:
                raise ValueError("beats and repeats must be positive")
            notes = []
            time_per_step = pattern_length / len(pattern)

            for repeat in range(repeats):
                offset = repeat * pattern_length
                for i, char in enumerate(pattern):
                    if char in DRUM_MAPPINGS:
                        note_start = offset + i * time_per_step
                        notes.append(MidiNote(
                            start=note_start,
                            length=time_per_step * 0.5,
                            pitch=DRUM_MAPPINGS[char],
                            velocity=100,
                            channel=9,
                        ))

            item = _create_notes(track, start_position, total_length, notes)

            return {
                "success": True,
                "item_id": item.id,
                "pattern": pattern,
                "repeats": repeats,
                "start_position": start_position,
                "total_length": total_length,
            }
        except Exception as e:
            logger.exception("create_drum_pattern failed")
            return {"success": False, "error": str(e)}
