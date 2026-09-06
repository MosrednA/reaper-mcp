import base64
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf
from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project
from reaper_mcp.track_state import get_track_solo_state, set_track_solo_state

logger = logging.getLogger("reaper_mcp.render_tools")

BOUNDS_ENTIRE_PROJECT = 1
BOUNDS_TIME_SELECTION = 2

# REAPER stores sink configurations as base64-encoded bytes whose first four
# bytes are the reversed output-format FourCC. The WAV suffix bytes select PCM
# bit depth and the standard WaveFormatExtensible header.
FORMAT_FOURCC = {
    "wav": b"evaw",
    "mp3": b"l3pm",
    "ogg": b"ggOv",
    "flac": b"calf",
}
WAV_BIT_DEPTH = {
    16: b"\x10\x00\x01",
    24: b"\x18\x00\x01",
    32: b"\x20\x00\x01",
}

_STRING_RENDER_KEYS = (
    "RENDER_FILE",
    "RENDER_PATTERN",
    "RENDER_FORMAT",
    "RENDER_FORMAT2",
)
_NUMERIC_RENDER_KEYS = (
    "RENDER_SETTINGS",
    "RENDER_SRATE",
    "RENDER_CHANNELS",
    "RENDER_BOUNDSFLAG",
    "RENDER_ADDTOPROJ",
    "RENDER_NORMALIZE",
    "RENDER_DITHER",
)


@dataclass(frozen=True)
class _RenderSettingsSnapshot:
    strings: dict[str, str]
    numbers: dict[str, float]


def _read_project_string(key: str) -> str:
    result = RPR.GetSetProjectInfo_String(0, key, "", False)
    if isinstance(result, (list, tuple)):
        return str(result[3])
    return str(result)


def _capture_render_settings() -> _RenderSettingsSnapshot:
    return _RenderSettingsSnapshot(
        strings={key: _read_project_string(key) for key in _STRING_RENDER_KEYS},
        numbers={key: float(RPR.GetSetProjectInfo(0, key, 0.0, False))
                 for key in _NUMERIC_RENDER_KEYS},
    )


def _restore_render_settings(snapshot: _RenderSettingsSnapshot) -> None:
    for key, value in snapshot.strings.items():
        RPR.GetSetProjectInfo_String(0, key, value, True)
    for key, value in snapshot.numbers.items():
        RPR.GetSetProjectInfo(0, key, value, True)


def _sink_configuration(format_name: str, bit_depth: int) -> str:
    normalized_format = format_name.lower()
    if normalized_format not in FORMAT_FOURCC:
        raise ValueError(f"Unsupported render format: {format_name}")
    if bit_depth not in WAV_BIT_DEPTH:
        raise ValueError("bit_depth must be 16, 24, or 32")

    configuration = FORMAT_FOURCC[normalized_format]
    if normalized_format == "wav":
        configuration += WAV_BIT_DEPTH[bit_depth]
    return base64.b64encode(configuration).decode("ascii")


def _validated_output_path(output_path: str, format_name: str) -> Path:
    normalized_format = format_name.lower()
    if normalized_format not in FORMAT_FOURCC:
        raise ValueError(f"Unsupported render format: {format_name}")

    path = Path(output_path).expanduser().resolve()
    expected_suffix = f".{normalized_format}"
    if path.suffix.lower() != expected_suffix:
        path = path.with_suffix(expected_suffix)
    return path


