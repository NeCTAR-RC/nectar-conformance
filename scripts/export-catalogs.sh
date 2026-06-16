#!/usr/bin/env bash
# Export compiled catalogs from an open-source (unauthenticated) PuppetDB into a dir,
# one file per node as <certname>.json shaped for nectar-conformance --catalog-dir.
# Use this for a LIVE site: it needs no local puppet compile / octocatalog-diff.
# Usage: scripts/export-catalogs.sh [--env ENVIRONMENT] [--out DIR] [--url URL]
# Requires: curl, jq. Run on the PuppetDB host (unauthenticated API on loopback).

set -euo pipefail

env=""
out="./catalogs"
url="http://localhost:8080"

while [ $# -gt 0 ]; do
  case "$1" in
    --env) env="$2"; shift 2 ;;
    --out) out="$2"; shift 2 ;;
    --url) url="$2"; shift 2 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

for bin in curl jq; do
  command -v "$bin" >/dev/null 2>&1 || { echo "error: '$bin' is required" >&2; exit 1; }
done

mkdir -p "$out"

if [ -n "$env" ]; then
  query="nodes[certname]{ catalog_environment = \"${env}\" }"
else
  query="nodes[certname]{}"
fi
certnames=$(curl -fsS -G "${url}/pdb/query/v4" --data-urlencode "query=${query}" \
  | jq -r '.[].certname')

count=0
for cn in $certnames; do
  # Stream the resources through jq via stdin; passing them as a CLI arg overflows ARG_MAX
  # for large catalogs. A failed/missing catalog is skipped, not fatal.
  if curl -fsS "${url}/pdb/query/v4/catalogs/${cn}/resources" \
       | jq --arg cn "$cn" --arg env "$env" \
           '{certname: $cn, environment: (if $env == "" then null else $env end), resources: .}' \
       > "${out}/${cn}.json"; then
    count=$((count + 1))
  else
    echo "warning: could not export catalog for ${cn}; skipping" >&2
    rm -f "${out}/${cn}.json"
  fi
done
echo "wrote ${count} catalog file(s) to ${out}"
