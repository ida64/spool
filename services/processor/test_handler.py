import base64
import importlib.util
import json
import os
import sys
import types
import unittest
from unittest.mock import Mock


dynamodb = Mock()
boto3 = types.ModuleType("boto3")
boto3.client = Mock(return_value=dynamodb)
sys.modules["boto3"] = boto3

spec = importlib.util.spec_from_file_location(
    "processor_handler",
    os.path.join(os.path.dirname(__file__), "handler.py"),
)
handler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler)


def record(sequence_number, event_name, event_id=None):
    payload = base64.b64encode(
        json.dumps({
            "id": event_id or f"event-{sequence_number}",
            "event": event_name,
        }).encode("utf-8")
    ).decode("utf-8")
    return {
        "kinesis": {
            "sequenceNumber": sequence_number,
            "data": payload,
        }
    }


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        dynamodb.reset_mock()
        dynamodb.transact_write_items.side_effect = None
        os.environ["TABLE_NAME"] = "event-counts"
        os.environ["DEDUP_TABLE_NAME"] = "processed-events"

    def test_reports_no_failures_when_every_record_is_processed(self):
        response = handler.lambda_handler(
            {"Records": [record("1", "egg_hatched"), record("2", "egg_hatched")]},
            None,
        )

        self.assertEqual(response, {"batchItemFailures": []})
        self.assertEqual(dynamodb.transact_write_items.call_count, 2)

    def test_reports_first_failed_record_and_stops_processing(self):
        dynamodb.transact_write_items.side_effect = RuntimeError("write failed")

        response = handler.lambda_handler(
            {"Records": [record("10", "egg_hatched"), record("11", "purchase")]},
            None,
        )

        self.assertEqual(
            response,
            {"batchItemFailures": [{"itemIdentifier": "10"}]},
        )
        self.assertEqual(dynamodb.transact_write_items.call_count, 1)

    def test_duplicate_event_is_treated_as_success_without_incrementing(self):
        duplicate = RuntimeError("duplicate")
        duplicate.response = {
            "Error": {"Code": "TransactionCanceledException"},
            "CancellationReasons": [
                {"Code": "ConditionalCheckFailed"},
                {"Code": "None"},
            ],
        }
        dynamodb.transact_write_items.side_effect = [None, duplicate]

        response = handler.lambda_handler(
            {
                "Records": [
                    record("20", "egg_hatched", "same-id"),
                    record("21", "egg_hatched", "same-id"),
                ]
            },
            None,
        )

        self.assertEqual(response, {"batchItemFailures": []})
        self.assertEqual(dynamodb.transact_write_items.call_count, 2)


if __name__ == "__main__":
    unittest.main()
