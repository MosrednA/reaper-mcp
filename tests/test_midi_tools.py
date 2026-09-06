from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from reaper_mcp import midi_tools as midi


@pytest.fixture
def native(monkeypatch):
    notes = [(0, 10, 60)]
    item = SimpleNamespace(id="item", position=12., length=4.,
                           active_take=SimpleNamespace(id="take", is_midi=True))
    monkeypatch.setattr(midi.reapy, "inside_reaper", nullcontext)
    monkeypatch.setattr(midi.RPR, "MIDI_CountEvts",
                        lambda *_: (len(notes), "take", len(notes), 0, 0))
    monkeypatch.setattr(midi.RPR, "MIDI_GetPPQPosFromProjTime", lambda t, s: s * 960)
    def insert(t, selected, muted, start, end, channel, pitch, velocity, no_sort):
        if pitch == 127:
            return (0,)
        notes.append((start, end, pitch))
        return (1,)
    monkeypatch.setattr(midi.RPR, "MIDI_InsertNote", insert)
    monkeypatch.setattr(midi.RPR, "MIDI_DeleteNote", lambda t, i: notes.pop(i))
    monkeypatch.setattr(midi.RPR, "MIDI_Sort", lambda *_: None)
    monkeypatch.setattr(midi.RPR, "UpdateItemInProject", lambda *_: None)
    return item, notes


def test_notes_are_relative_to_nonzero_item_position(native):
    item, notes = native
    assert midi._insert_notes(item, [midi.MidiNote(pitch=62, start=.5, length=.25)]) == 1
    assert notes[-1] == (12.5 * 960, 12.75 * 960, 62)


def test_batch_rolls_back_partial_insertions(native):
    item, notes = native
    with pytest.raises(RuntimeError):
        midi._insert_notes(item, [midi.MidiNote(pitch=p, start=0, length=.5)
                                  for p in [62, 127]])
    assert notes == [(0, 10, 60)]


@pytest.mark.parametrize("change", [{"pitch":128}, {"velocity":0}, {"start":float('nan')},
                                   {"length":-1}, {"channel":16}, {"extra":1}])
def test_invalid_notes_rejected_before_mutation(native, change):
    item, notes = native
    with pytest.raises(ValueError):
        midi._insert_notes(item, [{"pitch":60, "start":0, "length":1, **change}])
    assert len(notes) == 1


def test_overflow_rejected_before_mutation(native):
    item, notes = native
    with pytest.raises(ValueError):
        midi._insert_notes(item, [midi.MidiNote(pitch=60, start=3.5, length=1)])
    assert len(notes) == 1


def test_item_pointer_unpacked_from_native_tuple(monkeypatch):
    take = SimpleNamespace(is_midi=True)
    monkeypatch.setattr(midi.RPR, "CreateNewMIDIItemInProj",
                        lambda *args: ("item-pointer", *args))
    def construct(pointer):
        assert pointer == "item-pointer"
        return SimpleNamespace(active_take=take)
    monkeypatch.setattr(midi.reapy, "Item", construct)
    assert midi._new_item(SimpleNamespace(id="track"), 12, 4).active_take is take


def test_unknown_chord_is_not_silently_changed_to_c_major():
    with pytest.raises(ValueError):
        midi._parse_chord("bananas")
