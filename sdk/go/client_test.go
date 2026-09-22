package spool

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestTrack(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			if request.Method != http.MethodPost {
				t.Errorf("method = %q, want POST", request.Method)
			}

			if request.URL.Path != "/events" {
				t.Errorf("path = %q, want /events", request.URL.Path)
			}

			if request.Header.Get("Content-Type") != "application/json" {
				t.Errorf(
					"Content-Type = %q, want application/json",
					request.Header.Get("Content-Type"),
				)
			}

			var event Event
			if err := json.NewDecoder(request.Body).Decode(&event); err != nil {
				t.Errorf("decode request: %v", err)
			}

			if event.Name != "egg_hatched" {
				t.Errorf("event name = %q, want egg_hatched", event.Name)
			}

			if event.Properties["species"] != "diamond" {
				t.Errorf(
					"species = %v, want diamond",
					event.Properties["species"],
				)
			}

			writer.Header().Set("Content-Type", "application/json")
			writer.WriteHeader(http.StatusAccepted)
			_, _ = writer.Write([]byte(
				`{"id":"event-123","status":"accepted"}`,
			))
		},
	))
	defer server.Close()

	client, err := NewClient(server.URL)
	if err != nil {
		t.Fatalf("NewClient returned an error: %v", err)
	}

	response, err := client.Track(
		context.Background(),
		"egg_hatched",
		map[string]any{
			"species": "diamond",
		},
	)
	if err != nil {
		t.Fatalf("Track returned an error: %v", err)
	}

	if response.ID != "event-123" {
		t.Errorf("response ID = %q, want event-123", response.ID)
	}

	if response.Status != "accepted" {
		t.Errorf("response status = %q, want accepted", response.Status)
	}
}

func TestTrackBatch(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			if request.URL.Path != "/events/batch" {
				t.Errorf(
					"path = %q, want /events/batch",
					request.URL.Path,
				)
			}

			var payload struct {
				Events []Event `json:"events"`
			}

			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				t.Errorf("decode request: %v", err)
			}

			if len(payload.Events) != 2 {
				t.Errorf(
					"event count = %d, want 2",
					len(payload.Events),
				)
			}

			writer.Header().Set("Content-Type", "application/json")
			writer.WriteHeader(http.StatusAccepted)
			_, _ = writer.Write([]byte(`{"accepted":2,"failed":0}`))
		},
	))
	defer server.Close()

	client, err := NewClient(server.URL)
	if err != nil {
		t.Fatalf("NewClient returned an error: %v", err)
	}

	response, err := client.TrackBatch(
		context.Background(),
		[]Event{
			{Name: "player_joined"},
			{Name: "item_purchased"},
		},
	)
	if err != nil {
		t.Fatalf("TrackBatch returned an error: %v", err)
	}

	if response.Accepted != 2 {
		t.Errorf("accepted = %d, want 2", response.Accepted)
	}

	if response.Failed != 0 {
		t.Errorf("failed = %d, want 0", response.Failed)
	}
}

func TestTrackRejectsEmptyName(t *testing.T) {
	client, err := NewClient("https://example.com")
	if err != nil {
		t.Fatalf("NewClient returned an error: %v", err)
	}

	_, err = client.Track(context.Background(), "   ", nil)
	if err == nil {
		t.Fatal("Track returned nil error for an empty event name")
	}
}


func TestTrackBatchDoesNotMutateInput(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			var payload struct {
				Events []Event `json:"events"`
			}

			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				t.Errorf("decode request: %v", err)
			}

			if got := payload.Events[0].Name; got != "player_joined" {
				t.Errorf("normalized event name = %q, want player_joined", got)
			}

			writer.Header().Set("Content-Type", "application/json")
			writer.WriteHeader(http.StatusAccepted)
			_, _ = writer.Write([]byte(`{"accepted":1,"failed":0}`))
		},
	))
	defer server.Close()

	client, err := NewClient(server.URL)
	if err != nil {
		t.Fatalf("NewClient returned an error: %v", err)
	}

	events := []Event{{Name: "  player_joined  "}}
	_, err = client.TrackBatch(context.Background(), events)
	if err != nil {
		t.Fatalf("TrackBatch returned an error: %v", err)
	}

	if got := events[0].Name; got != "  player_joined  " {
		t.Errorf("TrackBatch mutated input event name to %q", got)
	}
}

func TestTrackBatchRejectsTooManyEvents(t *testing.T) {
	client, err := NewClient("https://example.com")
	if err != nil {
		t.Fatalf("NewClient returned an error: %v", err)
	}

	events := make([]Event, MaxBatchSize+1)
	for index := range events {
		events[index] = Event{Name: "test_event"}
	}

	_, err = client.TrackBatch(context.Background(), events)
	if err == nil {
		t.Fatal("TrackBatch returned nil error for an oversized batch")
	}
}

func TestAPIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, _ *http.Request) {
			writer.WriteHeader(http.StatusBadRequest)
			_, _ = writer.Write([]byte(
				`{"error":"invalid JSON or event"}`,
			))
		},
	))
	defer server.Close()

	client, err := NewClient(server.URL)
	if err != nil {
		t.Fatalf("NewClient returned an error: %v", err)
	}

	_, err = client.Track(context.Background(), "test_event", nil)
	if err == nil {
		t.Fatal("Track returned nil error for an API failure")
	}

	var apiError *APIError
	if !errors.As(err, &apiError) {
		t.Fatalf("error type = %T, want *APIError", err)
	}

	if apiError.StatusCode != http.StatusBadRequest {
		t.Errorf(
			"status code = %d, want %d",
			apiError.StatusCode,
			http.StatusBadRequest,
		)
	}

	if apiError.Status != "400 Bad Request" {
		t.Errorf(
			"status = %q, want 400 Bad Request",
			apiError.Status,
		)
	}

	if apiError.Body != `{"error":"invalid JSON or event"}` {
		t.Errorf("body = %q, want API error JSON", apiError.Body)
	}
}

func TestWithHTTPClient(t *testing.T) {
	httpClient := &http.Client{
		Timeout: 30 * time.Second,
	}

	client, err := NewClient(
		"https://example.com/",
		WithHTTPClient(httpClient),
	)
	if err != nil {
		t.Fatalf("NewClient returned an error: %v", err)
	}

	if client.httpClient != httpClient {
		t.Fatal("NewClient did not use the configured HTTP client")
	}

	if client.baseURL != "https://example.com" {
		t.Errorf(
			"base URL = %q, want https://example.com",
			client.baseURL,
		)
	}
}

func TestWithNilHTTPClient(t *testing.T) {
	_, err := NewClient(
		"https://example.com",
		WithHTTPClient(nil),
	)
	if err == nil {
		t.Fatal("NewClient accepted a nil HTTP client")
	}
}
