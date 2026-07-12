from pathlib import Path
from typing import Any

from app.services import instance_storage, server_runtime

_STORE_NAME = "config"


def default_mods_path(server_path: str, runtime: str | None = None) -> str:
    base = Path(server_path) / "Pal" / "Binaries"
    preferred = "Win64" if server_runtime.normalize(runtime) == server_runtime.WINDOWS_RUNTIME else "Linux"
    alternate = "Linux" if preferred == "Win64" else "Win64"
    preferred_path = base / preferred / "Mods"
    alternate_path = base / alternate / "Mods"
    return str(preferred_path if preferred_path.exists() or not alternate_path.exists() else alternate_path)

def _get_config(instance_id: str) -> dict[str, Any]:
    return instance_storage.load(instance_id, _STORE_NAME, {"modsPathOverride": None})


def get_mods_path_info(instance: dict[str, Any]) -> dict[str, Any]:
    override = _get_config(instance["id"]).get("modsPathOverride")
    if override:
        return {"path": override, "source": "override"}
    return {"path": default_mods_path(instance["serverPath"], instance.get("runtime")), "source": "derived"}


def get_mods_path(instance: dict[str, Any]) -> str | None:
    return get_mods_path_info(instance)["path"]


def set_mods_path_override(instance_id: str, path: str) -> None:
    instance_storage.save(instance_id, _STORE_NAME, {"modsPathOverride": path})


def clear_mods_path_override(instance_id: str) -> None:
    instance_storage.save(instance_id, _STORE_NAME, {"modsPathOverride": None})
