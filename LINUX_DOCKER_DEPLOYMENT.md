# AutoPalExpress on a Linux Server with Docker

This guide takes you from a fresh Linux server to a running AutoPalExpress deployment using Docker Compose.

It applies to Linux distributions that already have:

- Docker installed.
- The Docker Compose plugin installed (`docker compose`, with a space).
- Internet access from the host for the image build and, if needed, SteamCMD.

Python, Node.js, npm, and SteamCMD do **not** need to be installed directly on the Linux host to run the application. The optional full-deployment backup/restore scripts require **Python 3.10+** on the host, using only its standard library.

## Docker daemon access

The `docker compose` command must be run by a host account that can access Docker's Unix socket. Before building AutoPalExpress, test that access:

```bash
docker info
```

If this returns `permission denied while trying to connect to the Docker API at unix:///var/run/docker.sock`, the problem is on the Linux host; the image has not started yet. Start Docker and confirm that the privileged client works:

```bash
sudo systemctl enable --now docker
sudo docker info
```

For normal system Docker installations, give your login account access to the `docker` group:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker info
```

If `docker info` still reports the same error, log out and back in (or reboot) so the new group membership is applied, then run it again. As a one-time workaround, the Compose command can be run with `sudo`:

```bash
sudo docker compose up -d --build
```

The `docker` group grants root-equivalent control of the host. Do not make `/var/run/docker.sock` world-writable with `chmod 666`. If the server intentionally uses rootless Docker, use that user's rootless daemon/context instead of mixing it with the system Docker socket.


## 1. Get the project

Install Git using your distribution's normal package manager if it is not already available. Alternatively, download and extract the repository archive.

Using Git:

```bash
git clone https://github.com/Kvitekvist/AutoPalExpress.git autopalexpress
cd autopalexpress
```

If you downloaded an archive, extract it and change into the extracted repository directory instead.

Confirm that the directory contains the deployment files:

```bash
ls Dockerfile docker-compose.yml
```

## 2. Prepare persistent storage

Create the two directories used by the Compose stack:

```bash
mkdir -p data servers
```

The default mounts are:

| Host path | Container path | Purpose |
| --- | --- | --- |
| `./data` | `/data` | Accounts, settings, sessions, logs, mods, backups, SteamCMD cache, and new server deployments |
| `./servers` | `/servers` | Optional location for existing Palworld server installations |

These directories must remain in place when the container is updated. They contain the state that should survive image rebuilds.

The image runs the application as a non-root `autopal` user. This is required by Palworld's Linux server, which refuses to start as root. On startup, the container entrypoint checks the mounted `/data` and `/servers` paths and repairs ownership when their mount-point is not owned by `autopal`; this handles bind mounts left root-owned by an older image or by a previous host-side copy. The repair runs before Uvicorn starts, then the application drops privileges and runs as `autopal`.

If Docker reports a permission error after a failed or interrupted deployment, stop the stack and repair the host paths explicitly before starting it again:

```bash
docker compose down
sudo chown -R 1000:1000 data servers
docker compose up -d --build
```

Use the same `sudo chown -R 1000:1000` command for custom `AUTOPAL_DATA_PATH` and `AUTOPAL_SERVERS_PATH` directories. Do not run the application itself as root: Palworld's Linux executable refuses root execution.

## 3. Configure ports

The default Compose stack publishes:

| Service | Protocol | Default port |
| --- | --- | ---: |
| AutoPalExpress panel | TCP | `8000` |
| Palworld game server | UDP | `8211` |
| Steam query port | UDP | `8212` |

Create a `.env` file in the repository root when different ports are required:

```dotenv
AUTOPAL_PORT=8000
PALWORLD_GAME_PORT=8211
PALWORLD_QUERY_PORT=8212
AUTOPAL_SHM_SIZE=1gb
TZ=UTC
```

For a different host storage location, add absolute paths to the same file:

```dotenv
AUTOPAL_DATA_PATH=/srv/autopalexpress/data
AUTOPAL_SERVERS_PATH=/srv/autopalexpress/servers
```

Create those directories before starting the stack:

```bash
mkdir -p /srv/autopalexpress/data /srv/autopalexpress/servers
```

The Compose file publishes one game port and one query port. If multiple Palworld instances use different ports, add their UDP mappings to `docker-compose.yml` or use a host-networking design appropriate for your environment.


### RAM versus shared memory

The Compose stack does **not** set a general container RAM limit. On a normal Linux Docker host, Palworld can use the host's available memory, subject to the host's own memory, swap, and OOM behavior. `AUTOPAL_SHM_SIZE` controls only the container's `/dev/shm` shared-memory filesystem, which is used for Linux IPC and some Unreal Engine operations; it is not a 1 GiB RAM allocation or a cap on Palworld's total memory.

Increase it only if the server or Unreal Engine reports shared-memory/IPC errors:

```dotenv
AUTOPAL_SHM_SIZE=2gb
```

Apply the change by recreating the stack:

```bash
docker compose up -d --force-recreate
```
Steam Query Port is disabled by default in AutoPalExpress. The UDP mapping is harmless while it is disabled, but it is only needed for gameplay/discovery after enabling the option in Launcher Options.

## 4. Build and start the stack

From the repository root:

```bash
docker compose up -d --build
```

The first build downloads the Node base image, frontend dependencies, Python dependencies, and Linux runtime libraries. It can take several minutes.

Check the service status:

```bash
docker compose ps
```

The container should eventually show `healthy`.

Follow the application logs when diagnosing startup problems:

```bash
docker compose logs -f autopalexpress
```

## 5. Open the panel and create the first account

Find the Linux server's reachable address using your normal network tools. For a local-network deployment, the host's LAN address is usually what other devices should use.

Open:

```text
http://<linux-server-address>:8000
```

The first-run setup screen asks you to create the super-admin account. This browser setup replaces the Windows installer setup flow.

You can test the unauthenticated setup status from the Linux host:

```bash
curl --fail http://127.0.0.1:8000/api/auth/status
```

A new deployment returns:

```json
{"needsSetup":true}
```

## 6. Deploy or import a Palworld server

### Deploy from the application

Use the server deployment flow in AutoPalExpress. The container uses Linux SteamCMD and stores the resulting deployment below `/data/servers`.

The corresponding host path with the default mounts is:

```text
./data/servers/<server-name>
```

The host needs outbound internet access for SteamCMD and any external integrations used by the application.

### Import an existing server

Copy the existing Linux Palworld server into the host directory mounted as `./servers`:

```bash
cp -a /path/to/PalServer ./servers/
```

Import it in the AutoPalExpress UI using the **container path**:

```text
/servers/PalServer
```

Do not enter the host path. For example, enter `/servers/PalServer`, not `/srv/autopalexpress/servers/PalServer`.

The Linux server executable candidates recognized by the application are:

```text
PalServer.sh
PalServer-Linux-Shipping
PalServer
```

## 7. Open the Linux firewall

Firewall commands vary by Linux distribution and firewall implementation. If the host firewall is enabled, allow the panel TCP port and Palworld UDP ports using the tools appropriate for that distribution.

The required defaults are:

```text
TCP 8000  - AutoPalExpress panel
UDP 8211  - Palworld game traffic
UDP 8212  - Steam query traffic, only when query port is enabled
```

Do not expose Palworld's REST management port. The Compose stack intentionally does not publish it; AutoPalExpress uses it internally and friends should use the authenticated panel instead.

## 8. Configure router forwarding when remote players need access

If players connect from outside the Linux server's local network, forward the Palworld game UDP port from the router to the Linux server's LAN address:

```text
Protocol: UDP
External port: 8211
Internal address: <linux-server-LAN-address>
Internal port: 8211
```

Forward the query port separately only when it is enabled:

```text
Protocol: UDP
External port: 8212
Internal address: <linux-server-LAN-address>
Internal port: 8212
```

Only forward the AutoPalExpress panel port when remote panel access is actually required:

```text
Protocol: TCP
External port: 8000
Internal address: <linux-server-LAN-address>
Internal port: 8000
```

The panel currently uses plain HTTP. A VPN such as Tailscale or ZeroTier, or a reverse proxy with real HTTPS, is safer than exposing the panel directly to the public internet.

## 9. Start and configure the server

After the server is deployed or imported:

1. Open **Settings** and verify the server path.
2. Verify the game port.
3. Use **World Settings** for Palworld configuration values.
4. Use **Launcher Options** for optional launch flags.
5. Start the server from **Server Control**.
6. Confirm that the Dashboard reports the server as online.

The Palworld process runs inside the AutoPalExpress container. The Compose UDP mappings make the published game/query ports reachable through the Linux host.

`127.0.0.1:8211` is a UDP game endpoint, not an HTTP page. Do not test it with a browser or `curl`; connect to it from the Palworld client. The REST API uses TCP `8212` inside the container and is intentionally not published to the host.

## 10. Back up, migrate, and update

### Create a full backup

Run from the AutoPalExpress repository root. The backup command requires host Python 3.10+, Docker CLI/Compose, access to the Docker daemon, and an existing AutoPalExpress container. It also works when that container is already stopped.

```bash
python3 --version
bash backup.sh
```

The command asks permission for downtime, forces a save and requests REST shutdown for every running registered Palworld instance, waits for game processes to exit, and stops AutoPalExpress before copying files. A failed save/shutdown or an unregistered game process aborts the backup; there is no force-kill or stale-save fallback. If REST is unavailable, save and stop the game manually first. **Nothing restarts automatically, even after an error.** Check the old server's state if the command fails.

The archive contains:

- Project files, including `.env`, Git metadata when present in the project, local files, and the migration commands.
- Every persistent bind mount or named volume attached to the container: application accounts/sessions/settings/logs/history/backups and complete Palworld binaries, saves, configuration, and mods.
- Resolved Compose configuration, actual container environment, published ports, shared memory size, and image platform.

It discovers the actual container mounts instead of assuming `./data` and `./servers`. Registered server paths and custom mod paths outside captured mounts are refused, not silently omitted.

The default output is `backups/autopalexpress-<UTC-time>-<unique-id>.tar.gz` with a matching `.tar.gz.sha256`. Both filenames are printed. The archive is private to the invoking user, but **not encrypted**; it contains credentials, sessions, and potentially API keys. Transfer/store it securely. A checksum detects corruption, not a malicious or untrusted backup.

Optional arguments:

```bash
# Put archives on another disk, outside all mounted storage.
bash backup.sh --output-dir /mnt/backups/autopalexpress

