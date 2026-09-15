package spool

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestTrackWire(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.URL.Path != "/dev/events" || r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("unexpected request: %v", r)
		}
		var event Event
		if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
			t.Error(err)
		}
		if event.Name != "egg_hatched" || event.Properties["species"] != "diamond" {
			t.Errorf("unexpected event: %+v", event)
		}
		w.WriteHeader(202)
		w.Write([]byte(`{"id":"abc","status":"accepted"}`))
	}))
	defer server.Close()
	c, err := New(server.URL+"/dev/events/", nil)
	if err != nil {
		t.Fatal(err)
	}
	result, err := c.Track(context.Background(), Event{Name: "egg_hatched", Properties: map[string]any{"species": "diamond"}})
	if err != nil || result.ID != "abc" {
		t.Fatalf("%+v %v", result, err)
	}
}

func TestBatchPartialFailure(t *testing.T) {
	calls := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.URL.Path != "/events/batch" {
			t.Error(r.URL.Path)
		}
		var payload struct {
			Events []map[string]any `json:"events"`
		}
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Error(err)
		}
		if len(payload.Events) != 2 {
			t.Error("wrong batch size")
		}
		for _, event := range payload.Events {
			if value, ok := event["properties"]; ok && value == nil {
				t.Error("null properties rejected by server")
			}
		}
		w.WriteHeader(202)
		w.Write([]byte(`{"accepted":1,"failed":1}`))
	}))
	defer server.Close()
	c, _ := New(server.URL+"/events", nil)
	result, err := c.TrackBatch(context.Background(), []Event{{Name: "a"}, {Name: "b"}})
	var partial *PartialFailureError
	if !errors.As(err, &partial) || result.Accepted != 1 || calls != 1 {
		t.Fatalf("%+v %v calls=%d", result, err, calls)
	}
}

func TestFailures(t *testing.T) {
	for _, tc := range []struct {
		name   string
		status int
		body   string
	}{
		{"api", 400, `{"error":"invalid JSON or event"}`},
		{"malformed", 202, `nope`},
		{"missing acceptance", 202, `{}`},
		{"redirect", 302, ``},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(tc.status); w.Write([]byte(tc.body)) }))
			defer server.Close()
			c, _ := New(server.URL+"/events", nil)
			_, err := c.Track(context.Background(), Event{Name: "a"})
			if err == nil {
				t.Fatal("expected error")
			}
			if tc.status != 202 {
				var api *APIError
				if !errors.As(err, &api) || api.StatusCode != tc.status {
					t.Fatal(err)
				}
			}
		})
	}
}

func TestBatchCounts(t *testing.T) {
	for _, tc := range []struct {
		body      string
		wantError bool
	}{
		{`{"accepted":100,"failed":0}`, false},
		{`{"accepted":99,"failed":0}`, true},
		{`{"accepted":101,"failed":-1}`, true},
		{`null`, true},
	} {
		t.Run(tc.body, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(202)
				w.Write([]byte(tc.body))
			}))
			defer server.Close()
			client, _ := New(server.URL+"/events", nil)
			events := make([]Event, 100)
			for i := range events {
				events[i].Name = "a"
			}
			_, err := client.TrackBatch(context.Background(), events)
			if (err != nil) != tc.wantError {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}

func TestValidationAndCancellation(t *testing.T) {
	c, _ := New("http://127.0.0.1:1/events", nil)
	if _, err := c.Track(context.Background(), Event{Name: "  "}); err == nil {
		t.Fatal("blank accepted")
	}
	for _, events := range [][]Event{nil, make([]Event, 101), {{Name: ""}}} {
		if _, err := c.TrackBatch(context.Background(), events); err == nil {
			t.Fatal("invalid batch accepted")
		}
	}
	if _, err := c.Track(context.Background(), Event{Name: "a", Properties: map[string]any{"bad": make(chan int)}}); err == nil {
		t.Fatal("invalid JSON accepted")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := c.Track(ctx, Event{Name: "a"}); !errors.Is(err, context.Canceled) {
		t.Fatal(err)
	}
	for _, endpoint := range []string{"", "ftp://example.com/events", "https://example.com", "https://example.com/events?x=1"} {
		if _, err := New(endpoint, nil); err == nil {
			t.Errorf("accepted %q", endpoint)
		}
	}
}
