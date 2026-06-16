#!/usr/bin/env bash
# Export per-node facts from an open-source (unauthenticated) PuppetDB into a directory,
# one file per node as <certname>.json in the {name, values} puppet facts format.
# That format is accepted both by octocatalog-diff's --fact-file and by
# nectar-conformance's static source (--facts-dir).
#
# Usage:
#   scripts/export-facts.sh [--env ENVIRONMENT] [--out DIR] [--url URL]
#
#   --env   limit to one puppet environment (a site == an environment); default: all nodes
#   --out   output directory; default: ./facts
#   --url   PuppetDB query API base URL; default: http://localhost:8080
#
# Requires: curl, jq. Run on the PuppetDB host (the unauthenticated API is on loopback).

set -euo pipefail

env=""
out="./facts"
url="http://localhost:8080"

while [ $# -gt 0 ]; do
  case "$1" in
    --env) env="$2"; shift 2 ;;
    --out) out="$2"; shift 2 ;;
    --url) url="$2"; shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

for bin in curl jq; do
  command -v "$bin" >/dev/null 2>&1 || { echo "error: '$bin' is required" >&2; exit 1; }
done

mkdir -p "$out"

# Fetch facts (optionally filtered to one environment) as one row per fact.
if [ -n "$env" ]; then
  facts_json=$(curl -fsS -G "${url}/pdb/query/v4" \
    --data-urlencode "query=facts[certname,name,value]{ environment = \"${env}\" }")
else
  facts_json=$(curl -fsS "${url}/pdb/query/v4/facts")
fi

# Group by certname, rebuild each node's fact tree, write one file per node.
count=0
while IFS=$'\t' read -r certname doc; do
  printf '%s' "$doc" > "${out}/${certname}.json"
  count=$((count + 1))
done < <(printf '%s' "$facts_json" | jq -r '
  group_by(.certname)[]
  | .[0].certname + "\t"
    + ({name: .[0].certname, values: (map({(.name): .value}) | add)} | @json)')

echo "wrote ${count} fact file(s) to ${out}"