# Select the existing Portainer container explicitly.
bash backup.sh --container YOUR_CONTAINER_NAME

# Acknowledge downtime without a prompt.
bash backup.sh --yes
```

For Portainer, the repository's resolved Compose mount targets must match the selected container. Live container mount sources, environment and port settings are captured even when Portainer supplied values outside `.env`.

The output directory, the project's `backups/`, and generated `.autopal-migration/` metadata are excluded from the project payload to prevent recursive archives. Persistent storage under `.autopal-migration/` is still captured separately through its mounts, so backing up a restored deployment works. No old backup files are deleted automatically.

This is an application migration, not a host disk image. Docker image layers, OS packages, router/firewall/DNS rules, and unrelated host services are not included. Rebuilding needs Docker/Compose and internet access. The scripts support the single `autopalexpress` Compose service and project-root build context. Extra services, external networks/secrets/configs, external build inputs, tmpfs/device mounts, special files, and escaping/absolute symlinks are refused rather than producing an incomplete or unsafe archive.

### Restore onto a new server

1. Transfer **both** the archive and its `.sha256` sidecar, keeping their filenames together.
2. Clone/download a current AutoPalExpress checkout on the new server so `restore.sh` and `scripts/` are available. Host Python 3.10+ is required; extraction itself does not need Docker.
3. Choose a **nonexistent or empty, nonsymlink** destination. Its parent directory must already exist. Do not use the nonempty checkout containing the restore command as the destination.

From that checkout, replacing the example archive path:

```bash
bash restore.sh /path/to/backup.tar.gz /srv/autopalexpress-restored
```

Use `--yes` to acknowledge restore without a prompt. There is deliberately no overwrite option.

Restore verifies the checksum, manifest, member paths and links before extracting into private staging. The completed project is installed atomically. Existing occupied destinations are left untouched. Regular permissions/executable bits are retained, special permission bits are stripped, and extracted files belong to the restoring user rather than arbitrary archived UIDs.

All captured storage is restored under:

```text
/srv/autopalexpress-restored/.autopal-migration/storage/<mount-id>
```

Named volumes become local bind directories. The generated `compose.migration.json` maps these new host paths to the **original container paths**, preserving `instances.json` IDs and server/mod paths. It also relocates the build context and retains the resolved settings. Original deployment files remain available; the source Compose snapshot is saved in `.autopal-migration/source-compose.json`.

The image repairs ownership of `/data` and `/servers` on startup. If restoring with a different UID or using additional custom mounts, ensure all restored storage is accessible to the image's `autopal` UID/GID (`1000:1000` in the standard image):

```bash
sudo chown -R 1000:1000 /srv/autopalexpress-restored/.autopal-migration/storage
```

Review the generated configuration, especially published host IP/port bindings and public address overrides. Then explicitly start:

```bash
cd /srv/autopalexpress-restored
docker compose -f compose.migration.json up -d --build
docker compose -f compose.migration.json ps
```

**Always use `-f compose.migration.json` for a restored deployment**, including logs, restart and update commands. Its values are already resolved; changing the old `.env` does not reconfigure them. Edit the snapshot when changing ports or other deployment settings. Literal `$` characters in resolved string values are represented as `$$` for Compose.

Restore never starts the panel or game automatically. Once the panel starts, a previously enabled active-server auto-start setting still applies. Verify existing admin login, selected instance, world/player/guild/base progress, mods, settings, and a save/restart before cutover. Reconfigure firewall/router/DNS for the new host. Keep the old deployment stopped but intact; never let players use both world copies.

### Update an existing deployment

Take a full backup first, then pull the latest project files and rebuild:

```bash
bash backup.sh
git pull
docker compose up -d --build
```

For a restored deployment, replace the last command with `docker compose -f compose.migration.json up -d --build`.

Check the updated service with `docker compose ps` and `docker compose logs --tail=100 autopalexpress` (add the same `-f` option after `compose` when restored).

## 11. Stop, start, and restart

Stop the service without deleting persistent data:

```bash
docker compose down
```

Start it again:

```bash
docker compose up -d
```

Restart only the application container:

```bash
docker compose restart autopalexpress
```

Avoid `docker compose down -v` unless you intentionally want to delete Docker-managed volumes. The normal deployment uses bind mounts, but deleting volumes is still an unsafe habit when the Compose file is later changed to use named volumes.

## 12. Portainer deployment

Portainer can deploy the same Compose file as a stack:

1. Open **Stacks**.
2. Select **Add stack**.
3. Load the repository from Git or paste the contents of `docker-compose.yml`.
4. Set stack environment variables if needed:
   - `AUTOPAL_PORT`
   - `PALWORLD_GAME_PORT`
   - `PALWORLD_QUERY_PORT`
   - `AUTOPAL_DATA_PATH`
   - `AUTOPAL_SERVERS_PATH`
   - `TZ`
5. Deploy the stack.
6. Wait for the container to become healthy.
7. Open `http://<linux-server-address>:8000`.

