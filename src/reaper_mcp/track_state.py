import math
from typing import Protocol


class TrackInfo(Protocol):
    def get_info_value(self, name: str) -> float: ...

    def set_info_value(self, name: str, value: float) -> None: ...


class TakeInfo(Protocol):
    name: str


class ItemInfo(Protocol):
    n_takes: int
    active_take: TakeInfo

MIN_VOLUME_DB = -150.0


def linear_to_db(value: float) -> float:
    """Convert a REAPER linear gain value to decibels."""
    if value <= 0.0:
        return MIN_VOLUME_DB
    return 20.0 * math.log10(value)


def db_to_linear(value_db: float) -> float:
    """Convert decibels to the linear gain value expected by REAPER."""
    if not math.isfinite(value_db):
        raise ValueError("volume_db must be finite")
    if value_db <= MIN_VOLUME_DB:
        return 0.0
    return 10.0 ** (value_db / 20.0)


def get_track_volume_db(track: TrackInfo) -> float:
    return linear_to_db(float(track.get_info_value("D_VOL")))


def set_track_volume_db(track: TrackInfo, value_db: float) -> float:
    track.set_info_value("D_VOL", db_to_linear(value_db))
    return get_track_volume_db(track)


def get_track_pan(track: TrackInfo) -> float:
    return float(track.get_info_value("D_PAN"))


def set_track_pan_value(track: TrackInfo, pan: float) -> float:
    if not math.isfinite(pan) or not -1.0 <= pan <= 1.0:
        raise ValueError("pan must be finite and between -1.0 and 1.0")
    track.set_info_value("D_PAN", pan)
    return get_track_pan(track)


def get_track_muted(track: TrackInfo) -> bool:
    return bool(track.get_info_value("B_MUTE"))


def set_track_muted_value(track: TrackInfo, muted: bool) -> bool:
    track.set_info_value("B_MUTE", 1.0 if muted else 0.0)
    return get_track_muted(track)


def get_track_soloed(track: TrackInfo) -> bool:
    return bool(track.get_info_value("I_SOLO"))


def set_track_soloed_value(track: TrackInfo, soloed: bool) -> bool:
    track.set_info_value("I_SOLO", 1.0 if soloed else 0.0)
    return get_track_soloed(track)


def get_item_name(item: ItemInfo) -> str:
    """Return REAPER's visible item name, which is owned by the active take."""
    if item.n_takes <= 0:
        return ""
    return item.active_take.name
