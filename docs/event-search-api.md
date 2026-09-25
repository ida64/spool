# Event Search API

Initial implementation plan for querying archived Spool telemetry.

## Scope

- Add `GET /api/v1/events/search`.
- Query archived S3 events through Athena.
- Use partition projection for the existing `year/month/day/hour` archive layout.
- Scope every query to the authenticated Spool project.
- Support filters for event name, stage, time range, and result limit.
- Return a pagination token for larger result sets.
- Add `GET /api/v1/events/{event_id}` for direct event lookup.
- Add Terraform for Athena/Glue resources and Lambda permissions.
- Add unit/integration coverage for query validation and project isolation.

This document exists to bootstrap the draft PR; implementation will replace or expand it as the feature lands.
