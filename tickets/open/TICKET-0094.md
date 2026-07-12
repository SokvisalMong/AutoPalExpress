# TICKET-0094

**Status**

Ready for live testing on the experimental branch

**Type**

Feature (Experimental)

**Priority**

High

**Created**

2026-07-12

---

## Description

Add an experimental per-server runtime choice when creating a Palworld server: `Linux (Mods Unsupported)` (the default/top option) or `Windows Binary (Mods Supported)`. On Linux hosts, the Windows choice must install and launch the Windows server through Wine. Windows-only Mods and UE4SS features must be unavailable for Linux-runtime servers. The UI must prominently warn that Palworld worlds/player data cannot safely move between Linux and Windows binaries because platform UUIDs differ, so a runtime choice is effectively permanent for a world.

This work lives only on `experimental/windows-server-runtime`; it must not be merged into `main` until tested.

## External setup reference

Wine prerequisites and UE4SS placement follow [CuteNatalie/Palworld-Modded-Server-Linux](https://github.com/CuteNatalie/Palworld-Modded-Server-Linux): 64-bit Wine prefix, winbind, VC++ 2015-2022 runtime, Windows SteamCMD, and UE4SS files under `Pal/Binaries/Win64`.

## Implementation Plan

- [x] Persist a normalized per-instance runtime with migration/inference for existing installs.
- [x] Add runtime selection to the new-server wizard with Linux first and the UUID transfer warning.
- [x] Install/launch the selected binary; use Windows SteamCMD and Wine for Windows runtime on Linux.
- [x] Resolve config and Mods paths by instance runtime, not backend host OS.
- [x] Hide/redirect Mods navigation and gate mod/UE4SS APIs for Linux-runtime servers.
- [x] Document the experimental Wine prerequisites and no-cross-runtime-transfer warning.
- [x] Verify backend compilation, frontend build, and focused runtime/path behavior; live Wine testing remains pending.

## Files Modified

`app/services/server_runtime.py`, `app/services/steam_locator.py`, `app/services/steamcmd.py`, `app/services/instance_store.py`, `app/services/local_config.py`, `app/services/palworld_settings.py`, `app/services/process_manager.py`, `app/services/deploy_jobs.py`, `app/services/server_update.py`, `app/routes/instances.py`, `app/routes/mods.py`, `app/routes/ue4ss.py`, runtime-aware frontend models/API/wizard/sidebar/routes/dashboard/instance cards, `tests/test_server_runtime.py`, README, Getting Started, architecture/decision/project memory, and changelog.

## Testing

- `python -m compileall -q app` passed.
- `python -m unittest tests.test_server_runtime` passed (3 tests).
- `npm run build` passed.
- `npm run lint` reported only the five pre-existing warnings in unrelated files.
- Backend route import smoke test could not run because this environment lacks the installed `fastapi` dependency.
- Live Wine deployment and UE4SS/mod installation remain pending on a Linux host with the documented prerequisites.

## Result

Implemented on `experimental/windows-server-runtime`; deliberately not merged into `main`. The ticket stays open until the user completes live Wine testing.

## Closed

