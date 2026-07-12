# AutoPalExpress on a Linux Server with Docker

This guide takes you from a fresh Linux server to a running AutoPalExpress deployment using Docker Compose.

It applies to Linux distributions that already have:

- Docker installed.
- The Docker Compose plugin installed (`docker compose`, with a space).
- Internet access from the host for the image build and, if needed, SteamCMD.

Python, Node.js, npm, and SteamCMD do **not** need to be installed directly on the Linux host. The Docker image supplies the application runtime and builds the frontend.

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

## 10. Update the deployment

Back up persistent state before an update:

```bash
tar -czf autopalexpress-data-backup-$(date +%F).tar.gz data
```

Pull the latest project files and rebuild:

```bash
git pull
docker compose up -d --build
```

Check the updated service:

```bash
docker compose ps
docker compose logs --tail=100 autopalexpress
```

Accounts, settings, server registrations, mods, backups, and other files in `data/` remain outside the image.

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
