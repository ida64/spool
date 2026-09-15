package spool

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const (
	defaultTimeout = 10 * time.Second
	MaxBatchSize   = 100
)

type Client struct {
	baseURL    string
	httpClient *http.Client
}

type Option func(*Client) error

func WithHTTPClient(httpClient *http.Client) Option {
	return func(client *Client) error {
		if httpClient == nil {
			return errors.New("spool: HTTP client cannot be nil")
		}

		client.httpClient = httpClient
		return nil
	}
}

func (c *Client) Track(
	ctx context.Context,
	event string,
	properties map[string]any,
) (*TrackResponse, error) {
	event = strings.TrimSpace(event)
	if event == "" {
		return nil, errors.New("spool: event name is required")
	}

	payload := Event{
		Name:       event,
		Properties: properties,
	}

	var response TrackResponse
	if err := c.post(ctx, "/events", payload, &response); err != nil {
		return nil, err
	}

	return &response, nil
}

func (c *Client) post(
	ctx context.Context,
	path string,
	payload any,
	result any,
) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("spool: encode request: %w", err)
	}

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.baseURL+path,
		bytes.NewReader(body),
	)
	if err != nil {
		return fmt.Errorf("spool: create request: %w", err)
	}

	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")

	response, err := c.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("spool: send request: %w", err)
	}
	defer response.Body.Close()

	responseBody, err := io.ReadAll(response.Body)
	if err != nil {
		return fmt.Errorf("spool: read response: %w", err)
	}

	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return &APIError{
			StatusCode: response.StatusCode,
			Status:     response.Status,
			Body:       strings.TrimSpace(string(responseBody)),
		}
	}
	if result == nil || len(responseBody) == 0 {
		return nil
	}

	if err := json.Unmarshal(responseBody, result); err != nil {
		return fmt.Errorf("spool: decode response: %w", err)
	}

	return nil
}

type Event struct {
	Name       string         `json:"event"`
	Properties map[string]any `json:"properties,omitempty"`
}

type TrackResponse struct {
	ID     string `json:"id"`
	Status string `json:"status"`
}

type BatchResponse struct {
	Accepted int `json:"accepted"`
	Failed   int `json:"failed"`
}

type APIError struct {
	StatusCode int
	Status     string
	Body       string
}

func (err *APIError) Error() string {
	if err.Body == "" {
		return fmt.Sprintf("spool: API returned %s", err.Status)
	}

	return fmt.Sprintf(
		"spool: API returned %s: %s",
		err.Status,
		err.Body,
	)
}

func (c *Client) TrackBatch(
	ctx context.Context,
	events []Event,
) (*BatchResponse, error) {
	if len(events) == 0 {
		return nil, errors.New("spool: batch must contain at least one event")
	}

	if len(events) > MaxBatchSize {
		return nil, fmt.Errorf(
			"spool: batch cannot contain more than %d events",
			MaxBatchSize,
		)
	}

	for index := range events {
		events[index].Name = strings.TrimSpace(events[index].Name)

		if events[index].Name == "" {
			return nil, fmt.Errorf(
				"spool: event at index %d has an empty name",
				index,
			)
		}
	}

	payload := struct {
		Events []Event `json:"events"`
	}{
		Events: events,
	}

	var response BatchResponse
	if err := c.post(ctx, "/events/batch", payload, &response); err != nil {
		return nil, err
	}

	return &response, nil
}

func NewClient(baseURL string, options ...Option) (*Client, error) {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if baseURL == "" {
		return nil, errors.New("spool: base URL is required")
	}

	client := &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: defaultTimeout,
		},
	}

	for _, option := range options {
		if option == nil {
			return nil, errors.New("spool: option cannot be nil")
		}

		if err := option(client); err != nil {
			return nil, err
		}
	}

	return client, nil
}
