#!/bin/sh
set -eu

APP_USER=autopal
APP_UID="$(id -u "$APP_USER")"
APP_GID="$(id -g "$APP_USER")"
EXPECTED_OWNER="${APP_UID}:${APP_GID}"

repair_mount() {
    target="$1"
    mkdir -p "$target"

    # Bind mounts keep host ownership. Repair mounts left root-owned by an
    # older image before the application drops to its required non-root user.
    if [ "$(stat -c '%u:%g' "$target")" != "$EXPECTED_OWNER" ]; then
        echo "Repairing ownership of $target for $APP_USER"
        chown -R "$EXPECTED_OWNER" "$target"
    fi
}

repair_mount /data
repair_mount /servers

exec runuser --user "$APP_USER" -- "$@"
