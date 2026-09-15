import base64
import json
import os
import uuid
import hmac
from datetime import datetime, timezone

import boto3

kinesis = boto3.client("kinesis")

MAX_BODY_BYTES = 64 * 1024


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
        if not isinstance(payload, dict) or not isinstance(payload.get("event"), str) or not payload["event"].strip():
            raise ValueError("event must be a non-empty string")
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return error(400, "invalid JSON or event")

    record = {"id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), "event": payload["event"], "payload": payload}
    kinesis.put_record(StreamName=os.environ["KINESIS_STREAM_NAME"], PartitionKey=record["event"], Data=json.dumps(record).encode("utf-8"))
    return {"statusCode": 202, "headers": {"content-type": "application/json"}, "body": json.dumps({"id": record["id"], "status": "accepted"})}
