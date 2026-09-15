# Spool Go SDK

Dependency-free Go client for single and batch telemetry ingestion. Requires Go 1.20+.

Once this SDK is merged into the repository:

```sh
go get github.com/ida64/spool/sdk/go
```

```go
package main

import (
    "context"
    "log"
    "os"

    spool "github.com/ida64/spool/sdk/go"
)

func main() {
    // Complete URL, e.g. https://API_ID.execute-api.us-east-1.amazonaws.com/dev/events
    client, err := spool.New(os.Getenv("SPOOL_EVENTS_URL"), nil)
    if err != nil { log.Fatal(err) }

    result, err := client.Track(context.Background(), spool.Event{
        Name: "egg_hatched",
        Properties: map[string]any{"species": "diamond"},
    })
    if err != nil { log.Fatal(err) }
    log.Println(result.ID, result.Status)

    batch, err := client.TrackBatch(context.Background(), []spool.Event{
        {Name: "player_joined"},
        {Name: "item_purchased", Properties: map[string]any{"item": "egg"}},
    })
    if err != nil { log.Fatalf("batch counts=%+v: %v", batch, err) }
    log.Println(batch.Accepted)
}
```

- `New` takes the `/events` endpoint, preserving stage prefixes. Batch calls append `/batch`.
- The default HTTP timeout is 10 seconds. Pass a custom `*http.Client` to configure transport/timeouts. Redirects are disabled.
- Both methods accept a context for cancellation and deadlines.
- Batches must contain 1–100 events. Nil properties are omitted, not sent as JSON null.
- Use `errors.As` with `*spool.APIError` to inspect HTTP errors, or `*spool.PartialFailureError` to inspect partial batch failures. Batch counts are also returned alongside the error.
- No automatic retries: Spool generates IDs server-side and does not deduplicate. A partial failure does not identify failed records; retrying can double-count accepted events. A timeout may also occur after acceptance.
- HTTP 202 means accepted for ingestion, not fully processed into DynamoDB.

Run tests locally without AWS:

```sh
cd sdk/go
go test -race ./...
go vet ./...
```
