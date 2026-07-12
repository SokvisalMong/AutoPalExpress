# TICKET-0095

**Status**

Closed

**Type**

Bug

**Priority**

Medium

**Created**

2026-07-12

---

## Description

A fresh Linux deployment can fail at the first `docker compose up` with `permission denied while trying to connect to the Docker API at unix:///var/run/docker.sock`.

---

## Reason

The host account running Compose does not have permission to access Docker's Unix socket. The existing runbook assumes Docker is installed but does not explain daemon startup or the standard `docker`-group setup, so a new-server operator cannot distinguish a host Docker permission problem from an AutoPalExpress image or Compose problem.

---

## Implementation Plan

* [x] Document the Docker daemon and socket permission checks.

* [x] Document the preferred `docker`-group fix and temporary `sudo` workaround.

* [x] Link the prerequisite guidance from the README Compose quick start.

---

## Files Modified

* `LINUX_DOCKER_DEPLOYMENT.md`
* `README.md`
* `CHANGELOG.md`
* `.claude/memory/project_memory.md`
* `.claude/memory/ticket_memory.md`
* `tickets/closed/TICKET-0095.md`

---

## Testing

`docker compose config` completed successfully against `docker-compose.yml`. `docker info` completed successfully in the development environment, and documentation search confirmed the README link, Docker commands, socket warning, and ticket references.

---

## Result

Completed. Fresh Linux operators now get a direct diagnosis and safe recovery path before the first Compose build.

---

## Notes

This is a host-level Docker access issue, not an AutoPalExpress container user or `/data` ownership issue. The Docker socket must not be made world-writable.

---

## Closed

2026-07-12
