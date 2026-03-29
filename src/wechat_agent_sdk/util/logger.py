"""Plugin logger — writes JSON lines to the main openclaw log file."""

import datetime
import json
import os
import socket
import platform
from typing import Optional


MAIN_LOG_DIR = "/tmp/openclaw"
SUBSYSTEM = "gateway/channels/openclaw-weixin"
RUNTIME = "python"
RUNTIME_VERSION = platform.python_version()
HOSTNAME = socket.gethostname() or "unknown"
PARENT_NAMES = ["openclaw"]

LEVEL_IDS = {
    "TRACE": 1,
    "DEBUG": 2,
    "INFO": 3,
    "WARN": 4,
    "ERROR": 5,
    "FATAL": 6,
}

DEFAULT_LOG_LEVEL = "INFO"


def _resolve_min_level() -> int:
    env = os.environ.get("OPENCLAW_LOG_LEVEL", "").upper()
    if env and env in LEVEL_IDS:
        return LEVEL_IDS[env]
    return LEVEL_IDS[DEFAULT_LOG_LEVEL]


_min_level_id = _resolve_min_level()


def set_log_level(level: str) -> None:
    global _min_level_id
    upper = level.upper()
    if upper not in LEVEL_IDS:
        raise ValueError(f"Invalid log level: {level}. Valid levels: {', '.join(LEVEL_IDS.keys())}")
    _min_level_id = LEVEL_IDS[upper]


def _to_local_iso(now: datetime.datetime) -> str:
    offset_minutes = -now.utcoffset().total_seconds() / 60 if now.utcoffset() else 0
    sign = "+" if offset_minutes >= 0 else "-"
    abs_mins = abs(int(offset_minutes))
    off_str = f"{sign}{str(abs_mins // 60).zfill(2)}:{str(abs_mins % 60).zfill(2)}"
    local_now = now.replace(microsecond=0) + datetime.timedelta(minutes=offset_minutes)
    return local_now.isoformat().replace("+00:00", off_str)


def _local_date_key(now: datetime.datetime) -> str:
    return _to_local_iso(now)[:10]


def _resolve_main_log_path() -> str:
    date_key = _local_date_key(datetime.datetime.now())
    return os.path.join(MAIN_LOG_DIR, f"openclaw-{date_key}.log")


_log_dir_ensured = False


class Logger:
    def __init__(self, account_id: Optional[str] = None):
        self._account_id = account_id

    def _log(self, level: str, message: str) -> None:
        level_id = LEVEL_IDS.get(level, LEVEL_IDS["INFO"])
        if level_id < _min_level_id:
            return

        now = datetime.datetime.now()
        logger_name = f"{SUBSYSTEM}/{self._account_id}" if self._account_id else SUBSYSTEM
        prefixed_message = f"[{self._account_id}] {message}" if self._account_id else message

        entry = json.dumps({
            "0": logger_name,
            "1": prefixed_message,
            "_meta": {
                "runtime": RUNTIME,
                "runtimeVersion": RUNTIME_VERSION,
                "hostname": HOSTNAME,
                "name": logger_name,
                "parentNames": PARENT_NAMES,
                "date": now.isoformat(),
                "logLevelId": LEVEL_IDS.get(level, LEVEL_IDS["INFO"]),
                "logLevelName": level,
            },
            "time": _to_local_iso(now),
        })

        global _log_dir_ensured
        try:
            if not _log_dir_ensured:
                os.makedirs(MAIN_LOG_DIR, exist_ok=True)
                _log_dir_ensured = True
            log_path = _resolve_main_log_path()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass

    def info(self, message: str) -> None:
        self._log("INFO", message)

    def debug(self, message: str) -> None:
        self._log("DEBUG", message)

    def warn(self, message: str) -> None:
        self._log("WARN", message)

    def error(self, message: str) -> None:
        self._log("ERROR", message)

    def with_account(self, account_id: str) -> "Logger":
        return Logger(account_id)

    def get_log_file_path(self) -> str:
        return _resolve_main_log_path()

    def close(self) -> None:
        pass


logger = Logger()
