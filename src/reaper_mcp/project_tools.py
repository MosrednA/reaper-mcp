import logging
import os
import time
from pathlib import Path

from reapy import reascript_api as RPR

from reaper_mcp.connection import get_project
from reaper_mcp.project_state import (
    current_project_file,
    get_project_time_signature,
    project_markers,
    set_project_time_signature,
    write_project,
)

logger = logging.getLogger("reaper_mcp.project_tools")


def register_tools(mcp):

    @mcp.tool()
    def create_project(tempo: float = 120.0, time_signature: str = "4/4", name: str = "") -> dict:
        """Create a new REAPER project with the given tempo and time signature."""
        try:
            RPR.Main_OnCommand(41929, 0)  # File: New project
            project = get_project()
            project.bpm = tempo
            if time_signature:
                num, denom = map(int, time_signature.split("/"))
                set_project_time_signature(project, num, denom)
            return {
                "success": True,
                "name": name or f"New Project {time.strftime('%Y-%m-%d %H-%M-%S')}",
                "tempo": project.bpm,
                "time_signature": time_signature,
            }
        except Exception as e:
            logger.exception("create_project failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def save_project(project_path: str = "") -> dict:
        """Save in place, or Save As to project_path and make that the active filename.

        Untitled projects require a path. Use save_project_copy for a snapshot.
        """
        try:
            project = get_project()
            filename = project_path or current_project_file()
            if not filename:
                raise ValueError("Untitled project: provide project_path")
            path = Path(filename).expanduser().resolve()
            if path.suffix.lower() != ".rpp":
                raise ValueError("project_path must end in .rpp")
            path.parent.mkdir(parents=True, exist_ok=True)
            write_project(project.id, path, 8)
            active = current_project_file()
            if not active or Path(active).resolve() != path:
                raise RuntimeError("Project written, but active filename did not change")
            return {"success": True, "project_path": str(path), "active_project_path": active}
        except Exception as e:
            logger.exception("save_project failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def save_project_copy(project_path: str) -> dict:
        """Write an RPP snapshot without changing the active project's filename."""
        try:
            project = get_project()
            path = Path(project_path).expanduser().resolve()
            if not project_path or path.suffix.lower() != ".rpp":
                raise ValueError("Provide a .rpp project_path")
            active = current_project_file()
            if active and Path(active).resolve() == path:
                raise ValueError("Use save_project to save the active file")
            path.parent.mkdir(parents=True, exist_ok=True)
            write_project(project.id, path, 0)
            if current_project_file() != active:
                raise RuntimeError("Copy written, but active project unexpectedly changed")
            return {"success": True, "project_path": str(path), "active_project_path": active}
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def load_project(project_path: str) -> dict:
        """Load a REAPER project (.rpp) from the given file path."""
        try:
            if not os.path.exists(project_path):
                return {"success": False, "error": f"File not found: {project_path}"}
            RPR.Main_openProject(project_path)
            project = get_project()
            return {
                "success": True,
                "name": project.name,
                "tempo": project.bpm,
                "time_signature": _format_time_signature(project),
                "project_path": project_path,
            }
        except Exception as e:
            logger.exception("load_project failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def get_project_info() -> dict:
        """Get information about the current project: name, path, tempo, tracks, length."""
        try:
            project = get_project()
            markers, regions = project_markers(project.id)
            filename = current_project_file()

            return {
                "success": True,
                "name": project.name,
                "path": str(Path(filename).parent) if filename else "",
                "project_path": filename,
                "media_path": project.path,
                "tempo": project.bpm,
                "time_signature": _format_time_signature(project),
                "length": project.length,
                "track_count": project.n_tracks,
                "markers": markers,
                "regions": regions,
            }
        except Exception as e:
            logger.exception("get_project_info failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_tempo(bpm: float) -> dict:
        """Set the project tempo in BPM."""
        try:
            project = get_project()
            project.bpm = bpm
            return {"success": True, "tempo": project.bpm}
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}

    @mcp.tool()
    def set_time_signature(numerator: int, denominator: int) -> dict:
        """Set the project time signature, e.g. 4/4, 3/4, 6/8."""
        try:
            project = get_project()
            applied_numerator, applied_denominator = set_project_time_signature(
                project, numerator, denominator
            )
            return {
                "success": True,
                "time_signature": f"{applied_numerator}/{applied_denominator}",
            }
        except Exception as e:
            logger.exception("REAPER operation failed")
            return {"success": False, "error": str(e)}


def _format_time_signature(project) -> str:
    numerator, denominator = get_project_time_signature(project)
    return f"{numerator}/{denominator}"
