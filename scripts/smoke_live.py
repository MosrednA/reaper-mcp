"""Opt-in live regression in a disposable REAPER tab. Never edits the user's song.

Run with --output DIRECTORY --sample PATH_TO_SHORT_WAV. Saves test artifacts there.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from reapy import reascript_api as RPR

from reaper_mcp import (
    audio_tools,
    fx_tools,
    midi_tools,
    project_tools,
    render_tools,
    validation_tools,
)
from reaper_mcp.connection import get_project


class Registry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sample', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assert args.sample.is_file()
    registry = Registry()
    for module in [project_tools, midi_tools, fx_tools, audio_tools,
                   render_tools, validation_tools]:
        module.register_tools(registry)
    results = {}

    def call(name, **kwargs):
        result = registry.tools[name](**kwargs)
        assert result['success'], (name, result)
        results[name] = result
        return result

    original = get_project().id
    test_project = None
    try:
        RPR.Main_OnCommand(40859, 0)  # New project tab
        test_project = get_project().id
        assert test_project != original
        assert RPR.CountTracks(test_project) == 0
        for index in range(2):
            RPR.InsertTrackAtIndex(index, False)
            track = RPR.GetTrack(test_project, index)
            RPR.GetSetMediaTrackInfo_String(track, 'P_NAME', ['Synth', 'Drum'][index], True)
            RPR.SetMediaTrackInfo_Value(track, 'D_VOL', .3)
        call('add_fx', track_index=0, fx_name='ReaSynth')
        clip = call('create_midi_part', track_index=0, start_position=1., length=1.,
                    notes=[{'pitch':60,'start':.25,'length':.25}])
        call('add_midi_notes', track_index=0, item_index=clip['item_index'],
             notes=[{'pitch':67,'start':.6,'length':.1}])
        item = get_project().tracks[0].items[clip['item_index']]
        note = RPR.MIDI_GetNote(item.active_take.id, 0, False, False, 0.,0.,0,0,0)
        assert abs(RPR.MIDI_GetProjTimeFromPPQPos(item.active_take.id,note[5])-1.25)<1e-6
        call('import_audio_file', track_index=1, position=2., file_path=str(args.sample.resolve()))
        RPR.AddProjectMarker2(test_project, True, 1., 2., 'Smoke hook', 10, 0)
        call('save_project', project_path=str(out/'live-smoke.rpp'))
        call('save_project_copy', project_path=str(out/'live-copy.rpp'))
        info=call('get_project_info')
        assert Path(info['project_path']) == out/'live-smoke.rpp'
        assert info['regions'][0]['name'] == 'Smoke hook'
        page=call('get_fx_parameters',track_index=0,fx_index=0,limit=2)
        first=page['parameters'][0]
        call('set_fx_parameters',track_index=0,fx_index=0,
             changes=[{'param_index':first['index'],'value':first['normalized_value']}])
        check=call('check_project')
        assert check['note_count'] == 2 and check['issues'] == []
        get_project().time_selection=(.25,.5)
        RPR.Main_OnCommand(40100, 0)  # Intentionally offline: preparation must recover audio
        call('render_stems',output_directory=str(out/'stems'))
        drum_stem = results['render_stems']['stems'][1]['output_path']
        stem_audio, stem_rate = sf.read(drum_stem, always_2d=True)
        stem_window = stem_audio[int(2*stem_rate):int(2.08*stem_rate)]
        assert np.sqrt(np.mean(stem_window*stem_window)) > .01, 'Offline drum missing in stem'
        RPR.Main_OnCommand(40100, 0)  # Exercise recovery again for the full mix
        call('render_time_selection',output_path=str(out/'full.wav'),start=0.,end=3.)
        selection=get_project().time_selection
        assert (selection.start,selection.end)==(.25,.5)
        assert all(RPR.GetMediaTrackInfo_Value(RPR.GetTrack(test_project,i),'I_SOLO')==0
                   for i in range(2))
        audio,rate=sf.read(out/'full.wav',always_2d=True)
        drum=audio[int(2*rate):int(2.12*rate)]
        synth=audio[int(1.25*rate):int(1.5*rate)]
        assert np.sqrt(np.mean(drum*drum))>.01, 'Drum missing after stem renders'
        assert np.sqrt(np.mean(synth*synth))>.001, 'MIDI synth missing'
        results['offline_media_recovery'] = True
        results['audio_check']={'drum_rms':float(np.sqrt(np.mean(drum*drum))),
                                'synth_rms':float(np.sqrt(np.mean(synth*synth)))}
        call('save_project')
        (out/'results.json').write_text(json.dumps(results,indent=2))
        print(json.dumps(results,indent=2),flush=True)
    finally:
        if test_project is not None and test_project != original:
            RPR.SelectProjectInstance(test_project)
            RPR.Main_SaveProjectEx(test_project,str(out/'live-smoke.rpp'),8)
            RPR.Main_OnCommand(40860,0)  # Close only the disposable, saved tab
        RPR.SelectProjectInstance(original)


if __name__=='__main__':
    main()
