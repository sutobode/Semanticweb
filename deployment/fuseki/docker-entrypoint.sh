#!/bin/sh
set -eu

cp /opt/vietheritage-shiro.ini "$FUSEKI_BASE/shiro.ini"
exec /tmp/fuseki-base-entrypoint.sh "$@"
