# TICKET-0088

**Status**

Closed

**Type**

Feature

**Priority**

Medium

**Created**

2026-07-11

---

## Description

Add a Docker Compose deployment for running AutoPalExpress on a Linux host through Docker or Portainer. The image must build the React frontend, run the FastAPI backend as the single production service, persist application data, and document the Portainer stack configuration and mounted server storage.

---

## Reason

The current supported distribution is a Windows installer, but a Linux host should be able to deploy the web panel without a Windows desktop or installer. Docker Compose is the common Portainer stack format and provides repeatable updates plus persistent volumes.

---

## Implementation Plan

* [x] Add a multi-stage Dockerfile that builds `web/` and runs the backend with a production Uvicorn command.

* [x] Add a Compose stack with persistent data/server mounts, configurable web/game ports, restart policy, and healthcheck.

* [x] Allow the backend data directory to be configured through an environment variable while preserving the existing source and Windows defaults.

* [x] Document Linux/Portainer deployment, first-run setup, volume paths, port forwarding, and update commands in the README.

* [x] Update architecture, project memory, ticket memory, changelog, and close this ticket after focused validation.

---

## Files Modified

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `app/paths.py`
- `app/services/steam_locator.py`
- `app/services/process_manager.py`
- `app/services/palworld_settings.py`
- `app/services/local_config.py`
- `app/services/steamcmd.py`
- `app/routes/instances.py`
- `README.md`
- `.claude/memory/architecture.md`
- `.claude/memory/decisions.md`
- `.claude/memory/project_memory.md`
- `.claude/memory/ticket_memory.md`
- `CHANGELOG.md`

---

## Testing

- `docker compose config` succeeded.
- `docker compose build` succeeded, including the Vite production build and Python runtime image.
- `docker compose up -d --force-recreate` started the service healthy.
- `curl --fail http://127.0.0.1:8000/api/auth/status` returned `{"needsSetup":true}`.
- `curl --fail http://127.0.0.1:8000/` returned the built AutoPalExpress HTML.
- `python -m compileall -q app` succeeded.
- Runtime-image helper smoke test confirmed Linux executable candidates, `steamcmd.sh`, and `/data`.
---

## Result

Linux hosts can deploy AutoPalExpress with Docker Compose or Portainer. The production image serves the built UI and API from one container, persists state through `/data`, supports mounted server files under `/servers`, publishes configurable admin/game/query ports, and keeps the REST management port private.

---

## Notes

The Compose service runs the panel and any Palworld server files mounted into the container. The stack must not publish the Palworld REST management port directly; friends should use the authenticated panel.

---

## Closed

2026-07-11
