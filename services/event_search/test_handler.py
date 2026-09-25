import importlib.util
import json
import os
import sys
import types
import unittest
from unittest.mock import Mock

athena = Mock()
dynamodb = Mock()
s3 = Mock()

boto3 = types.ModuleType("boto3")
boto3.client = Mock(side_effect=lambda name: {
    "athena": athena,
    "dynamodb": dynamodb,
    "s3": s3,
}[name])
sys.modules["boto3"] = boto3

spec = importlib.util.spec_from_file_location(
    "event_search_handler",
    os.path.join(os.path.dirname(__file__), "handler.py"),
)
handler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler)


class EventSearchTests(unittest.TestCase):
    def setUp(self):
        athena.reset_mock()
        dynamodb.reset_mock()
        dynamodb.get_item.side_effect = None
        s3.reset_mock()

        os.environ["PROJECTS_TABLE_NAME"] = "projects"
        os.environ["EVENT_INDEX_TABLE_NAME"] = "event-index"
        os.environ["ARCHIVE_BUCKET"] = "archive"
        os.environ["ATHENA_DATABASE"] = "spool"
        os.environ["ATHENA_TABLE"] = "events"
        os.environ["ATHENA_WORKGROUP"] = "spool"
        os.environ["PAGINATION_SECRET"] = "secret"

        token_hash = handler.hashlib.sha256(b"token").hexdigest()
        dynamodb.get_item.return_value = {
            "Item": {
                "project_id": {"S": "default"},
                "token_hash": {"S": token_hash},
                "enabled": {"BOOL": True},
            }
        }

    def request(self, query=None, path=None):
        return {
            "headers": {
                "X-Spool-Project": "default",
                "X-Spool-Token": "token",
            },
            "queryStringParameters": query or {},
            "pathParameters": path or {},
        }

    def test_rejects_invalid_credentials(self):
        dynamodb.get_item.return_value = {}
        result = handler.lambda_handler(self.request(), None)
        self.assertEqual(result["statusCode"], 403)

    def test_search_builds_project_scoped_partition_pruned_query(self):
        athena.start_query_execution.return_value = {"QueryExecutionId": "q-1"}
        athena.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "SUCCEEDED"}}
        }
        athena.get_query_results.return_value = {
            "ResultSet": {
                "Rows": [
                    {"Data": [{"VarCharValue": "path"}]},
                    {"Data": [{"VarCharValue": "s3://archive/year=2026/month=09/day=25/hour=03/e.json"}]},
                ]
            }
        }
        s3.get_object.return_value = {
            "Body": types.SimpleNamespace(read=lambda: b'{"id":"e","event":"player_error","payload":{"project_id":"default"}}')
        }

        result = handler.lambda_handler(
            self.request({
                "event": "player_error",
                "stage": "production",
                "since": "2h",
                "limit": "25",
            }),
            None,
        )

        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body["events"][0]["id"], "e")

        query = athena.start_query_execution.call_args.kwargs["QueryString"]
        self.assertIn("payload.project_id = 'default'", query)
        self.assertIn("event = 'player_error'", query)
        self.assertIn("payload.stage = 'production'", query)
        self.assertIn("year=", query)
        self.assertIn("hour IN", query)

    def test_rejects_search_windows_over_seven_days(self):
        result = handler.lambda_handler(
            self.request({"since": "8d"}),
            None,
        )
        self.assertEqual(result["statusCode"], 400)
        athena.start_query_execution.assert_not_called()

    def test_event_lookup_is_project_scoped(self):
        auth_item = dynamodb.get_item.return_value
        dynamodb.get_item.side_effect = [
            auth_item,
            {
                "Item": {
                    "event_id": {"S": "event-1"},
                    "project_id": {"S": "other"},
                    "s3_uri": {"S": "s3://archive/x.json"},
                }
            },
        ]
        result = handler.lambda_handler(
            self.request(path={"event_id": "event-1"}),
            None,
        )
        self.assertEqual(result["statusCode"], 404)
        s3.get_object.assert_not_called()

    def test_pagination_tokens_cannot_cross_projects(self):
        token = handler.encode_token({
            "execution_id": "q-1",
            "athena_token": "next",
            "project_id": "default",
            "limit": 20,
        })
        with self.assertRaises(ValueError):
            handler.decode_token(token, "other")


if __name__ == "__main__":
    unittest.main()
