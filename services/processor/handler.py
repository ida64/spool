import base64
import json
import os

import boto3

dynamodb = boto3.client("dynamodb")


def lambda_handler(event, _context):
    for record in event.get("Records", []):
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
    return {"processed": len(event.get("Records", []))}

