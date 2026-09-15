import base64
import json
import os
import uuid
from datetime import datetime, timezone

MAX_BATCH_EVENTS = 100

import boto3

kinesis = boto3.client("kinesis")

def lambda_handler(event, _context):
    try:
        body = event.get("body") if isinstance(event, dict) else None
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body or "").decode("utf-8")

        payload = json.loads(body or "")

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
        return {"statusCode": 400, "headers": {"content-type": "application/json"}, "body": json.dumps({"error": "invalid JSON or events"})}