def _set_render_settings(
    output_path: str,
    format_name: str,
    sample_rate: int,
    bit_depth: int,
    channels: int,
    bounds: int,
) -> Path:
    """Configure deterministic master-mix rendering and return the actual output path."""
    if not 8_000 <= sample_rate <= 384_000:
        raise ValueError("sample_rate must be between 8000 and 384000 Hz")
    if channels not in (1, 2):
        raise ValueError("channels must be 1 (mono) or 2 (stereo)")
    if bounds not in (BOUNDS_ENTIRE_PROJECT, BOUNDS_TIME_SELECTION):
        raise ValueError("Unsupported render bounds")

    path = _validated_output_path(output_path, format_name)
    path.parent.mkdir(parents=True, exist_ok=True)

    RPR.GetSetProjectInfo_String(0, "RENDER_FILE", str(path.parent), True)
    RPR.GetSetProjectInfo_String(0, "RENDER_PATTERN", path.stem, True)
    RPR.GetSetProjectInfo_String(
        0, "RENDER_FORMAT", _sink_configuration(format_name, bit_depth), True
    )
    RPR.GetSetProjectInfo_String(0, "RENDER_FORMAT2", "", True)

    # Render the master mix exactly as heard. Do not add the result back into the
    # project, normalize it, or dither it behind the caller's back.
    numeric_settings = {
        "RENDER_SETTINGS": 0.0,
        "RENDER_SRATE": float(sample_rate),
        "RENDER_CHANNELS": float(channels),
        "RENDER_BOUNDSFLAG": float(bounds),
        "RENDER_ADDTOPROJ": 0.0,
        "RENDER_NORMALIZE": 0.0,
        "RENDER_DITHER": 0.0,
    }
    for key, value in numeric_settings.items():
        RPR.GetSetProjectInfo(0, key, value, True)
    return path


