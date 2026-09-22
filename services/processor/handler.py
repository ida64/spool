import base64
import json
import os
import time

import boto3

dynamodb = boto3.client("dynamodb")

DEDUP_TTL_SECONDS = 7 * 24 * 60 * 60


def is_duplicate(error):
    response = getattr(error, "response", {})
    if response.get("Error", {}).get("Code") != "TransactionCanceledException":
        return False

    reasons = response.get("CancellationReasons", [])
    return bool(reasons) and reasons[0].get("Code") == "ConditionalCheckFailed"


def process_record(record):
    data = base64.b64decode(record["kinesis"]["data"])
    item = json.loads(data)
    event_id = item["id"]
    event_name = item["event"]
    stage = item.get("stage", "prod")
    expires_at = int(time.time()) + DEDUP_TTL_SECONDS

    try:
        dynamodb.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": os.environ["DEDUP_TABLE_NAME"],
                        "Item": {
                            "event_id": {"S": event_id},
                            "expires_at": {"N": str(expires_at)},
                        },
                        "ConditionExpression": "attribute_not_exists(event_id)",
                    }
                },
                {
                    "Update": {
                        "TableName": os.environ["TABLE_NAME"],
                        "Key": {"event_name": {"S": event_name}},
                        "UpdateExpression": "ADD #count :increment",
                        "ExpressionAttributeNames": {"#count": "count"},
                        "ExpressionAttributeValues": {":increment": {"N": "1"}},
                    }
                },
                {
                    "Update": {
                        "TableName": os.environ["STAGE_TABLE_NAME"],
                        "Key": {
                            "stage": {"S": stage},
                            "event_name": {"S": event_name},
                        },
                        "UpdateExpression": "ADD #count :increment",
                        "ExpressionAttributeNames": {"#count": "count"},
                        "ExpressionAttributeValues": {":increment": {"N": "1"}},
                    }
                },
            ]
        )
    except Exception as error:
        if is_duplicate(error):
            return False
        raise

    return True


def lambda_handler(event, _context):
    for record in event.get("Records", []):
        sequence_number = record["kinesis"]["sequenceNumber"]

        try:
            process_record(record)
        except Exception as error:
            print(json.dumps({
                "message": "record_processing_failed",
                "sequence_number": sequence_number,
                "error": str(error),
            }))
            return {
                "batchItemFailures": [
                    {"itemIdentifier": sequence_number}
                ]
            }

    return {"batchItemFailures": []}
