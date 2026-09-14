import base64
import json
import os
import uuid
from datetime import datetime, timezone

import boto3

kinesis = boto3.client("kinesis")


def lambda_handler(event, _context):
    try:
        body = event.get("body") if isinstance(event, dict) else None
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body or "").decode("utf-8")
        payload = json.loads(body or "")
        if not isinstance(payload, dict) or not isinstance(payload.get("event"), str) or not payload["event"].strip():
            raise ValueError("event must be a non-empty string")
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return {"statusCode": 400, "headers": {"content-type": "application/json"}, "body": json.dumps({"error": "invalid JSON or event"})}

    record = {"id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), "event": payload["event"], "payload": payload}
    kinesis.put_record(StreamName=os.environ["KINESIS_STREAM_NAME"], PartitionKey=record["event"], Data=json.dumps(record).encode("utf-8"))
    return {"statusCode": 202, "headers": {"content-type": "application/json"}, "body": json.dumps({"id": record["id"], "status": "accepted"})}

