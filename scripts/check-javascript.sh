#!/usr/bin/env bash
set -euo pipefail

repository_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
while IFS= read -r javascript_file; do
  node --check "$javascript_file"
done < <(find "$repository_dir/static/js" -type f -name '*.js' -print | sort)
