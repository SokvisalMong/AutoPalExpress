# TICKET-0096

**Status**

Closed

**Type**

Feature

**Priority**

High

**Created**

2026-10-26

---

## Description

Add root-level Bash commands that back up the complete Linux/Docker AutoPalExpress deployment and restore it onto a new server. Include project files, application accounts/settings/history/backups, full Palworld installations/saves/mods, actual persistent Docker mounts, and resolved Compose configuration.

---

## Reason

The existing Backup Now feature copies only SaveGames and cannot migrate the complete deployment. The user needs runnable backup and restore scripts, not manual archive instructions.

---

## Implementation Plan

* [x] Add backup.sh and a standard-library Python backup implementation that discovers the actual container mounts, quiesces Palworld safely, stops the container, archives the project and persistent storage, and emits a SHA-256 sidecar.
* [x] Add restore.sh and a matching restore implementation that validates the checksum/archive, refuses nonempty destinations, extracts into staging, remaps mounts/build paths, and leaves the restored deployment stopped.
* [x] Exercise actual script entry points with temporary deployments, including custom storage, archive corruption, unsafe paths, and destination collisions.
* [x] Update deployment guidance, README, architecture, decision/project/ticket memory, and changelog.

---

## Files Modified

- `backup.sh`, `restore.sh`
- `scripts/migration_common.py`, `scripts/server_backup.py`, `scripts/server_restore.py`
- `.gitignore`, `.dockerignore`
- `README.md`, `LINUX_DOCKER_DEPLOYMENT.md`, `CHANGELOG.md`
- `.claude/memory/architecture.md`, `.claude/memory/decisions.md`
- `.claude/memory/project_memory.md`, `.claude/memory/ticket_memory.md`
- `tickets/closed/TICKET-0096.md`

---

## Testing

- Bash syntax and both actual `--help` entry points passed; all three Python helpers parsed successfully without pip dependencies.
- Built the actual application image for `linux/amd64`, including frontend compilation. Built it again from a restored project's relocated Compose build context.
- A real isolated Docker deployment used an external data bind, a named server volume, a read-only file mount, and an admin account created through the real HTTP setup endpoint. Backup/restore preserved project hidden/local files, accounts, instance ID/history, world/player/mod/config files, and mount read-only settings.
- Exercised real HTTP save/shutdown requests and process discovery using a disposable REST protocol process named PalServer. A rejected save aborted without an archive or forced stop; the successful sequence wrote the fresh world bytes before shutdown and container stop. The Palworld game engine itself was not launched.
- Restored application served HTML and accepted the existing admin password without first-run setup. A second migration of that restored deployment worked; actual Docker runtime labels/environment retained literal dollar characters.
- Verified already-stopped backup, no archive recursion, no partial-file leaks, unmounted server-path refusal, output-inside-storage refusal, noninteractive consent enforcement, checksum mismatch, invalid manifest version, traversal/absolute/cross-payload-link refusal, and empty/nonempty/symlink destination handling.
- Native ARM image build exposed the existing Dockerfile's x86-only lib32 package requirement; verification used supported amd64 emulation instead. Unchanged frontend dependencies reported six high-severity npm advisories and the existing large-chunk warning; dependencies were not changed by this ticket.

---

## Result

Complete full-deployment migration commands and documented cutover process. The source remains stopped; destination extraction is atomic and does not start services. Restored runtime uses explicit `compose.migration.json`, with old container paths/instance IDs unchanged and new host storage paths.

---

## Notes

Linux Docker Compose deployment; host-level OS packages, Docker images, router/firewall/DNS configuration, and unrelated host services are not part of the application backup. Default backup output and generated migration metadata are excluded from the project payload; persistent mounts are captured separately. Restore never starts a game server automatically.

No packaged application/installer version bump: this adds optional host tools and documentation, not packaged application behavior. The in-app save-only backup/restore-UI status is intentionally unchanged.

---

## Closed

2026-10-26
