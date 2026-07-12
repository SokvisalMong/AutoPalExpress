"""Per-instance Palworld server runtime selection.

The backend host OS is not the same thing as the server binary's runtime:
Linux hosts can run the Windows server through Wine, and the two binaries have
incompatible world/player UUIDs. Keep runtime handling centralized so paths,
SteamCMD, and process launch all make the same decision.
"""

from __future__ import annotations

import shutil
import sys
from typing import Any, Literal

ServerRuntime = Literal["linux", "windows"]
LINUX_RUNTIME: ServerRuntime = "linux"
WINDOWS_RUNTIME: ServerRuntime = "windows"


def normalize(value: Any) -> ServerRuntime:
    return WINDOWS_RUNTIME if str(value or "").lower() == WINDOWS_RUNTIME else LINUX_RUNTIME


def is_windows(instance_or_runtime: dict[str, Any] | str | None) -> bool:
    if isinstance(instance_or_runtime, dict):
        return normalize(instance_or_runtime.get("runtime")) == WINDOWS_RUNTIME
    return normalize(instance_or_runtime) == WINDOWS_RUNTIME


def host_can_run(runtime: ServerRuntime) -> bool:
    if runtime == LINUX_RUNTIME:
        return sys.platform != "win32"
    return sys.platform == "win32" or shutil.which("wine") is not None


def wine_command() -> str:
    command = shutil.which("wine")
    if not command:
        raise RuntimeError(
            "Windows Binary (Mods Supported) requires Wine on Linux. Install a 64-bit Wine prefix, winbind, "
            "and the VC++ 2015-2022 runtime before deploying it."
        )
    return command


def display_name(runtime: Any) -> str:
    return "Windows Binary (Mods Supported)" if normalize(runtime) == WINDOWS_RUNTIME else "Linux (Mods Unsupported)"
