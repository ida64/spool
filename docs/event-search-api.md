# Event Search API

Spool can query raw telemetry archived in S3 without copying arbitrary event properties into DynamoDB.

## Endpoints

### Search events

`GET /api/v1/events/search`

Required headers:

- `X-API-Key` - API Gateway key.
- `X-Spool-Project` - project ID.
- `X-Spool-Token` - project token.

Supported query parameters:

- `event` - exact event name.
- `stage` - exact stage.
- `since` - ISO-8601 timestamp or relative duration such as `30m`, `2h`, or `3d`.
- `until` - ISO-8601 timestamp. Defaults to now.
- `limit` - page size from 1 to 100. Defaults to 100.
- `next_token` - opaque signed pagination/query token returned by Spool.

Searches default to the previous 24 hours and are capped at a seven-day window. The Athena query is always scoped to the authenticated project and includes projected year/month/day/hour partition predicates.

Example:

```bash
curl -s \
  -H "X-API-Key: $SPOOL_API_KEY" \
  -H "X-Spool-Project: default" \
  -H "X-Spool-Token: $SPOOL_TOKEN" \
  "$SPOOL_URL/api/v1/events/search?event=player_error&stage=production&since=2h&limit=50"
```

A query that finishes within the Lambda request returns HTTP 200:

```json
{
  "status": "complete",
  "events": [],
  "next_token": null
}
```

If Athena is still running after the synchronous wait window, Spool returns HTTP 202 with a `next_token`. Repeat the request with only `next_token` to poll and then page the same query.

### Get one event

`GET /api/v1/events/{event_id}`

New archived events are indexed in DynamoDB for 30 days. The lookup verifies that the indexed event belongs to the authenticated project, then returns the original JSON document from S3.

## Storage/query design

The archiver continues to write the canonical raw event object at:

```text
year=YYYY/month=MM/day=DD/hour=HH/<event_id>.json
```

Glue exposes those objects as a partition-projected table. Athena searches only metadata needed for filtering and returns `$path`; the query Lambda then reads the matching S3 objects so arbitrary `properties` are returned exactly as ingested.

Athena query results use a separate encrypted S3 bucket and expire after seven days. The workgroup enforces a 256 MiB bytes-scanned cutoff per query.

## Tenant isolation

Search and direct lookup both authenticate against the existing projects table. Athena predicates always include `payload.project_id`, direct event lookup verifies the event-index `project_id`, and pagination tokens are HMAC-signed and bound to the project that created them.
