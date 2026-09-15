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


def record(sequence_number, event_name):
    payload = base64.b64encode(
        json.dumps({"event": event_name}).encode("utf-8")
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
        dynamodb.update_item.side_effect = None
        os.environ["TABLE_NAME"] = "event-counts"

    def test_reports_no_failures_when_every_record_is_processed(self):
        response = handler.lambda_handler(
            {"Records": [record("1", "egg_hatched"), record("2", "egg_hatched")]},
            None,
        )

        self.assertEqual(response, {"batchItemFailures": []})
        self.assertEqual(dynamodb.update_item.call_count, 2)

    def test_reports_first_failed_record_and_stops_processing(self):
        dynamodb.update_item.side_effect = RuntimeError("write failed")

        response = handler.lambda_handler(
            {"Records": [record("10", "egg_hatched"), record("11", "purchase")]},
            None,
        )

        self.assertEqual(
            response,
            {"batchItemFailures": [{"itemIdentifier": "10"}]},
        )
        self.assertEqual(dynamodb.update_item.call_count, 1)


if __name__ == "__main__":
    unittest.main()
