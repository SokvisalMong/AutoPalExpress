"""Create a stopped, full-deployment AutoPalExpress migration archive."""

from __future__ import annotations

import argparse
import io
import json
import os
import posixpath
import shlex
import subprocess
import sys
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from migration_common import (
    MigrationError, add_mount, add_project, docker, load_deployment,
    open_verified_archive, write_checksum,
)


QUIESCE = '''
import asyncio
import time
import psutil
from app.services import instance_store, palworld_rest, process_manager


def live_processes():
    found = []
    for process in psutil.process_iter(["name", "status"]):
        if (process.info["name"] or "").lower() in process_manager._PALWORLD_PROCESS_NAMES:
            if process.info["status"] != psutil.STATUS_ZOMBIE:
                found.append(process)
    return found


async def main():
    instances = instance_store.list_instances()
    running = [i for i in instances if process_manager._instance_processes(i)]
    registered = {p.pid for i in instances for p in process_manager._instance_processes(i)}
    if any(p.pid not in registered for p in live_processes()):
        raise RuntimeError("Unregistered Palworld process found. Stop it before backup.")
    # Save every server before shutting any of them down. A failed REST call
    # aborts; there is deliberately no force-kill or stale-save fallback.
    for instance in running:
        print("Saving " + instance["name"], flush=True)
        await palworld_rest.save(instance)
    for instance in running:
        print("Shutting down " + instance["name"], flush=True)
        await palworld_rest.shutdown(instance, 0, "Server migration backup: maintenance in progress.")
    deadline = time.monotonic() + 120
    while live_processes():
        if time.monotonic() >= deadline:
            raise RuntimeError("Palworld did not exit within 120 seconds; stop it manually and retry.")
        await asyncio.sleep(0.5)
    print("All Palworld processes are stopped.", flush=True)


asyncio.run(main())
'''


def container_json(container: str, path: str, default: dict) -> dict:
    result = subprocess.run(
        ["docker", "cp", f"{container}:{path}", "-"], capture_output=True, check=False
    )
    if result.returncode:
        error = result.stderr.decode(errors="replace").strip()
        if "could not find the file" in error.lower():
            return default
        raise MigrationError(error or f"Cannot read container file {path}.")
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        members = archive.getmembers()
        if len(members) != 1 or not members[0].isreg() or members[0].size > 8 * 1024 * 1024:
            raise MigrationError(f"Expected a small JSON file, not a link or directory: {path}")
        with archive.extractfile(members[0]) as source:
            value = json.load(source)
    if not isinstance(value, dict):
        raise MigrationError(f"Invalid object in {path}.")
    return value


def validate_paths(info: dict, mounts: list[dict]) -> None:
    environment = dict(item.split("=", 1) for item in info["Config"].get("Env", []) if "=" in item)
    data = environment.get("AUTOPAL_DATA_DIR", "/data")

    def covered(path: str) -> None:
        if not isinstance(path, str) or not path.startswith("/") or posixpath.normpath(path) != path:
            raise MigrationError(f"Expected a canonical Linux container path, got {path!r}.")
        if not any(path == mount["target"] or path.startswith(mount["target"] + "/") for mount in mounts):
            raise MigrationError(f"{path} is outside persistent Docker mounts; mount it before backing up.")

    covered(data)
    registry = container_json(info["Id"], f"{data}/instances.json", {"instances": []})
    instances = registry.get("instances")
    if not isinstance(instances, list):
        raise MigrationError("Invalid instances.json: instances must be a list.")
    for instance in instances:
        if not isinstance(instance, dict):
            raise MigrationError("Invalid instance record in instances.json.")
        covered(instance.get("serverPath"))
        instance_id = instance.get("id")
        if not isinstance(instance_id, str) or instance_id in {"", ".", ".."} or len(PurePosixPath(instance_id).parts) != 1:
            raise MigrationError("Invalid instance ID in instances.json.")
        config = container_json(info["Id"], f"{data}/instances/{instance_id}/config.json", {})
        if config.get("modsPathOverride"):
            covered(config["modsPathOverride"])


