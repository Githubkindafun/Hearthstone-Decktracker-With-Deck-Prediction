from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Iterator, Optional

TIMESTAMP_PATTERN = re.compile(r"^D\s+(?P<ts>\d{2}:\d{2}:\d{2}\.\d+)")


def parse_timestamp(line: str) -> Optional[float]:
    match = TIMESTAMP_PATTERN.match(line)
    if not match:
        return None
    hh, mm, ss = match.group("ts").split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def wait_for_logs(
    log_dir: Path,
    zone_name: str = "Zone.log",
    power_name: str = "Power.log",
    poll_interval: float = 0.25,
) -> tuple[Path, Path]:
    zone_log = log_dir / zone_name
    power_log = log_dir / power_name
    while not power_log.exists():
        time.sleep(poll_interval)
    while not zone_log.exists():
        time.sleep(poll_interval)
    return zone_log, power_log


def iter_merged_logs(
    zone_log: Path,
    power_log: Path,
    poll_interval: float = 0.05,
) -> Iterator[tuple[str, str]]:
    with open(zone_log, "r", encoding="utf-8") as zone_handle, open(power_log, "r", encoding="utf-8") as power_handle:
        zone_buffer: Optional[tuple[Optional[float], str]] = None
        power_buffer: Optional[tuple[Optional[float], str]] = None

        while True:
            if zone_buffer is None:
                zline = zone_handle.readline()
                if zline:
                    zone_buffer = (parse_timestamp(zline), zline)

            if power_buffer is None:
                pline = power_handle.readline()
                if pline:
                    power_buffer = (parse_timestamp(pline), pline)

            if zone_buffer is None and power_buffer is None:
                time.sleep(poll_interval)
                continue

            next_source = None
            if zone_buffer and power_buffer:
                zts, _ = zone_buffer
                pts, _ = power_buffer
                if pts is None and zts is None:
                    next_source = "power"
                elif pts is None:
                    next_source = "zone"
                elif zts is None:
                    next_source = "power"
                elif pts <= zts:
                    next_source = "power"
                else:
                    next_source = "zone"
            elif power_buffer:
                next_source = "power"
            else:
                next_source = "zone"

            if next_source == "power":
                _, pline = power_buffer
                power_buffer = None
                yield "power", pline
            else:
                _, zline = zone_buffer
                zone_buffer = None
                yield "zone", zline


def iter_player_log(
    player_log: Path,
    poll_interval: float = 0.05,
    emit_catch_up: bool = False,
) -> Iterator[tuple[str, Optional[str]]]:
    caught_up = False
    with open(player_log, "r", encoding="utf-8") as handle:
        while True:
            line = handle.readline()
            if line:
                if "[Power]" in line:
                    yield "power", line
                elif "[Zone]" in line:
                    yield "zone", line
                continue

            if emit_catch_up and not caught_up:
                caught_up = True
                yield "catch_up", None
            time.sleep(poll_interval)
