import json
import os
from datetime import datetime, timedelta, timezone

import boto3

dynamodb = boto3.client("dynamodb")


def response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",
        },
        "body": json.dumps(body),
    }


def parse_window(params):
    interval = (params.get("interval") or "hour").lower()
    if interval not in {"hour", "day"}:
        raise ValueError("interval must be hour or day")

    limit = int(params.get("limit") or (24 if interval == "hour" else 30))
    if limit < 1 or limit > 168:
        raise ValueError("limit must be between 1 and 168")

    return interval, limit


def lambda_handler(event, _context):
    event_name = (event.get("pathParameters") or {}).get("event")
    if not event_name:
        return response(400, {"error": "event path parameter is required"})

    params = event.get("queryStringParameters") or {}

    try:
        interval, limit = parse_window(params)
    except (ValueError, TypeError):
        return response(400, {"error": "invalid interval or limit"})

    now = datetime.now(timezone.utc)
    if interval == "hour":
        start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=limit - 1)
        start_bucket = start.strftime("hour#%Y-%m-%dT%H:00:00Z")
        prefix = "hour#"
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=limit - 1)
        start_bucket = start.strftime("day#%Y-%m-%d")
        prefix = "day#"

    result = dynamodb.query(
        TableName=os.environ["BUCKET_TABLE_NAME"],
        KeyConditionExpression="event_name = :event_name AND bucket >= :start_bucket",
        ExpressionAttributeValues={
            ":event_name": {"S": event_name},
            ":start_bucket": {"S": start_bucket},
        },
        ScanIndexForward=True,
    )

    points = [
        {
            "bucket": item["bucket"]["S"].removeprefix(prefix),
            "count": int(item.get("count", {}).get("N", "0")),
        }
        for item in result.get("Items", [])
        if item["bucket"]["S"].startswith(prefix)
    ]

    return response(200, {
        "event": event_name,
        "interval": interval,
        "points": points[-limit:],
    })
