#!/bin/sh
set -eu

: "${ADMIN_PASSWORD:?ADMIN_PASSWORD is required}"

umask 077
printf 'admin: %s\n' "$ADMIN_PASSWORD" > /fuseki/passwords

exec java -Xmx1g -jar /fuseki/fuseki-server.jar \
    --conf=/fuseki/config.ttl \
    --passwd=/fuseki/passwords \
    --auth=basic \
    "$@"
