import base64
import json
import os
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")


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

    return {"archived": len(event.get("Records", []))}
