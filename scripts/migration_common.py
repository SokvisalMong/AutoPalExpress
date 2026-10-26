"""Docker discovery and safe archive I/O for the two migration commands."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


class MigrationError(Exception):
    """An actionable migration failure, without an internal traceback."""


def docker(*args: str, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["docker", *args], cwd=cwd, text=True, capture_output=True, check=False
        )
    except FileNotFoundError as exc:
        raise MigrationError("Docker CLI is not installed or is not on PATH.") from exc
    if result.returncode:
        raise MigrationError(result.stderr.strip() or f"docker {' '.join(args)} failed.")
    return result.stdout


def compose(root: Path, *args: str) -> str:
    options = ["-f", "compose.migration.json"] if (root / "compose.migration.json").is_file() else []
    return docker("compose", *options, *args, cwd=root)


def _check_compose(config: dict[str, Any], root: Path) -> None:
    if set(config.get("services", {})) != {"autopalexpress"}:
        raise MigrationError("This backup supports the single autopalexpress Compose service only.")
    if config.get("configs") or config.get("secrets"):
        raise MigrationError("Compose configs/secrets must be moved into project files or mounts before backup.")
    if any(network.get("external") for network in config.get("networks", {}).values()):
        raise MigrationError("External Docker networks are not portable; use a Compose-managed network.")
    service = config["services"]["autopalexpress"]
    if any(service.get(key) for key in ("volumes_from", "devices", "device_cgroup_rules", "tmpfs",
                                        "develop", "credential_spec", "use_api_socket")):
        raise MigrationError("Host devices, tmpfs, develop, credential_spec, and inherited mounts are not portable.")
    for key in ("env_file", "label_file"):
        references = service.get(key, [])
        if isinstance(references, str):
            references = [references]
        for reference in references:
            value = reference.get("path") if isinstance(reference, dict) else reference
            if not isinstance(value, str) or not (root / value).resolve().is_relative_to(root):
                raise MigrationError(f"{key} references must stay inside the project root.")
    build = service.get("build")
    if not isinstance(build, dict) or Path(build.get("context", "")).resolve() != root:
        raise MigrationError("The Compose build context must be this AutoPalExpress project root.")
    if any(build.get(key) for key in ("additional_contexts", "secrets", "ssh", "cache_from", "cache_to")):
        raise MigrationError("External build contexts, secrets, SSH mounts, and build caches are not portable.")
    dockerfile = Path(build.get("dockerfile", "Dockerfile"))
    if not (root / dockerfile).resolve().is_relative_to(root):
        raise MigrationError("The Dockerfile must be inside the project root.")


def _unescape_compose_dollars(value: Any) -> Any:
    # `compose config` re-escapes literal dollars for reloading its output.
    # The manifest stores runtime values; restore escapes exactly once.
    if isinstance(value, str):
        return value.replace("$$", "$")
    if isinstance(value, list):
        return [_unescape_compose_dollars(item) for item in value]
    if isinstance(value, dict):
        return {key: _unescape_compose_dollars(item) for key, item in value.items()}
    return value


def load_deployment(root: Path, container: str | None) -> tuple[dict, dict, list[dict]]:
    config = _unescape_compose_dollars(json.loads(compose(root, "config", "--format", "json")))
    _check_compose(config, root)
    if not container:
        ids = compose(root, "ps", "--all", "--quiet", "autopalexpress").split()
        if len(ids) != 1:
            raise MigrationError("Expected one existing AutoPalExpress container; use --container NAME for Portainer.")
        container = ids[0]
    inspected = json.loads(docker("inspect", container))
    if len(inspected) != 1:
        raise MigrationError("Expected exactly one container.")
    info = inspected[0]
    state = info["State"]
    if state.get("Paused") or state.get("Restarting") or state.get("Dead"):
        raise MigrationError("Unpause or repair the container before taking a backup.")
    service = config["services"]["autopalexpress"]
    configured = {volume["target"]: volume for volume in service.get("volumes", [])}
    actual = info.get("Mounts", [])
    if len(configured) != len(service.get("volumes", [])) or set(configured) != {m["Destination"] for m in actual}:
        raise MigrationError("Compose mount targets differ from the actual container; use its matching Compose files.")
    if len(actual) > 1000:
        raise MigrationError("Too many persistent mounts for this backup format.")
    mounts = []
    for index, mount in enumerate(sorted(actual, key=lambda item: item["Destination"])):
        target = mount["Destination"]
        if mount["Type"] not in {"bind", "volume"} or not target.startswith("/") or target == "/":
            raise MigrationError(f"Unsupported persistent mount: {target} ({mount['Type']}).")
        if posixpath.normpath(target) != target:
            raise MigrationError(f"Noncanonical container mount path: {target}")
        configured[target]["read_only"] = not mount["RW"]
        mounts.append({
            "id": f"{index:03d}",
            "target": target,
            "source": mount["Source"],
            "readOnly": not mount["RW"],
        })
    if not mounts:
        raise MigrationError("No persistent Docker mounts were found; refusing an incomplete backup.")
    # Portainer and exported shell variables may differ from .env. Snapshot the
    # live container's effective settings rather than silently reverting them.
    service["environment"] = dict(item.split("=", 1) for item in info["Config"].get("Env", []) if "=" in item)
    image = json.loads(docker("image", "inspect", info["Image"]))[0]
    service["platform"] = f"{image['Os']}/{image['Architecture']}"
    bindings = info["HostConfig"].get("PortBindings") or {}
    service["ports"] = [
        {"target": int(port.split("/")[0]), "protocol": port.split("/")[1],
         "published": binding["HostPort"], **({"host_ip": binding["HostIp"]} if binding["HostIp"] else {})}
        for port, entries in bindings.items() for binding in (entries or [])
    ]
    if info["HostConfig"].get("ShmSize"):
        service["shm_size"] = info["HostConfig"]["ShmSize"]
    return config, info, mounts


def _name(name: str) -> str:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise MigrationError(f"Unsafe archive path: {name!r}")
    return str(path)


def _scope(name: str) -> str:
    parts = PurePosixPath(name).parts
    if parts[0] == "project":
        return "project"
    if parts[0] == "mounts" and len(parts) >= 2:
        return f"mounts/{parts[1]}"
    return name


def _check_member(member: tarfile.TarInfo) -> None:
    name = _name(member.name)
    if name == ".":
        raise MigrationError("Unexpected archive root entry.")
    if not (member.isdir() or member.isreg() or member.issym() or member.islnk()):
        raise MigrationError(f"Unsupported archive file type: {name}")
    if member.issym() or member.islnk():
        if not member.linkname or member.linkname.startswith("/") or "\\" in member.linkname:
            raise MigrationError(f"Unsafe archive link: {name} -> {member.linkname}")
        target = posixpath.normpath(
            posixpath.join(posixpath.dirname(name), member.linkname) if member.issym() else member.linkname
        )
        scope = _scope(name)
        if target != scope and not target.startswith(scope + "/"):
            raise MigrationError(f"Archive link escapes its payload: {name} -> {member.linkname}")


def add_project(archive: tarfile.TarFile, root: Path, excluded: list[Path]) -> None:
    exclusions = [root / "backups", root / ".autopal-migration", *excluded]
    exclusions = [path.absolute() for path in exclusions]

    def include(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
        relative = PurePosixPath(member.name).relative_to("project")
        source = root.joinpath(*relative.parts)
        if any(source == path or source.is_relative_to(path) for path in exclusions):
            return None
        _check_member(member)
        return member

    archive.add(root, arcname="project", recursive=True, filter=include)


def add_mount(archive: tarfile.TarFile, container_id: str, mount: dict) -> None:
    prefix = f"mounts/{mount['id']}"
    # docker cp archives a single root entry, then its descendants. No host
    # access to root-owned bind mounts or Docker's volume directory is needed.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            ["docker", "cp", f"{container_id}:{mount['target']}", "-"],
            stdout=subprocess.PIPE, stderr=errors,
        )
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as incoming:
                first = incoming.next()
                if first is None or not (first.isdir() or first.isreg()):
                    raise MigrationError(f"Mount is not a directory or regular file: {mount['target']}")
                source_root = _name(first.name)
                mount["kind"] = "directory" if first.isdir() else "file"

                def relocate(name: str) -> str:
                    name = _name(name)
                    if name == source_root:
                        return prefix
                    if source_root == ".":
                        return f"{prefix}/{name}"
                    if not name.startswith(source_root + "/"):
                        raise MigrationError(f"Unexpected docker cp path: {name}")
                    return prefix + name[len(source_root):]

                def append(member: tarfile.TarInfo) -> None:
                    saved = copy.copy(member)
                    saved.name = relocate(member.name)
                    if saved.islnk():
                        saved.linkname = relocate(member.linkname)
                    _check_member(saved)
                    archive.addfile(saved, incoming.extractfile(member) if member.isreg() else None)

                append(first)
                for member in incoming:
                    # TarFile iteration starts at the already-read first entry.
                    if member is first:
                        continue
                    append(member)
            process.stdout.close()
            if process.wait():
                errors.seek(0)
                raise MigrationError(errors.read().decode(errors="replace").strip() or "docker cp failed.")
        except BaseException:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
            process.wait()
            raise


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksum(path: Path) -> Path:
    sidecar = path.with_name(path.name + ".sha256")
    descriptor = os.open(sidecar, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(f"{_digest(path)}  {path.name}\n")
    return sidecar


def _validate_manifest(archive: tarfile.TarFile, entries: dict[str, tarfile.TarInfo]) -> dict:
    member = entries.get("manifest.json")
    if member is None or not member.isreg() or member.size > 8 * 1024 * 1024:
        raise MigrationError("Missing or invalid backup manifest.")
    with archive.extractfile(member) as source:
        manifest = json.load(source)
    if (not isinstance(manifest, dict) or manifest.get("format") != "autopalexpress-full-backup"
            or type(manifest.get("version")) is not int or manifest["version"] != 1):
        raise MigrationError("Unsupported AutoPalExpress backup format/version.")
    if not isinstance(manifest.get("compose"), dict) or not isinstance(manifest.get("mounts"), list) or not manifest["mounts"]:
        raise MigrationError("Backup manifest has no Compose configuration or mounts.")
    ids, targets = set(), set()
    for mount in manifest["mounts"]:
        if (not isinstance(mount, dict) or not isinstance(mount.get("id"), str)
                or not re.fullmatch(r"[0-9]{3}", mount["id"])):
            raise MigrationError("Invalid mount identifier in backup manifest.")
        target = mount.get("target")
        if (not isinstance(target, str) or not target.startswith("/") or target.startswith("//")
                or "\x00" in target or "\\" in target or target == "/" or posixpath.normpath(target) != target):
            raise MigrationError("Invalid mount target in backup manifest.")
        if mount["id"] in ids or target in targets or type(mount.get("readOnly")) is not bool:
            raise MigrationError("Duplicate mount or invalid readOnly value in backup manifest.")
        ids.add(mount["id"])
        targets.add(target)
        payload = entries.get(f"mounts/{mount['id']}")
        kind = mount.get("kind")
        if payload is None or not ((kind == "directory" and payload.isdir()) or (kind == "file" and payload.isreg())):
            raise MigrationError(f"Missing or invalid mount payload: {mount['id']}")
    if "project" not in entries or not entries["project"].isdir():
        raise MigrationError("Backup has no project directory.")
    for name in entries:
        parts = PurePosixPath(name).parts
        if parts[0] == "project":
            if len(parts) > 1 and parts[1] == ".autopal-migration":
                raise MigrationError("Project payload uses the reserved migration metadata directory.")
        elif parts[0] == "mounts":
            if len(parts) == 1 and not entries[name].isdir():
                raise MigrationError("Invalid mount payload root.")
            if len(parts) > 1 and parts[1] not in ids:
                raise MigrationError(f"Unexpected mount payload: {name}")
        elif name != "manifest.json":
            raise MigrationError(f"Unexpected top-level archive member: {name}")
    return manifest


def open_verified_archive(path: Path) -> tuple[tarfile.TarFile, dict]:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.is_file():
        raise MigrationError(f"Checksum sidecar is required: {sidecar}")
    checksum = sidecar.read_text(encoding="utf-8").split()
    if not checksum or not re.fullmatch(r"[0-9a-fA-F]{64}", checksum[0]):
        raise MigrationError("Invalid SHA-256 sidecar.")
    if _digest(path) != checksum[0].lower():
        raise MigrationError("SHA-256 mismatch; the backup is corrupt or the sidecar belongs to another backup.")
    archive = tarfile.open(path, mode="r:gz")
    try:
        entries = {}
        for member in archive.getmembers():
            _check_member(member)
            name = _name(member.name)
            if name in entries:
                raise MigrationError(f"Duplicate archive member: {name}")
            entries[name] = member
        for name, member in entries.items():
            for parent in PurePosixPath(name).parents:
                ancestor = entries.get(str(parent))
                if ancestor is not None and not ancestor.isdir():
                    raise MigrationError(f"Archive writes through a file/link: {name}")
            if member.islnk():
                target = entries.get(posixpath.normpath(member.linkname))
                if target is None or not target.isreg():
                    raise MigrationError(f"Hardlink does not reference a regular payload file: {name}")
        return archive, _validate_manifest(archive, entries)
    except BaseException:
        archive.close()
        raise


def extract_archive(archive: tarfile.TarFile, destination: Path) -> None:
    directories, links = [], []
    for member in archive.getmembers():
        target = destination.joinpath(*PurePosixPath(_name(member.name)).parts)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if member.isdir():
            target.mkdir(exist_ok=True, mode=0o700)
            directories.append((member, target))
        elif member.isreg():
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output, archive.extractfile(member) as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            os.chmod(target, member.mode & 0o777)
            os.utime(target, (member.mtime, member.mtime))
        else:
            links.append((member, target))
    # Links are created last so extraction never traverses an archive symlink.
    for member, target in links:
        if member.issym():
            target.symlink_to(member.linkname)
        else:
            os.link(destination / member.linkname, target)
    for member, target in reversed(directories):
        os.chmod(target, member.mode & 0o777)
        os.utime(target, (member.mtime, member.mtime))
