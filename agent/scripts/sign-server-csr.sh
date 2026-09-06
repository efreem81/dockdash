#!/bin/sh
set -eu

if [ "$#" -ne 4 ]; then
  echo "Usage: $0 CA_DIRECTORY CSR_FILE OUTPUT_CERTIFICATE SAN" >&2
  echo "Example SAN: IP:192.168.0.160 or DNS:dockerhost-agent" >&2
  exit 2
fi

ca_dir=$1
csr_file=$2
output_certificate=$3
san=$4
case "$san" in
  IP:*|DNS:*) ;;
  *) echo 'SAN must begin with IP: or DNS:' >&2; exit 2 ;;
esac
case "$san" in
  *[!A-Za-z0-9:.,_-]*) echo 'SAN contains unsupported characters' >&2; exit 2 ;;
esac

umask 077
extension_file=$(mktemp)
trap 'rm -f "$extension_file"' EXIT HUP INT TERM
printf '%s\n' \
  'basicConstraints=critical,CA:FALSE' \
  'keyUsage=critical,digitalSignature,keyEncipherment' \
  'extendedKeyUsage=serverAuth' \
  "subjectAltName=$san" > "$extension_file"

openssl x509 -req -sha256 -days 397 \
  -in "$csr_file" -CA "$ca_dir/ca.crt" -CAkey "$ca_dir/ca.key" \
  -CAcreateserial -extfile "$extension_file" -out "$output_certificate"
chmod 0444 "$output_certificate"
openssl verify -CAfile "$ca_dir/ca.crt" -purpose sslserver "$output_certificate"
