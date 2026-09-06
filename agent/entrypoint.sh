#!/bin/sh
set -eu

for certificate_file in /certs/server.crt /certs/server.key /certs/ca.crt; do
  if [ ! -r "$certificate_file" ]; then
    echo "Required mTLS file is missing or unreadable: $certificate_file" >&2
    exit 1
  fi
done

exec gunicorn --no-control-socket --config /agent/gunicorn_conf.py app:app
