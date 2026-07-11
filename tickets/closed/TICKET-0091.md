# TICKET-0091

**Status**

Closed

**Type**

Enhancement

**Priority**

Medium

**Created**

2026-07-11

---

## Description

Make Dashboard server-status polling more responsive and clarify/configure Docker shared memory for Linux Palworld deployments.

---

## Reason

The Dashboard currently polls status every four seconds, which makes state and metrics changes feel stale. The Compose deployment's `shm_size` is shared memory, not total container RAM; users need an explicit safe configuration path and documentation so they do not confuse it with a RAM limit.

---

## Implementation Plan

* [x] Increase Dashboard status polling to one second.

* [x] Make Compose shared-memory size configurable with `AUTOPAL_SHM_SIZE`, retaining a 1 GiB default and no general container RAM cap.

* [x] Explain RAM versus `/dev/shm` in the Linux deployment guide and README; do not expose the Docker socket or pretend a web setting can recreate its own container safely.

* [x] Update project records and verify frontend build, Compose interpolation, and runtime behavior.

---

## Files Modified

- `web/src/pages/Dashboard.tsx`
- `docker-compose.yml`
- `LINUX_DOCKER_DEPLOYMENT.md`
- `README.md`
- `CHANGELOG.md`
- `.claude/memory/project_memory.md`
- `.claude/memory/ticket_memory.md`

---

## Testing

- `docker compose build` succeeded, including the Vite frontend build.
- `AUTOPAL_SHM_SIZE=2gb docker compose config` resolved `shm_size` to 2147483648 bytes.
- Backend compilation remained successful.

## Note

No web UI control was added for Docker memory because the running application cannot change its own container's `/dev/shm` allocation, and mounting `/var/run/docker.sock` would grant root-equivalent control of the Linux host. The safe operational control is the `.env`/Portainer `AUTOPAL_SHM_SIZE` setting followed by container recreation. Total container RAM remains uncapped.

---

## Result

Dashboard status polling is now one second. Linux deployments can configure shared memory with `AUTOPAL_SHM_SIZE`; this changes `/dev/shm` only and does not cap or allocate Palworld's total RAM.

---

## Closed

2026-07-11
