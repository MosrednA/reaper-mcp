import logging

import reapy
from pydantic import BaseModel, ConfigDict, Field
from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project

logger = logging.getLogger("reaper_mcp.fx_tools")


class ParameterChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    param_index: int = Field(ge=0, strict=True)
    value: float = Field(ge=0, le=1, allow_inf_nan=False)


def register_tools(mcp):

    @mcp.tool()
    def add_fx(track_index: int, fx_name: str) -> dict:
        """
        Add an FX plugin to a track. Works for both instruments (VSTi) and effects (VST/AU).
        Use the exact plugin name as shown in REAPER's FX browser.
        Built-in Cockos plugins: ReaEQ, ReaComp, ReaDelay, ReaVerb, ReaLimit, ReaSynth,
        ReaSamplOmatic5000, ReaTune, ReaGate, ReaFIR, ReaXcomp.
        """
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx = track.add_fx(fx_name)
            return {
                "success": True,
                "fx_index": fx.index,
                "name": fx.name,
                "n_params": fx.n_params,
                "track_index": track_index,
            }
        except Exception as e:
            logger.exception("add_fx failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def remove_fx(track_index: int, fx_index: int) -> dict:
        """Remove an FX plugin from a track by its index."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx_name = track.fxs[fx_index].name
            RPR.TrackFX_Delete(track.id, fx_index)
            return {"success": True, "track_index": track_index, "removed": fx_name}
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_fx_parameter(
        track_index: int, fx_index: int, param_index: int, value: float
    ) -> dict:
        """
        Set a normalized parameter value (0.0–1.0) on an FX plugin.
        Use get_fx_parameters to discover available parameters and their indices.
        """
        try:
            change = ParameterChange(param_index=param_index, value=value)
            if track_index < 0 or fx_index < 0:
                raise ValueError("Indices must be nonnegative")
            project = get_project()
            track = project.tracks[track_index]
            fx = track.fxs[fx_index]
            param = fx.params[param_index]
            if not RPR.TrackFX_SetParamNormalized(
                track.id, fx_index, change.param_index, change.value
            ):
                raise RuntimeError("REAPER rejected the parameter value")
            param_name = param.name
            return {
                "success": True,
                "track_index": track_index,
                "fx_index": fx_index,
                "param_index": param_index,
                "param_name": param_name,
                "value": float(param.normalized),
                "requested_value": value,
            }
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_fx_parameters(
        track_index: int, fx_index: int, offset: int = 0, limit: int = 128,
        name_filter: str = "", include_midi_cc: bool = False,
    ) -> dict:
        """Read a bounded parameter page. offset/next_offset are raw plugin indices.

        MIDI CC parameters are excluded by default. name_filter is a case-insensitive
        substring. Read values only for matches; limit is at most 256.
        """
        try:
            if track_index < 0 or fx_index < 0 or offset < 0 or not 1 <= limit <= 256:
                raise ValueError("Nonnegative indices/offset and limit 1–256 required")
            project = get_project()
            track = project.tracks[track_index]
            fx = track.fxs[fx_index]
            params = []
            i = min(offset, fx.n_params)
            with reapy.inside_reaper():
                while i < fx.n_params and len(params) < limit:
                    param = fx.params[i]
                    name = param.name
                    index = i
                    i += 1
                    if not include_midi_cc and name.casefold().startswith("midi cc"):
                        continue
                    if name_filter.casefold() not in name.casefold():
                        continue
                    params.append({"index": index, "name": name,
                                   "normalized_value": float(param.normalized),
                                   "formatted_value": param.formatted})
            return {
                "success": True,
                "track_index": track_index,
                "fx_index": fx_index,
                "fx_name": fx.name,
                "parameters": params,
                "total_parameters": fx.n_params,
                "next_offset": i if i < fx.n_params else None,
            }
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_fx_parameters(
        track_index: int, fx_index: int, changes: list[ParameterChange]
    ) -> dict:
        """Set a validated batch of normalized parameters with readback and rollback.

        Returned values are actual plugin values, which may be quantized.
        """
        try:
            changes = [ParameterChange.model_validate(c) for c in changes]
            if track_index < 0 or fx_index < 0 or not 1 <= len(changes) <= 256:
                raise ValueError("Nonnegative indices and 1–256 changes required")
            if len({c.param_index for c in changes}) != len(changes):
                raise ValueError("Duplicate parameter indices")
            track = get_project().tracks[track_index]
            fx = track.fxs[fx_index]
            if any(c.param_index >= fx.n_params for c in changes):
                raise ValueError("Parameter index out of range")
            with reapy.inside_reaper():
                before = {c.param_index: float(fx.params[c.param_index].normalized)
                          for c in changes}
                try:
                    result = []
                    for c in changes:
                        if not RPR.TrackFX_SetParamNormalized(
                            track.id, fx_index, c.param_index, c.value
                        ):
                            raise RuntimeError(f"REAPER rejected parameter {c.param_index}")
                        result.append({"index": c.param_index,
                                       "name": fx.params[c.param_index].name,
                                       "requested_value": c.value,
                                       "value": float(fx.params[c.param_index].normalized)})
                except Exception:
                    for index, value in before.items():
                        if not RPR.TrackFX_SetParamNormalized(track.id, fx_index, index, value):
                            raise RuntimeError("Parameter update failed; rollback also failed")
                    raise
            return {"success": True, "parameters": result}
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def list_track_fx(track_index: int) -> dict:
        """List all FX plugins on a track."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx_list = []
            for i in range(track.n_fxs):
                fx = track.fxs[i]
                fx_list.append({
                    "index": i,
                    "name": fx.name,
                    "enabled": fx.is_enabled,
                    "n_params": fx.n_params,
                })
            return {"success": True, "track_index": track_index, "fx": fx_list}
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def bypass_fx(track_index: int, fx_index: int, bypassed: bool) -> dict:
        """Enable or bypass (disable) an FX plugin on a track."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx = track.fxs[fx_index]
            fx.is_enabled = not bypassed
            return {
                "success": True,
                "track_index": track_index,
                "fx_index": fx_index,
                "fx_name": fx.name,
                "bypassed": bypassed,
            }
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def load_fx_preset(track_index: int, fx_index: int, preset_name: str) -> dict:
        """Load a saved preset by name for an FX plugin."""
        try:
            project = get_project()
            track = project.tracks[track_index]
            fx = track.fxs[fx_index]
            fx.preset = preset_name
            return {
                "success": True,
                "track_index": track_index,
                "fx_index": fx_index,
                "fx_name": fx.name,
                "preset": fx.preset,
            }
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}
