#!/usr/bin/env python3
"""Verify and restore a complete deployment without running restored code or Docker."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import sys
import tarfile
import tempfile

from migration_common import MigrationError, extract_archive, open_verified_archive


def destination_state(destination: Path) -> tuple[int, int] | None:
    """Refuse links and occupied targets without creating or removing anything."""
    try:
        info = destination.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise MigrationError("Destination must be a nonexistent or empty nonsymlink directory.")
    with os.scandir(destination) as entries:
        if next(entries, None) is not None:
            raise MigrationError(f"Destination is not empty: {destination}")
    return info.st_dev, info.st_ino


def destination_path(value: str) -> Path:
    requested = Path(os.path.abspath(os.path.expanduser(value)))
    # Do not resolve the final component: doing so would hide a destination symlink.
    destination_state(requested)
    try:
        parent = requested.parent.resolve(strict=True)
    except FileNotFoundError as exc:
        raise MigrationError("Destination parent directory must already exist.") from exc
    if not parent.is_dir():
        raise MigrationError("Destination parent must be a directory.")
    if not requested.name:
        raise MigrationError("The filesystem root cannot be a restore destination.")
    return parent / requested.name


def absolute_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MigrationError(f"{label} must be an absolute Linux path.")
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts or value.startswith("//"):
        raise MigrationError(f"{label} must be an absolute Linux path without '..'.")
    return path


def project_reference(value: object, old_root: PurePosixPath, destination: Path,
                      label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise MigrationError(f"Invalid {label} project path.")
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise MigrationError(f"Unsupported parent traversal in {label}: {value}")
    if path.is_absolute():
        try:
            relative = path.relative_to(old_root)
        except ValueError as exc:
            raise MigrationError(f"{label} is outside the captured project: {value}") from exc
    else:
        relative = path
    return str(destination.joinpath(*relative.parts))


def migrate_file_references(service: dict, old_root: PurePosixPath, destination: Path) -> None:
    for key in ("env_file", "label_file"):
        if key not in service:
            continue
        values = service[key]
        if isinstance(values, (str, dict)):
            values = [values]
        if not isinstance(values, list):
            raise MigrationError(f"Invalid Compose {key} value.")
        remapped = []
        for entry in values:
            if isinstance(entry, str):
                remapped.append(project_reference(entry, old_root, destination, key))
            elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
                entry = dict(entry)
                entry["path"] = project_reference(entry["path"], old_root, destination, key)
                remapped.append(entry)
            else:
                raise MigrationError(f"Invalid Compose {key} entry.")
        service[key] = remapped


def migrate_compose(manifest: dict, mounts: list[dict], destination: Path) -> dict:
    source = manifest.get("compose")
    if not isinstance(source, dict):
        raise MigrationError("Manifest Compose configuration is missing.")
    config = copy.deepcopy(source)
    services = config.get("services")
    if not isinstance(services, dict) or set(services) != {"autopalexpress"}:
        raise MigrationError("Only the single autopalexpress Compose service is supported.")
    service = services["autopalexpress"]
    if not isinstance(service, dict):
        raise MigrationError("Invalid autopalexpress service configuration.")
    for key in ("configs", "secrets", "include"):
        if config.get(key):
            raise MigrationError(f"Compose {key} dependencies are not captured by this archive format.")
    for key in ("configs", "secrets", "devices", "device_cgroup_rules", "develop",
                "credential_spec", "extends", "volumes_from", "tmpfs", "use_api_socket"):
        if service.get(key):
            raise MigrationError(f"Unsupported Compose service setting: {key}")
    networks = config.get("networks", {})
    if not isinstance(networks, dict):
        raise MigrationError("Invalid Compose network definitions.")
    old_name = config.pop("name", None)
    for name, network in networks.items():
        if network is None:
            continue
        if not isinstance(network, dict) or network.get("external"):
            raise MigrationError("External Compose networks cannot be restored independently.")
        if old_name and network.get("name") == f"{old_name}_{name}":
            network.pop("name")

    build = service.get("build")
    if isinstance(build, str):
        build = {"context": build}
        service["build"] = build
    if not isinstance(build, dict):
        raise MigrationError("The captured service needs a local build context for rebuilding.")
    old_root = absolute_path(build.get("context"), "Compose build context")
    if old_root == PurePosixPath("/"):
        raise MigrationError("A filesystem-root build context is unsupported.")
    for key in ("additional_contexts", "ssh", "secrets", "cache_from", "cache_to"):
        if build.get(key):
            raise MigrationError(f"Unsupported external build input: {key}")
    build["context"] = str(destination)
    dockerfile = build.get("dockerfile")
    if dockerfile is not None:
        # Absolute Dockerfile paths are context-relative in the restored deployment.
        remapped = project_reference(dockerfile, old_root, destination, "Dockerfile")
        build["dockerfile"] = str(Path(remapped).relative_to(destination))
    migrate_file_references(service, old_root, destination)

    volume_entries = service.get("volumes", [])
    if not isinstance(volume_entries, list):
        raise MigrationError("Compose volumes must be resolved long-form entries.")
    by_target = {mount["target"]: mount for mount in mounts}
    seen: set[str] = set()
    remapped_volumes = []
    for volume in volume_entries:
        if not isinstance(volume, dict) or volume.get("type") not in {"bind", "volume"}:
            raise MigrationError("Only resolved bind and named-volume mounts can be restored.")
        target = volume.get("target")
        if not isinstance(target, str) or target not in by_target or target in seen:
            raise MigrationError(f"Compose mount is absent or duplicated in manifest: {target!r}")
        mount = by_target[target]
        read_only = volume.get("read_only", False)
        if not isinstance(read_only, bool) or read_only != mount["readOnly"]:
            raise MigrationError(f"Compose mount read-only setting disagrees at {target}.")
        entry = {
            "type": "bind",
            "source": str(destination / ".autopal-migration" / "storage" / mount["id"]),
            "target": target,
            "read_only": mount["readOnly"],
            "bind": {"create_host_path": False},
        }
        if volume.get("consistency"):
            entry["consistency"] = volume["consistency"]
        if volume["type"] == "bind" and isinstance(volume.get("bind"), dict):
            for option in ("propagation", "selinux"):
                if option in volume["bind"]:
                    entry["bind"][option] = volume["bind"][option]
        remapped_volumes.append(entry)
        seen.add(target)
    if seen != set(by_target):
        missing = ", ".join(sorted(set(by_target) - seen))
        raise MigrationError(f"Manifest mounts are missing from Compose: {missing}")
    service["volumes"] = remapped_volumes
    service.pop("container_name", None)
    config.pop("volumes", None)
    return config


def escape_compose_dollars(value: object) -> object:
    """Resolved strings must survive Compose interpolation a second time."""
    if isinstance(value, str):
        return value.replace("$", "$$")
    if isinstance(value, list):
        return [escape_compose_dollars(item) for item in value]
    if isinstance(value, dict):
        # Compose interpolates values, never mapping keys (including environment names).
        return {key: escape_compose_dollars(item) for key, item in value.items()}
    return value


def write_json(path: Path, value: object) -> None:
    """Replace generated files rather than following a captured symlink/hardlink."""
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".migration-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def confirm_restore(destination: Path, assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise MigrationError("Restore requires interactive consent; use --yes for unattended operation.")
    print("Only restore backups you trust. Checksums detect corruption, not malicious content.")
    print(f"Restore all captured project and storage files into {destination}?")
    try:
        consent = input("Continue? [y/N] ").strip().lower()
    except EOFError as exc:
        raise MigrationError("Restore cancelled.") from exc
    if consent not in {"y", "yes"}:
        raise MigrationError("Restore cancelled.")


def restore(archive_path: Path, destination: Path, assume_yes: bool) -> None:
    original_state = destination_state(destination)
    archive, manifest = open_verified_archive(archive_path)
    try:
        mounts = manifest["mounts"]
        config = migrate_compose(manifest, mounts, destination)
        confirm_restore(destination, assume_yes)
        with tempfile.TemporaryDirectory(prefix=".autopal-restore-", dir=destination.parent) as temporary:
            staging = Path(temporary)
            extract_archive(archive, staging)
            project = staging / "project"
            root_mode = stat.S_IMODE(project.stat().st_mode) & 0o777
            project.chmod(root_mode | 0o700)
            metadata = project / ".autopal-migration"
            metadata.mkdir(mode=0o755)
            storage = metadata / "storage"
            storage.mkdir(mode=0o755)
            for mount in mounts:
                os.rename(staging / "mounts" / mount["id"], storage / mount["id"])
            write_json(metadata / "source-compose.json", manifest["compose"])
            write_json(project / "compose.migration.json", escape_compose_dollars(config))
            project.chmod(root_mode)
            if destination_state(destination) != original_state:
                raise MigrationError("Destination changed during restore; refusing installation.")
            # POSIX rename replaces an existing empty directory atomically. It cannot
            # replace a nonempty directory, so no removal/overwrite phase is needed.
            os.replace(project, destination)
    finally:
        archive.close()
    print(f"Restored deployment to {destination}")
    print("No services were started. Review the restored configuration before startup.")
    print("With Docker Engine and Compose installed, start it explicitly:")
    print(f"cd -- {shlex.quote(str(destination))}")
    print("docker compose -f compose.migration.json up -d --build")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore a complete AutoPalExpress backup without Docker or service startup.",
        epilog="A matching ARCHIVE.sha256 sidecar is required. The destination parent must exist.",
    )
    parser.add_argument("archive", type=Path, metavar="ARCHIVE.tar.gz")
    parser.add_argument("destination", metavar="DESTINATION",
                        help="nonexistent or empty nonsymlink directory")
    parser.add_argument("--yes", action="store_true", help="consent without an interactive prompt")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or newer is required.")
    try:
        destination = destination_path(args.destination)
        restore(args.archive.expanduser().absolute(), destination, args.yes)
    except (MigrationError, OSError, ValueError, tarfile.TarError, EOFError) as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Restore cancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
