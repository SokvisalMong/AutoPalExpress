# TICKET-0093

**Status**

Closed

**Type**

Bug

**Priority**

High

**Created**

2026-07-12

---

## Description

After rebooting or recreating the Linux Docker Compose service, the AutoPalExpress container can enter a restart loop before Uvicorn starts. The runtime image correctly runs as non-root `autopal`, but bind-mounted `/data` (and potentially `/servers`) may be owned by root after an earlier root-running container or host-side copy. The backend then fails during import when it tries to create `/data/instances` with `PermissionError: [Errno 13] Permission denied`.

## Reason

A persistent bind mount must remain usable after host reboot and container recreation without requiring the operator to know the container UID or manually repair ownership every time.

* [x] Add a root startup entrypoint that repairs mounted storage ownership when needed, then drops privileges to `autopal` before starting Uvicorn.
* [x] Keep Palworld's non-root runtime requirement intact and document the automatic repair/manual ownership fallback.
* [x] Rebuild/recreate the Compose service and verify API health plus restart persistence.

## Files Modified

* `Dockerfile`
* `docker-entrypoint.sh`
* `README.md`
* `LINUX_DOCKER_DEPLOYMENT.md`

## Testing

* `sh -n docker-entrypoint.sh`
* `docker compose build --no-cache autopalexpress`
* Recreated the service against root-owned bind mounts; the entrypoint repaired `/data`, Uvicorn started, and `/api/auth/status` returned HTTP 200.
* Restarted the Compose service; it returned to `healthy`, `/api/auth/status` returned `{"needsSetup":true}`, and the application process remained non-root.

## Result

The restart loop is fixed. Root-owned persistent mounts are repaired before the backend starts, while Uvicorn and Palworld still run as `autopal`.

## Notes

The live failure was reproduced from `docker logs autopalexpress-test-autopalexpress-1`; `/data` and `/data/instances` were root-owned bind-mounted paths, and the traceback failed at `instance_store.py` while creating `/data/instances`.

---

## Closed

2026-07-12