Use host paths in Portainer variables, for example:

```dotenv
AUTOPAL_DATA_PATH=/srv/autopalexpress/data
AUTOPAL_SERVERS_PATH=/srv/autopalexpress/servers
```

When importing a mounted server through the application, still use its container path, such as `/servers/PalServer`.


### Common Linux container symptoms

If the log says `Refusing to run with the root privileges`, rebuild and recreate the latest image. Do not override the Compose service with `user: root`.

If the Dashboard says metrics are unavailable, check that the Palworld REST API is listening inside the container:

```bash
docker compose exec autopalexpress sh -c 'cat /proc/net/tcp'
```

The REST listener appears as hexadecimal port `2014`, which is decimal `8212`. Check the application log for successful requests such as:

```text
GET http://127.0.0.1:8212/v1/api/metrics 200
```

The Linux deployment does not use the Windows Firewall integration. Configure the Linux host firewall with its normal system tool instead; the panel reports Windows Firewall as unsupported rather than trying to run `netsh`.

## Troubleshooting commands

Show service status:

```bash
docker compose ps
```

Read recent logs:

```bash
docker compose logs --tail=200 autopalexpress
```

Check the API from the host:

```bash
curl --fail http://127.0.0.1:8000/api/auth/status
```

Recreate the container after changing Compose environment variables:

```bash
docker compose up -d --force-recreate
```

Rebuild without using cached image layers:

```bash
docker compose build --no-cache
docker compose up -d
```
