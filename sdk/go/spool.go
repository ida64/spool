// Package spool sends telemetry events to the Spool ingestion API.
package spool

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const MaxBatchEvents = 100

// Event is one telemetry event. Nil Properties are omitted from requests.
type Event struct {
	Name       string         `json:"event"`
	Properties map[string]any `json:"properties,omitempty"`
}

type Result struct {
	ID     string `json:"id"`
	Status string `json:"status"`
}

type BatchResult struct {
	Accepted int `json:"accepted"`
	Failed   int `json:"failed"`
}

// PartialFailureError means some records failed. The API does not identify
// which records failed; retrying the batch may duplicate accepted events.
type PartialFailureError struct{ Result BatchResult }

func (e *PartialFailureError) Error() string {
	return fmt.Sprintf("spool: batch accepted %d events, failed %d", e.Result.Accepted, e.Result.Failed)
}

// APIError preserves a non-202 HTTP response (body capped at 64 KiB).
type APIError struct {
	StatusCode int
	Body       string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("spool: HTTP %d: %s", e.StatusCode, e.Body)
}

// Client can be shared by goroutines. Do not mutate its HTTP client during use.
type Client struct {
	endpoint   string
	httpClient *http.Client
}

// New accepts the complete single-event URL, including /events and any stage
// prefix. A nil HTTP client selects a client with a 10-second timeout.
// Requests are never automatically retried by the SDK.
func New(eventsURL string, httpClient *http.Client) (*Client, error) {
	u, err := url.Parse(eventsURL)
	if err != nil {
		return nil, fmt.Errorf("spool: invalid events URL: %w", err)
	}
	if (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || u.ForceQuery {
		return nil, fmt.Errorf("spool: events URL must be HTTP(S), without credentials, query or fragment")
	}
	u.Path = strings.TrimRight(u.Path, "/")
	if !strings.HasSuffix(u.Path, "/events") {
		return nil, fmt.Errorf("spool: events URL must end in /events")
	}
	u.RawPath = ""
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 10 * time.Second}
	}
	// Disable redirects so a POST cannot silently change method or destination.
	copyClient := *httpClient
	copyClient.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	return &Client{endpoint: u.String(), httpClient: &copyClient}, nil
}

func validate(event Event) error {
	if strings.TrimSpace(event.Name) == "" {
		return fmt.Errorf("spool: event name must not be blank")
	}
	return nil
}

// Track submits one event. Acceptance does not mean processing is complete.
func (c *Client) Track(ctx context.Context, event Event) (Result, error) {
	var result Result
	if err := validate(event); err != nil {
		return result, err
	}
	err := c.post(ctx, c.endpoint, event, &result)
	if err == nil && (result.ID == "" || result.Status != "accepted") {
		err = fmt.Errorf("spool: invalid acceptance response")
	}
	return result, err
}

// TrackBatch submits 1–100 events. It returns both counts and an error on
// partial failure. It neither splits batches nor retries them.
func (c *Client) TrackBatch(ctx context.Context, events []Event) (BatchResult, error) {
	var result BatchResult
	if len(events) == 0 || len(events) > MaxBatchEvents {
		return result, fmt.Errorf("spool: batch must contain 1–%d events", MaxBatchEvents)
	}
	for i, event := range events {
		if err := validate(event); err != nil {
			return result, fmt.Errorf("event %d: %w", i, err)
		}
	}
	if err := c.post(ctx, c.endpoint+"/batch", struct {
		Events []Event `json:"events"`
	}{events}, &result); err != nil {
		return result, err
	}
	if result.Accepted < 0 || result.Failed < 0 || result.Accepted+result.Failed != len(events) {
		return result, fmt.Errorf("spool: invalid batch response counts")
	}
	if result.Failed > 0 {
		return result, &PartialFailureError{Result: result}
	}
	return result, nil
}

func (c *Client) post(ctx context.Context, endpoint string, payload, result any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("spool: encode request: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("spool: create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("spool: send request: %w", err)
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 65537))
	if err != nil {
		return fmt.Errorf("spool: read response: %w", err)
	}
	if resp.StatusCode != http.StatusAccepted {
		if len(data) > 65536 {
			data = data[:65536]
		}
		return &APIError{StatusCode: resp.StatusCode, Body: string(data)}
	}
	if len(data) > 65536 {
		return fmt.Errorf("spool: response exceeds 64 KiB")
	}
	if err := json.Unmarshal(data, result); err != nil {
		return fmt.Errorf("spool: decode response: %w", err)
	}
	return nil
}
