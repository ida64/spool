import base64
import json
import os
import time
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.client("dynamodb")

EVENT_INDEX_TTL_SECONDS = 30 * 24 * 60 * 60


def lambda_handler(event, _context):
    bucket = os.environ["ARCHIVE_BUCKET"]

    for record in event.get("Records", []):
        item = json.loads(base64.b64decode(record["kinesis"]["data"]))
        timestamp = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc)
        event_id = item["id"]
        key = (
            f"year={timestamp:%Y}/month={timestamp:%m}/day={timestamp:%d}/"
            f"hour={timestamp:%H}/{event_id}.json"
        )

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=(json.dumps(item, separators=(",", ":")) + "\n").encode("utf-8"),
            ContentType="application/x-ndjson",
        )

        project_id = str((item.get("payload") or {}).get("project_id", "")).strip()
        if project_id:
            dynamodb.put_item(
                TableName=os.environ["EVENT_INDEX_TABLE_NAME"],
                Item={
                    "event_id": {"S": event_id},
                    "project_id": {"S": project_id},
                    "s3_uri": {"S": f"s3://{bucket}/{key}"},
                    "expires_at": {"N": str(int(time.time()) + EVENT_INDEX_TTL_SECONDS)},
                },
            )

    return {"archived": len(event.get("Records", []))}
