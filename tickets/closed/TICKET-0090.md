# TICKET-0090

**Status**

Closed

**Type**

Bug

**Priority**

High

**Created**

2026-07-11

---

## Description

A Linux Palworld server launched from the Docker deployment remains as a sleeping process without binding UDP game port `8211` or TCP REST port `8212`. AutoPalExpress then reports REST metrics connection failures, and clients cannot connect to `127.0.0.1:8211`. The Linux container also returns 500 errors when the frontend checks Windows Firewall status because `netsh` is unavailable.

---

## Reason

Live testing on the Linux host reproduced the user's symptoms. The container had the Palworld process, but `/proc/net/udp` contained no game listener and `/proc/net/tcp` contained no REST listener. The spawned Linux process inherited no Steam app identity, and the Linux-only firewall calls were not degraded safely.

---

## Implementation Plan

* [x] Pass Linux Steam app identity environment variables to Palworld launches and retain the Compose shared-memory/file-descriptor limits.

* [x] Make Windows Firewall status calls return an explicit unsupported result on Linux instead of raising `FileNotFoundError` and HTTP 500.

* [x] Rebuild/restart the test container and verify game/REST listeners and metrics connectivity.

* [x] Update Linux deployment documentation and project records.

---

## Files Modified

- `Dockerfile`
- `docker-compose.yml`
- `app/services/process_manager.py`
- `app/services/firewall.py`
- `app/routes/network.py`
- `LINUX_DOCKER_DEPLOYMENT.md`
- `CHANGELOG.md`
- `.claude/memory/project_memory.md`
- `.claude/memory/ticket_memory.md`

---

## Testing

- `python -m compileall -q app` succeeded.
- `docker compose build` succeeded, including the frontend production build.
- `docker compose config` succeeded with `shm_size: 1gb` and `nofile` limits.
- Recreated the isolated Compose test container using the updated image.
- Confirmed Palworld runs as the non-root `autopal` user.
- Confirmed UDP game port `8211` and TCP REST port `8212` bind inside the container.
- `palworld_rest.metrics()` returned live values: `serverfps=59`, `serverfpsaverage=59.72999954223633`, `serverframetime=16.73365592956543`, and `maxplayernum=32`.
- Application logs showed repeated `GET /v1/api/metrics` and `GET /v1/api/info` HTTP 200 responses.
- Confirmed Linux firewall status returns `supported: false` and does not call `netsh`.

---

## Result

Linux Palworld startup and metrics now work in the Docker deployment. The root execution refusal was the direct cause of the missing game and REST listeners. `127.0.0.1:8211` remains a UDP game endpoint for the Palworld client, not an HTTP URL; REST TCP `8212` stays internal to the container.

---

## Closed

2026-07-11
