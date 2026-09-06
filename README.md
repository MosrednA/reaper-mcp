# REAPER MCP Server

A Model Context Protocol (MCP) server that enables AI agents to control REAPER DAW — 63 tools covering project management, tracks, MIDI, FX, mixing, mastering, rendering, and audio analysis.

## Requirements

- [REAPER](https://www.reaper.fm/) 7.79+ installed and running (native marker-name API)
- Python 3.10+
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) 2.x
- REAPER's distant API enabled (see [Setup](#setting-up-reaper))

## Installation

```bash
pip install reaper-mcp-server
```

Or install from source:

```bash
git clone https://github.com/bonfire-systems/reaper-mcp.git
cd reaper-mcp
pip install -e .
```

## Setting Up REAPER

The server communicates with REAPER via [python-reapy](https://github.com/RomeoDespres/reapy), which requires REAPER's distant API to be enabled.

1. Open REAPER
2. Go to Actions > Run ReaScript
3. Select `scripts/enable_reapy.py` from this repo (or create a new script with the contents below)
   ```python
   import reapy
   reapy.config.enable_dist_api()
   ```
4. Restart REAPER

## Usage

### With Claude Desktop

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "reaper": {
      "command": "reaper-mcp-server",
      "args": []
    }
  }
}
```

### With Claude Code

```bash
claude mcp add reaper -- reaper-mcp-server
```

### Standalone

```bash
reaper-mcp-server          # start the server
reaper-mcp-server --debug  # with debug logging
```

## Development

Install the editable package with its test tools, then run the regression suite:

```bash
pip install -e ".[dev]"
pytest
```

## Tools (63)

### Project Management
`create_project` `load_project` `save_project` `get_project_info` `set_tempo` `set_time_signature` `set_cursor_position` `play_project` `stop_transport`

`save_project()` saves the active filename; an untitled project needs an explicit
`.rpp` path. `save_project(path)` performs Save As and changes the active filename
without reloading the project. `save_project_copy(path)` writes a snapshot while
keeping the active filename. Both verify that REAPER wrote an RPP. This uses
the native [Main_SaveProjectEx contract](https://www.reaper.fm/sdk/reascript/reascripthelp.html#Main_SaveProjectEx).

`get_project_info` separates `project_path` (RPP), `path` (project directory), and
`media_path`. Markers/regions include their actual displayed IDs, names, and bounds.

### Tracks
`create_track` `delete_track` `rename_track` `list_tracks` `get_track_info` `set_track_color` `create_bus` `create_send` `remove_send` `list_sends`

### MIDI
`create_midi_item` `add_midi_note` `create_chord_progression` `create_drum_pattern`

`create_midi_part(track_index, start_position, length, notes)` creates a complete
clip; `add_midi_notes(track_index, item_index, notes)` appends to one. Each note has
`pitch`, `start`, `length`, optional `velocity` (100) and `channel` (0). Times are
seconds relative to the item, including items later in the timeline. Batches are
limited to 8192 notes, validated before insertion, counted afterward, and rolled
back on insertion failure. Unknown chords/pattern symbols are rejected.

### FX & Instruments
`add_fx` `remove_fx` `bypass_fx` `list_track_fx` `get_fx_parameters` `set_fx_parameter` `load_fx_preset` `add_master_fx` `list_master_fx` `set_master_fx_parameter`

`get_fx_parameters` now accepts `offset=0`, `limit=128` (maximum 256),
`name_filter=""` and `include_midi_cc=False`. `next_offset` is the next raw plugin
index; null means finished. Names are filtered before values are read. Values are
retrieved within a short REAPER batch instead of thousands of separate UI ticks.
`set_fx_parameters(..., changes=[{"param_index": 14, "value": 0.4}])` validates
the entire batch, reads actual plugin values back, and rolls back on failure.
Values may differ from requests for discrete/quantized parameters.

### Audio
`import_audio_file` `edit_audio_item` `start_recording` `adjust_pitch` `adjust_playback_rate`

### Mixing
`set_track_volume` `set_track_pan` `set_track_mute` `set_track_solo` `set_send_volume` `set_master_volume` `add_volume_automation` `add_pan_automation`

### Rendering
`render_project` `render_stems` `render_time_selection`

Rendering uses REAPER's native sink configuration and preserves the project's
existing render settings. Stem renders restore track solo states, and
time-selection renders restore the original selection after completion or failure.

Rendering preserves the chosen mute/solo mix. It does not silently unmute tracks
or reload the project. REAPER timeline/routing updates are flushed through separate
distant calls before the render action, outside held API batches. Recording must
be stopped before rendering. Exports go to a temporary sibling file, are checked
for readable nonempty audio and expected rate/channels, then replace the requested
file. Failed renders leave a previous export intact. Stem filenames include a
track-number prefix so duplicate names cannot overwrite each other.

All tools in one MCP server share an ordered command lock: simultaneous requests
cannot interleave operations or corrupt reapy's single request/response stream.
External scripts and separate MCP server processes are outside that lock.

`check_project` is a read-only preflight for missing media, empty MIDI clips,
muted/soloed tracks/items, and inactive/missing local instruments. Warnings can be
intentional (for example MIDI routed to another track). It explicitly returns
`audibility_verified: false`; structural checks and a non-clipping export do not
prove every part is audible.

### Live regression check

`python scripts/smoke_live.py --output /path/to/test-output --sample /path/to/kick.wav`
opens a disposable REAPER tab, tests MIDI at a nonzero timeline position, Save As,
copy, marker names, parameter batches, stems followed by a full render, and measures
separate synth/drum windows. It restores the original project tab in `finally`.
Run only when REAPER is available and no other actor is editing it. Artifacts and
the machine-readable result remain in the supplied output directory.

After updating an editable installation, restart/reconnect the MCP server so it
reloads its modules and advertises the new schemas; REAPER itself need not restart.

### Mastering
`apply_mastering_chain` `apply_limiter` `normalize_project`

### Analysis
`analyze_loudness` `analyze_dynamics` `analyze_frequency_spectrum` `analyze_stereo_field` `analyze_transients` `detect_clipping`

## Configuration

The server stores its configuration in your platform's config directory:

- macOS: `~/Library/Application Support/reaper-mcp/config.json`
- Linux: `~/.config/reaper-mcp/config.json`
- Windows: `%APPDATA%\reaper-mcp\config.json`

## License

MIT
