#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 OUTPUT_DIRECTORY COMMON_NAME" >&2
  exit 2
fi

output_dir=$1
common_name=$2
case "$common_name" in
  *[!A-Za-z0-9._-]*|'') echo 'Invalid common name' >&2; exit 2 ;;
esac

umask 077
mkdir -p "$output_dir"
if [ -e "$output_dir/server.key" ]; then
  echo "Refusing to overwrite $output_dir/server.key" >&2
  exit 1
fi
openssl req -newkey rsa:3072 -sha256 -nodes \
  -subj "/CN=$common_name" \
  -keyout "$output_dir/server.key" -out "$output_dir/server.csr"
chmod 0400 "$output_dir/server.key"
chmod 0444 "$output_dir/server.csr"
openssl req -in "$output_dir/server.csr" -noout -subject
