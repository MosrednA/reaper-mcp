from contextlib import nullcontext
from types import SimpleNamespace

from test_project_tools import ToolRegistry

from reaper_mcp import validation_tools as validation


def test_preflight_reports_empty_midi_and_missing_audio(monkeypatch,tmp_path):
    items=[SimpleNamespace(id='empty',active_take=SimpleNamespace(id='midi',is_midi=True)),
           SimpleNamespace(id='audio',active_take=SimpleNamespace(id='audio',is_midi=False))]
    track=SimpleNamespace(id='track',name='Test',n_items=2,items=items)
    project=SimpleNamespace(n_tracks=1,tracks=[track],path=str(tmp_path))
    monkeypatch.setattr(validation,'get_project',lambda:project)
    monkeypatch.setattr(validation,'current_project_file',lambda:str(tmp_path/'song.rpp'))
    monkeypatch.setattr(validation.reapy,'inside_reaper',nullcontext)
    rpr=SimpleNamespace(
        GetMediaTrackInfo_Value=lambda t,k:1 if k=='B_MUTE' else 0,
        TrackFX_GetInstrument=lambda t:-1,
        GetMediaItemInfo_Value=lambda *args:0,
        MIDI_CountEvts=lambda *args:(0,'midi',0,0,0),
        GetMediaItemTake_Source=lambda *args:'source',
        GetMediaSourceFileName=lambda *args:('source','missing.wav',4096),
    )
    monkeypatch.setattr(validation,'RPR',rpr)
    registry=ToolRegistry()
    validation.register_tools(registry)
    result=registry.tools['check_project']()
    assert result['success']
    assert {i['code'] for i in result['issues']} == {
        'empty_midi','missing_media','track_muted','no_local_instrument'}
    assert result['audibility_verified'] is False
