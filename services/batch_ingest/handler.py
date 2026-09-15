import base64
import json
import os
import uuid
import hmac
from datetime import datetime, timezone

MAX_BATCH_EVENTS = 100
MAX_BODY_BYTES = 256 * 1024

import boto3

kinesis = boto3.client("kinesis")


def error(status, message):
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps({"error": message})}


def authorized(event, payload):
    if not isinstance(payload, dict):
        return False
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    expected = os.environ.get("INGEST_TOKEN", "")
    supplied = headers.get("x-spool-token", "")
    if not expected or not hmac.compare_digest(str(supplied), expected):
        return False
    allowed_game_id = os.environ.get("ALLOWED_GAME_ID", "")
    return not allowed_game_id or str(payload.get("game_id", "")) == allowed_game_id

def lambda_handler(event, _context):
    try:
        body = event.get("body") if isinstance(event, dict) else None
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body or "").decode("utf-8")
        if len(body or "") > MAX_BODY_BYTES:
            return error(413, "request body too large")

        payload = json.loads(body or "")

        if not authorized(event, payload):
            return error(403, "invalid credentials or game_id")

        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise ValueError("events must be a non-empty list")

        if len(payload["events"]) == 0:
            raise ValueError("events must be a non-empty list")
        
        if len(payload["events"]) > MAX_BATCH_EVENTS:
            raise ValueError(f"events must not exceed {MAX_BATCH_EVENTS} items")

        k_events = []
        for event_item in payload["events"]:
            if not isinstance(event_item, dict) or not isinstance(event_item.get("event"), str) or not event_item["event"].strip():
                raise ValueError("each event must be a non-empty string")

            properties = event_item.get("properties", {})
            if not isinstance(properties, dict):
                raise ValueError("properties must be an object")

            event_name = event_item["event"].strip()

            record = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event_name,
                "payload": {
                    "event": event_name,
                    "properties": properties,
                },
            }
            
            k_events.append({
                "PartitionKey": record["event"],
                "Data": json.dumps(record).encode("utf-8")
            })

        response = kinesis.put_records(StreamName=os.environ["KINESIS_STREAM_NAME"], Records=k_events)
        failed = response.get("FailedRecordCount", 0)
        accepted = len(k_events) - failed

        return {"statusCode": 202, "headers": {"content-type": "application/json"}, "body": json.dumps({
            "accepted": accepted,
            "failed": failed
        })}
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return error(400, "invalid JSON or events")
