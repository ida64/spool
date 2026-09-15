#!/usr/bin/env bash
set -euo pipefail

for command in aws curl jq terraform; do
  command -v "$command" >/dev/null || {
    echo "missing required command: $command" >&2
    exit 1
  }
done

infra_dir="${1:-infra}"
api_endpoint="$(terraform -chdir="$infra_dir" output -raw batch_api_endpoint)"
table_name="$(terraform -chdir="$infra_dir" output -raw dynamodb_table_name)"
event_name="spool_smoke_$(date +%s)_$RANDOM"

read_count() {
  aws dynamodb get-item \
    --table-name "$table_name" \
    --key "{\"event_name\":{\"S\":\"$event_name\"}}" \
    --consistent-read \
    --output json | jq -r '.Item.count.N // "0"'
}

before="$(read_count)"
response_file="$(mktemp)"
trap 'rm -f "$response_file"' EXIT

status="$(curl --silent --show-error \
  --output "$response_file" \
  --write-out '%{http_code}' \
  --header 'content-type: application/json' \
  --data "{\"events\":[{\"event\":\"$event_name\"},{\"event\":\"$event_name\"}]}" \
  "$api_endpoint")"

if [[ "$status" != "202" ]]; then
  echo "expected HTTP 202, received $status: $(cat "$response_file")" >&2
  exit 1
fi

jq -e '.accepted == 2 and .failed == 0' "$response_file" >/dev/null || {
  echo "unexpected batch response: $(cat "$response_file")" >&2
  exit 1
}

expected=$((before + 2))
for _ in {1..20}; do
  after="$(read_count)"
  if [[ "$after" == "$expected" ]]; then
    echo "batch smoke test passed: $event_name increased from $before to $after"
    exit 0
  fi
  sleep 1
done

echo "timed out waiting for $event_name to reach $expected (last count: $after)" >&2
exit 1
