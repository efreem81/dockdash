#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 OUTPUT_DIRECTORY" >&2
  exit 2
fi

output_dir=$1
umask 077
mkdir -p "$output_dir"
for protected_file in ca.key controller.key; do
  if [ -e "$output_dir/$protected_file" ]; then
    echo "Refusing to overwrite $output_dir/$protected_file" >&2
    exit 1
  fi
done

extension_file=$(mktemp)
trap 'rm -f "$extension_file" "$output_dir/controller.csr"' EXIT HUP INT TERM
printf '%s\n' \
  'basicConstraints=critical,CA:FALSE' \
  'keyUsage=critical,digitalSignature,keyEncipherment' \
  'extendedKeyUsage=clientAuth' > "$extension_file"

openssl req -x509 -newkey rsa:4096 -sha256 -nodes -days 3650 \
  -subj '/CN=DockDash Private Agent CA' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' \
  -addext 'subjectKeyIdentifier=hash' \
  -keyout "$output_dir/ca.key" -out "$output_dir/ca.crt"
openssl req -newkey rsa:3072 -sha256 -nodes \
  -subj '/CN=dockdash-controller' \
  -keyout "$output_dir/controller.key" -out "$output_dir/controller.csr"
openssl x509 -req -sha256 -days 397 \
  -in "$output_dir/controller.csr" \
  -CA "$output_dir/ca.crt" -CAkey "$output_dir/ca.key" -CAcreateserial \
  -extfile "$extension_file" -out "$output_dir/controller.crt"

chmod 0400 "$output_dir/ca.key" "$output_dir/controller.key"
chmod 0444 "$output_dir/ca.crt" "$output_dir/controller.crt"
openssl verify -CAfile "$output_dir/ca.crt" -purpose sslclient "$output_dir/controller.crt"
