import math
from typing import Protocol


class MediaInfo(Protocol):
    def get_info_value(self, name: str) -> float: ...

    def set_info_value(self, name: str, value: float) -> None: ...


def _require_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def get_item_fade_in(item: MediaInfo) -> float:
    return float(item.get_info_value("D_FADEINLEN"))


def set_item_fade_in(item: MediaInfo, seconds: float) -> float:
    _require_finite(seconds, "fade_in")
    if seconds < 0.0:
        raise ValueError("fade_in must not be negative")
    item.set_info_value("D_FADEINLEN", seconds)
    return get_item_fade_in(item)


def get_item_fade_out(item: MediaInfo) -> float:
    return float(item.get_info_value("D_FADEOUTLEN"))


def set_item_fade_out(item: MediaInfo, seconds: float) -> float:
    _require_finite(seconds, "fade_out")
    if seconds < 0.0:
        raise ValueError("fade_out must not be negative")
    item.set_info_value("D_FADEOUTLEN", seconds)
    return get_item_fade_out(item)


def get_take_start_offset(take: MediaInfo) -> float:
    return float(take.get_info_value("D_STARTOFFS"))


def set_take_start_offset(take: MediaInfo, seconds: float) -> float:
    _require_finite(seconds, "start_offset")
    take.set_info_value("D_STARTOFFS", seconds)
    return get_take_start_offset(take)


def get_take_pitch(take: MediaInfo) -> float:
    return float(take.get_info_value("D_PITCH"))


def set_take_pitch(take: MediaInfo, semitones: float) -> float:
    _require_finite(semitones, "semitones")
    take.set_info_value("D_PITCH", semitones)
    return get_take_pitch(take)


def get_take_playback_rate(take: MediaInfo) -> float:
    return float(take.get_info_value("D_PLAYRATE"))


def set_take_playback_rate(take: MediaInfo, rate: float) -> float:
    _require_finite(rate, "rate")
    if rate <= 0.0:
        raise ValueError("rate must be greater than zero")
    take.set_info_value("D_PLAYRATE", rate)
    return get_take_playback_rate(take)