def _render_file(
    output_path: str,
    format_name: str,
    sample_rate: int,
    bit_depth: int,
    channels: int,
    bounds: int,
) -> Path:
    project = get_project()
    if bounds == BOUNDS_ENTIRE_PROJECT and project.length <= 0.0:
        raise RuntimeError("The project has no content to render")

    snapshot = _capture_render_settings()
    path: Path | None = None
    destination = _validated_output_path(output_path, format_name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, staging = tempfile.mkstemp(
        prefix=".reaper-render-", suffix=destination.suffix, dir=destination.parent
    )
    os.close(handle)
    Path(staging).unlink()
    try:
        path = _set_render_settings(
            staging, format_name, sample_rate, bit_depth, channels, bounds
        )
        # These separate distant calls let REAPER process pending media/routing
        # updates. Never render inside an inside_reaper HOLD batch or reload a
        # user's project as an implicit workaround.
        _prepare_render()
        RPR.Main_OnCommand(41824, 0)  # File: Render project, using recent settings
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("Render command completed but output file was not created")
        info = sf.info(str(path))
        if info.frames <= 0 or info.samplerate != sample_rate or info.channels != channels:
            raise RuntimeError("Rendered audio is empty or has unexpected rate/channels")
    except Exception:
        if path is not None:
            path.unlink(missing_ok=True)
        raise
    finally:
        try:
            _restore_render_settings(snapshot)
        except Exception:
            Path(staging).unlink(missing_ok=True)
            raise
    os.replace(path, destination)
    return destination


def _prepare_render() -> None:
    if RPR.GetPlayState() & 4:
        raise RuntimeError("Stop recording before rendering")
    # Offline PCM sources produce valid but silent files even in native renders.
    # Bring project media online without starting playback or changing the mix.
    # This is a native REAPER action; SWS is not required.
    RPR.Main_OnCommand(40101, 0)  # Item: Set all media online
    RPR.TrackList_AdjustWindows(False)
    RPR.UpdateTimeline()
    RPR.UpdateArrange()


def render_to_temp_file(sample_rate: int = 48000) -> str:
    """Render the current project to a temporary WAV for analysis."""
    handle, temporary_path = tempfile.mkstemp(suffix=".wav")
    os.close(handle)
    Path(temporary_path).unlink(missing_ok=True)
    try:
        return str(
            _render_file(
                temporary_path,
                "wav",
                sample_rate,
                24,
                2,
                BOUNDS_ENTIRE_PROJECT,
            )
        )
    except Exception:
        Path(temporary_path).unlink(missing_ok=True)
        raise


def register_tools(mcp):

    @mcp.tool()
    def render_project(
        output_path: str,
        format: str = "wav",
        sample_rate: int = 48000,
        bit_depth: int = 24,
        channels: int = 2,
    ) -> dict:
        """
        Render the entire project to a file.
        format: wav, flac, mp3 (requires LAME), ogg.
        sample_rate: e.g. 44100, 48000, 96000.
        bit_depth: 16, 24, or 32 (WAV only; ignored for mp3/ogg/flac).
        channels: 1 (mono) or 2 (stereo).
        """
        try:
            path = _render_file(
                output_path,
                format,
                sample_rate,
                bit_depth,
                channels,
                BOUNDS_ENTIRE_PROJECT,
            )
            return {
                "success": True,
                "output_path": str(path),
                "format": format.lower(),
                "sample_rate": sample_rate,
                "bit_depth": bit_depth,
                "channels": channels,
                "file_size_bytes": path.stat().st_size,
            }
        except Exception as e:
            logger.exception("render_project failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def render_time_selection(
        output_path: str,
        start: float,
        end: float,
        format: str = "wav",
        sample_rate: int = 48000,
        bit_depth: int = 24,
        channels: int = 2,
    ) -> dict:
        """Render a specific time range of the project to a file."""
        project = None
        original_selection = None
        try:
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
                raise ValueError("end must be greater than start")
            project = get_project()
            selection = project.time_selection
            original_selection = (float(selection.start), float(selection.end))
            project.time_selection = (start, end)
            path = _render_file(
                output_path,
                format,
                sample_rate,
                bit_depth,
                channels,
                BOUNDS_TIME_SELECTION,
            )
            return {
                "success": True,
                "output_path": str(path),
                "start": start,
                "end": end,
                "format": format.lower(),
                "file_size_bytes": path.stat().st_size,
            }
        except Exception as e:
            logger.exception("render_time_selection failed")
            return {"success": False, "error": str(e)}
        finally:
            if project is not None and original_selection is not None:
                project.time_selection = original_selection

    @mcp.tool()
    def render_stems(
        output_directory: str,
        track_indices: list[int] | None = None,
        format: str = "wav",
        sample_rate: int = 48000,
        bit_depth: int = 24,
    ) -> dict:
        """
        Render each track as a separate stem file by soloing each track individually.
        track_indices: list of track indices, or null to render all tracks.
        Files are named after the track names in the output directory.
        """
        original_solo_states = None
        project = None
        try:
            directory = Path(output_directory).expanduser().resolve()
            directory.mkdir(parents=True, exist_ok=True)
            project = get_project()
            original_solo_states = [
                get_track_solo_state(project.tracks[i]) for i in range(project.n_tracks)
            ]
            indices = track_indices if track_indices is not None else list(range(project.n_tracks))
            if len(set(indices)) != len(indices) or any(
                not 0 <= idx < project.n_tracks for idx in indices
            ):
                raise ValueError("Stem indices must be unique and in range")
            rendered = []

            for idx in indices:
                if not 0 <= idx < project.n_tracks:
                    raise IndexError(f"Track index out of range: {idx}")
                track = project.tracks[idx]
                track_name = track.name or f"Track_{idx}"
                for j in range(project.n_tracks):
                    set_track_solo_state(project.tracks[j], 1 if j == idx else 0)
                safe_name = "".join(
                    c if c.isalnum() or c in " _-" else "_" for c in track_name
                )
                path = _render_file(
                    str(directory / f"{idx + 1:02d}-{safe_name}.{format.lower()}"),
                    format,
                    sample_rate,
                    bit_depth,
                    2,
                    BOUNDS_ENTIRE_PROJECT,
                )
                rendered.append({
                    "track_index": idx,
                    "track_name": track_name,
                    "output_path": str(path),
                    "exists": path.exists(),
                })

            return {
                "success": True,
                "output_directory": str(directory),
                "stems": rendered,
            }
        except Exception as e:
            logger.exception("render_stems failed")
            return {"success": False, "error": str(e)}
        finally:
            if project is not None and original_solo_states is not None:
                for track, solo_state in zip(project.tracks, original_solo_states):
                    set_track_solo_state(track, solo_state)
