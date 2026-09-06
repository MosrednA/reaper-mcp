import logging

from mcp.server import MCPServer

logger = logging.getLogger("reaper_mcp.server")

mcp = MCPServer("reaper-mcp")
from reaper_mcp.serialized_tools import SerializedTools

registry = SerializedTools(mcp)

# Import each tool module's register_tools function and call it with the mcp instance.
# The imports must happen after mcp is created to avoid circular dependencies.
from reaper_mcp.analysis_tools import register_tools as _reg_analysis
from reaper_mcp.audio_tools import register_tools as _reg_audio
from reaper_mcp.fx_tools import register_tools as _reg_fx
from reaper_mcp.mastering_tools import register_tools as _reg_mastering
from reaper_mcp.midi_tools import register_tools as _reg_midi
from reaper_mcp.mixing_tools import register_tools as _reg_mixing
from reaper_mcp.project_tools import register_tools as _reg_project
from reaper_mcp.render_tools import register_tools as _reg_render
from reaper_mcp.track_tools import register_tools as _reg_track
from reaper_mcp.validation_tools import register_tools as _reg_validation

_reg_project(registry)
_reg_track(registry)
_reg_midi(registry)
_reg_fx(registry)
_reg_audio(registry)
_reg_mixing(registry)
_reg_render(registry)
_reg_mastering(registry)
_reg_analysis(registry)
_reg_validation(registry)
