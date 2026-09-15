# Spool Go SDK

## Create client

```go
client, err := spool.NewClient(
	"https://example.execute-api.us-east-1.amazonaws.com/dev",
)
if err != nil {
	log.Fatal(err)
}
```

## Send an event

```go
response, err := client.Track(
	context.Background(),
	"egg_hatched",
	map[string]any{
		"species": "diamond",
		"level":   12,
	},
)
if err != nil {
	log.Fatal(err)
}

fmt.Printf("event %s is %s\n", response.ID, response.Status)
```

## Send a batch

Spool accepts up to 100 events in one batch:

```go
response, err := client.TrackBatch(
	context.Background(),
	[]spool.Event{
		{
			Name: "player_joined",
			Properties: map[string]any{
				"player_id": "123",
			},
		},
		{
			Name: "item_purchased",
			Properties: map[string]any{
				"item":  "diamond_egg",
				"price": 500,
			},
		},
	},
)
if err != nil {
	log.Fatal(err)
}

fmt.Printf(
	"accepted=%d failed=%d\n",
	response.Accepted,
	response.Failed,
)
```

## Custom HTTP client

```go
client, err := spool.NewClient(
	endpoint,
	spool.WithHTTPClient(&http.Client{
		Timeout: 30 * time.Second,
	}),
)
```