def confirm(yes: bool) -> None:
    print("This saves/shuts down every Palworld instance, then stops AutoPalExpress.")
    print("The old deployment will NOT restart automatically, including after an error.")
    if not yes:
        if not sys.stdin.isatty():
            raise MigrationError("Noninteractive backup requires --yes to acknowledge downtime.")
        if input("Continue? Type yes: ").strip().lower() != "yes":
            raise MigrationError("Backup cancelled; the deployment was not stopped.")


def backup(root: Path, output: Path, container: str | None, yes: bool) -> Path:
    config, info, mounts = load_deployment(root, container)
    validate_paths(info, mounts)
    output = output.expanduser().resolve()
    for mount in mounts:
        source = Path(mount["source"]).resolve()
        if output == source or output.is_relative_to(source):
            raise MigrationError("Backup output must be outside all mounted storage directories.")
        if root == source or root.is_relative_to(source):
            raise MigrationError("A mount contains the project root; separate project and server storage first.")
    if output == root or root.is_relative_to(output):
        raise MigrationError("Choose a backup output subdirectory or a directory outside the project, not its parent.")
    confirm(yes)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC")
    path = output / f"autopalexpress-{stamp}-{uuid.uuid4().hex[:8]}.tar.gz"
    partial = path.with_name(path.name + ".partial")
    published = False
    try:
        if info["State"]["Running"]:
            print("Saving and stopping game servers...", flush=True)
            print(docker("exec", "--user", "autopal", info["Id"], "python", "-c", QUIESCE), end="", flush=True)
            docker("stop", "--time", "120", info["Id"])
        stopped = json.loads(docker("inspect", info["Id"]))[0]
        if stopped["State"]["Running"]:
            raise MigrationError("Container is still running; no backup was created.")
        # Validate metadata again after the scheduler and all game writers stop.
        validate_paths(stopped, mounts)
        print(f"Writing {path} (all project files and persistent mounts)...", flush=True)
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output_file:
            with tarfile.open(fileobj=output_file, mode="w:gz", dereference=False) as archive:
                exclusions = [output, *(Path(mount["source"]) for mount in mounts)]
                add_project(archive, root, exclusions)
                for mount in mounts:
                    print(f"Archiving {mount['target']}...", flush=True)
                    add_mount(archive, info["Id"], mount)
                manifest = {
                    "format": "autopalexpress-full-backup", "version": 1,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "compose": config, "mounts": mounts,
                }
                payload = json.dumps(manifest, indent=2).encode("utf-8")
                entry = tarfile.TarInfo("manifest.json")
                entry.mode, entry.size = 0o600, len(payload)
                archive.addfile(entry, io.BytesIO(payload))
            output_file.flush()
            os.fsync(output_file.fileno())
        # Verify the exact archive that will be delivered, before publishing it.
        checksum = write_checksum(partial)
        verified, _ = open_verified_archive(partial)
        verified.close()
        digest = checksum.read_text(encoding="utf-8").split()[0]
        checksum.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
        partial.rename(path)
        checksum.rename(path.with_name(path.name + ".sha256"))
        published = True
    finally:
        partial.unlink(missing_ok=True)
        partial.with_name(partial.name + ".sha256").unlink(missing_ok=True)
        if not published:
            path.unlink(missing_ok=True)
            path.with_name(path.name + ".sha256").unlink(missing_ok=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the full Linux/Docker AutoPalExpress deployment; leave it stopped.")
    parser.add_argument("--output-dir", type=Path, help="Archive directory (default: ./backups in the project).")
    parser.add_argument("--container", help="Existing Docker container name/ID, useful for Portainer deployments.")
    parser.add_argument("--yes", action="store_true", help="Acknowledge maintenance downtime without prompting.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or newer is required.")
    os.umask(0o077)
    try:
        path = backup(root, args.output_dir or root / "backups", args.container, args.yes)
    except (MigrationError, OSError, ValueError, tarfile.TarError, EOFError) as exc:
        print(f"Backup failed: {exc}\nCheck the old server's state before retrying; nothing is restarted automatically.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Backup interrupted. The old deployment is not restarted automatically.", file=sys.stderr)
        return 130
    print(f"\nBackup complete: {path}\nChecksum: {path}.sha256")
    print("Both files contain or protect sensitive data; copy them securely to the new server.")
    print("AutoPalExpress remains stopped. Do not run both copies of the world.")
    print(f"Restore on the new server: bash restore.sh {shlex.quote(str(path))} /path/to/new/AutoPalExpress")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
