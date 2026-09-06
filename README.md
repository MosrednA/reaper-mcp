# REAPER MCP Server — MosrednA fork

A Model Context Protocol (MCP) server that enables AI agents to control REAPER DAW — 63 tools covering project management, tracks, MIDI, FX, mixing, mastering, rendering, and audio analysis.

This is [MosrednA/reaper-mcp](https://github.com/MosrednA/reaper-mcp), a fork of
[bonfire-systems/reaper-mcp](https://github.com/bonfire-systems/reaper-mcp).
The original project provides the foundation; MosrednA's changes focus on reapy
compatibility, reliable project operations, efficient music authoring, and export
verification. It works with MCP clients that can launch a local **STDIO** server.

## What's different in this fork?

| MosrednA update | Result |
|---|---|
| [Track compatibility](https://github.com/MosrednA/reaper-mcp/commit/a3ca3c8) | Native track-state access for mute, solo, colors and track operations across python-reapy versions. |
| [MCP 2 and reapy compatibility](https://github.com/MosrednA/reaper-mcp/commit/631df95) | MCP 2 server registration; corrected media, FX, project and mastering API usage, with regression tests. |
| [FX and native rendering](https://github.com/MosrednA/reaper-mcp/commit/7aedd6a) | Normalized FX parameters, native audio sink settings, render validation and restoration of project settings. |
| [Connection validation](https://github.com/MosrednA/reaper-mcp/commit/5554cc3) | Verify that the distant API really exposes the required functions; reconnect a stale session and report actionable errors. |
| [Offline media recovery](#render-limitations) | Bring project media online before rendering; regression check deliberately offlines samples before stems and the full mix. |
| [Music workflow fixes](https://github.com/MosrednA/reaper-mcp/commit/fb9c641) | Correct Save As and separate Save Copy; real project/marker metadata; MIDI batches with relative timing and rollback; bounded FX queries and parameter batches; serialized tool calls; safer exports and structural preflight. |

The latest workflow update adds five tools: `save_project_copy`, `create_midi_part`,
`add_midi_notes`, `set_fx_parameters`, and `check_project` (58 → 63 tools).
The current regression suite passes **50 tests**, plus a live disposable-project check of
saving, MIDI, FX, stems and a synth/drum render. See [render limitations](#render-limitations)
for the remaining uncertainty around earlier larger-session failures; these fixes do not guarantee
that every part is audible in every export.

## Requirements

- [REAPER](https://www.reaper.fm/) 7.79+ installed and running (native marker-name API)
- Python 3.10+
- A Python runtime configured in REAPER, with `reapy` importable there; Windows
  music-session validation used 64-bit REAPER and Python 3.12
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) 2.x
- REAPER's distant API enabled (see [Setup](#setting-up-reaper))

## Installation

Install **this fork from source**. A plain `pip install reaper-mcp-server` does not
select MosrednA's repository and must not be assumed to contain these changes.
The distribution and executable retain the original `reaper-mcp-server` name.

```bash
git clone https://github.com/MosrednA/reaper-mcp.git
cd reaper-mcp
```

Windows (PowerShell; Python 3.12 example):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m reaper_mcp --help
```

macOS/Linux:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m reaper_mcp --help
```

Use that same virtual environment in your MCP client. Shell activation is not
required when you use its absolute executable path.

## Setting Up REAPER

The server communicates with REAPER via [python-reapy](https://github.com/RomeoDespres/reapy), which requires REAPER's distant API to be enabled.

1. Configure Python in REAPER's Preferences > Plug-ins > ReaScript. The embedded
   runtime must be able to `import reapy`; installing into a terminal's virtual
   environment alone does not automatically configure REAPER's Python search path.
2. Open REAPER's Actions list and load/run a Python ReaScript.
3. Select `scripts/enable_reapy.py` from this repo (or create a new script with the contents below)
   ```python
   import reapy
   reapy.config.enable_dist_api()
   ```
4. Restart REAPER

If `import reapy` fails inside REAPER, make the installed environment's
`site-packages` directory available to that Python runtime before running the
setup script. Keep REAPER open when using the MCP tools. Plugins and sample files
must be installed or accessible on the same machine running REAPER.

## Usage

### Any local STDIO MCP client

In your client's MCP settings, add a local server using these values. Replace the
placeholder checkout location (`C:/path/to/reaper-mcp` or
`/absolute/path/reaper-mcp`) with your actual clone directory. These are examples,
not required installation locations.

| Field | Value |
|---|---|
| Name | `reaper` |
| Transport/type | `stdio` / local process |
| Command on Windows | `C:\path\to\reaper-mcp\.venv\Scripts\python.exe` |
| Command on macOS/Linux | `/absolute/path/reaper-mcp/.venv/bin/python` |
| Arguments | `-m`, `reaper_mcp` (two separate arguments) |
| Working directory | Optional when using the absolute interpreter path and editable install |
| Environment/authentication | No server-specific environment variables or API key required |

The client launches the process and communicates through stdin/stdout. This server
does not expose an HTTP/SSE URL; clients that accept only a remote URL cannot connect
directly. Run the client/server on the REAPER machine for this setup. If your client
has a tool timeout, allow enough time for a complete render (for example 300 seconds,
increasing it for longer projects).

For clients using the common `mcpServers` JSON shape:

```json
{
  "mcpServers": {
    "reaper": {
      "command": "C:/path/to/reaper-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "reaper_mcp"]
    }
  }
}
```

The surrounding configuration schema is client-specific: some use `servers`,
TOML, or form fields instead. Copy the command and arguments into the equivalent
fields; the JSON above is not a universal MCP config format. For macOS/Linux,
replace only the command with the corresponding absolute `.venv/bin/python` path.

After connecting, call `get_project_info` and `list_tracks` to verify the active
REAPER project. `check_project` can then check its structure without editing it.

### Codex example

From the repository directory, register the installed Windows environment using
the CLI (the resolved path also works when it contains spaces):

```powershell
$reaperPython = (Resolve-Path .\.venv\Scripts\python.exe).Path
codex mcp add reaper -- $reaperPython -m reaper_mcp
```

Or add the corresponding entry to your Codex `config.toml`:

```toml
[mcp_servers.reaper]
command = "C:/path/to/reaper-mcp/.venv/Scripts/python.exe"
args = ["-m", "reaper_mcp"]
tool_timeout_sec = 300
```

See the [official Codex MCP documentation](https://developers.openai.com/codex/mcp)
for configuration locations and client options.

### Claude Desktop example

Use the `mcpServers` JSON example above in `claude_desktop_config.json`.

### With Claude Code

```bash
claude mcp add reaper -- "/absolute/path/reaper-mcp/.venv/bin/python" -m reaper_mcp
```

### Standalone

```bash
python -m reaper_mcp          # use the installed environment's interpreter
python -m reaper_mcp --debug  # diagnostics go to stderr
```

This waits for an MCP client on STDIO; it is not an interactive shell or web server.
The installed `reaper-mcp-server` executable is an equivalent entry point.

### Updating an editable installation

From your checkout, run `git pull --ff-only`, then repeat the editable install command
with the same interpreter to pick up dependency changes. Restart/reconnect the MCP
server (or restart its client) to load the new code and tool schemas. REAPER itself
does not need restarting for a server-code update.

## Development

Install the editable package with its test tools, then run the regression suite:

```bash
pip install -e ".[dev]"
pytest
```

## Tools (63)

### Project Management
`create_project` `load_project` `save_project` `save_project_copy` `get_project_info` `set_tempo` `set_time_signature` `set_cursor_position` `play_project` `stop_transport`

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
`create_midi_item` `create_midi_part` `add_midi_note` `add_midi_notes` `create_chord_progression` `create_drum_pattern`

`create_midi_part(track_index, start_position, length, notes)` creates a complete
clip; `add_midi_notes(track_index, item_index, notes)` appends to one. Each note has
`pitch`, `start`, `length`, optional `velocity` (100) and `channel` (0). Times are
seconds relative to the item, including items later in the timeline. Batches are
limited to 8192 notes, validated before insertion, counted afterward, and rolled
back on insertion failure. Unknown chords/pattern symbols are rejected.

### FX & Instruments
`add_fx` `remove_fx` `bypass_fx` `list_track_fx` `get_fx_parameters` `set_fx_parameter` `set_fx_parameters` `load_fx_preset` `add_master_fx` `list_master_fx` `set_master_fx_parameter`

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
distant calls before the render action, outside held API batches. Before every
render, the native `Item: Set all media online` action reopens project
media, including media previously set offline. This does not start playback or
change FX offline states. No SWS extension is required. Recording must be stopped
before rendering. Exports go to a temporary sibling file, are checked
for readable nonempty audio and expected rate/channels, then replace the requested
file. Failed renders leave a previous export intact. Stem filenames include a
track-number prefix so duplicate names cannot overwrite each other.

All tools in one MCP server share an ordered command lock: simultaneous requests
cannot interleave operations or corrupt reapy's single request/response stream.
External scripts and separate MCP server processes are outside that lock.

### Project validation

`check_project` is a read-only preflight for missing media, empty MIDI clips,
muted/soloed tracks/items, and inactive/missing local instruments. Warnings can be
intentional (for example MIDI routed to another track). It explicitly returns
`audibility_verified: false`; structural checks and a non-clipping export do not
prove every part is audible.

### Render limitations

A reproduced failure is fixed: REAPER's native render action can successfully write
an entirely silent WAV when PCM media is offline. The MCP now brings project media
online before master, selection, stem, and analysis renders. A disposable project
with eight directly constructed kick items routed through a bus rendered at RMS
0.26193 online and exactly 0 offline; bringing it online restored the same samples.

The earlier intermittent missing-drums problem in larger Windows sessions is not
fully attributed to that condition. After restarting REAPER, a large
project copy with 1935 drum sources rendered correctly on repeated cold renders, after
mute/unmute, after the online action, and after playback (identical drum RMS
0.06803). Those tests support the project construction but do not prove what put
the earlier session into its failing state.

The MCP does not automatically play or reload projects. Verify important parts in
the actual full export: file validity, no clipping, and `check_project` success do
not prove a complete audible mix. Missing files, intentionally offline FX, and
plugin-specific initialization problems are not repaired by bringing media online.

### Live regression check

`python scripts/smoke_live.py --output /path/to/test-output --sample /path/to/kick.wav`
opens a disposable REAPER tab, tests MIDI at a nonzero timeline position, Save As,
copy, marker names, parameter batches, stems followed by a full render, and measures
separate synth/drum windows. Media is deliberately set offline before the stems
and again before the full mix to regress silent exports. It restores the original project tab in `finally`.
Run only when REAPER is available and no other actor is editing it. Artifacts and
the machine-readable result remain in the supplied output directory.

After updating an editable installation, restart/reconnect the MCP server so it
reloads its modules and advertises the new schemas; REAPER itself need not restart.

### Mastering
`apply_mastering_chain` `apply_limiter` `normalize_project`

### Analysis
`analyze_loudness` `analyze_dynamics` `analyze_frequency_spectrum` `analyze_stereo_field` `analyze_transients` `detect_clipping`

## Configuration

Configure process launch in your MCP client as shown above. Tool arguments and the
active REAPER project determine operational settings. The repository includes a
`config.py` helper for JSON defaults, but the current server/tool path does not call
it; editing such a JSON file does not configure the running tools.

## License

MIT. Original project and license attribution are retained; the fork's additions
are maintained by [MosrednA](https://github.com/MosrednA).
