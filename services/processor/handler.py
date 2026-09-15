import base64
import json
import os

import boto3

dynamodb = boto3.client("dynamodb")


def process_record(record):
    data = base64.b64decode(record["kinesis"]["data"])
    item = json.loads(data)
    event_name = item["event"]

    dynamodb.update_item(
        TableName=os.environ["TABLE_NAME"],
        Key={"event_name": {"S": event_name}},
        UpdateExpression="ADD #count :increment",
        ExpressionAttributeNames={"#count": "count"},
        ExpressionAttributeValues={":increment": {"N": "1"}},
    )


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
