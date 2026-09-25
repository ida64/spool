import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import boto3

athena = boto3.client("athena")
dynamodb = boto3.client("dynamodb")
s3 = boto3.client("s3")

RELATIVE_TIME = re.compile(r"^(\d+)([mhd])$")


def response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",
        },
        "body": json.dumps(body),
    }


def sql_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def authorize(event):
    headers = {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}
    project_id = headers.get("x-spool-project", "").strip()
    supplied = headers.get("x-spool-token", "")

    if not project_id or not supplied:
        return None

    result = dynamodb.get_item(
        TableName=os.environ["PROJECTS_TABLE_NAME"],
        Key={"project_id": {"S": project_id}},
        ConsistentRead=True,
    )
    project = result.get("Item")
    if not project or not project.get("enabled", {}).get("BOOL", False):
        return None

    supplied_hash = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
    expected_hash = project.get("token_hash", {}).get("S", "")
    if not expected_hash or not hmac.compare_digest(supplied_hash, expected_hash):
        return None

    return project_id


def parse_time(value, default):
    if not value:
        return default

    match = RELATIVE_TIME.match(value.strip().lower())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {
            "m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
        }[unit]
        return datetime.now(timezone.utc) - delta

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def hour_partition_predicate(start, end):
    current = start.replace(minute=0, second=0, microsecond=0)
    last = end.replace(minute=0, second=0, microsecond=0)
    groups = {}

    while current <= last:
        key = (current.strftime("%Y"), current.strftime("%m"), current.strftime("%d"))
        groups.setdefault(key, []).append(current.strftime("%H"))
        current += timedelta(hours=1)

    clauses = []
    for (year, month, day), hours in groups.items():
        hour_values = ", ".join(sql_quote(hour) for hour in hours)
        clauses.append(
            f"(year={sql_quote(year)} AND month={sql_quote(month)} "
            f"AND day={sql_quote(day)} AND hour IN ({hour_values}))"
        )
    return "(" + " OR ".join(clauses) + ")"


def encode_token(payload):
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    secret = os.environ["PAGINATION_SECRET"].encode("utf-8")
    signature = hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def decode_token(token, project_id):
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(
            os.environ["PAGINATION_SECRET"].encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("bad signature")

        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if payload.get("project_id") != project_id:
            raise ValueError("wrong project")
        return payload
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("invalid next_token")


def s3_uri_to_key(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError("invalid Athena result path")
    return parsed.netloc, parsed.path.lstrip("/")


def read_archived_event(path):
    bucket, key = s3_uri_to_key(path)
    if bucket != os.environ["ARCHIVE_BUCKET"]:
        raise ValueError("Athena returned an unexpected archive bucket")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read())


def wait_for_query(execution_id, timeout_seconds=8):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = athena.get_query_execution(QueryExecutionId=execution_id)
        state = result["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            return "SUCCEEDED"
        if state in {"FAILED", "CANCELLED"}:
            reason = result["QueryExecution"]["Status"].get("StateChangeReason", "query failed")
            raise RuntimeError(reason)
        time.sleep(0.2)
    return "RUNNING"


def get_query_page(execution_id, project_id, limit, athena_token=None):
    args = {
        "QueryExecutionId": execution_id,
        "MaxResults": limit + (1 if athena_token is None else 0),
    }
    if athena_token:
        args["NextToken"] = athena_token

    result = athena.get_query_results(**args)
    rows = result.get("ResultSet", {}).get("Rows", [])
    paths = []
    for row in rows:
        value = (row.get("Data") or [{}])[0].get("VarCharValue")
        if not value or value == "path":
            continue
        paths.append(value)

    events = [read_archived_event(path) for path in paths[:limit]]
    next_athena_token = result.get("NextToken")
    next_token = None
    if next_athena_token:
        next_token = encode_token({
            "execution_id": execution_id,
            "athena_token": next_athena_token,
            "project_id": project_id,
            "limit": limit,
        })

    return events, next_token


def search_events(event, project_id):
    params = event.get("queryStringParameters") or {}
    token = params.get("next_token")

    if token:
        payload = decode_token(token, project_id)
        execution_id = payload["execution_id"]
        limit = int(payload["limit"])
        state = wait_for_query(execution_id)
        if state == "RUNNING":
            return response(202, {
                "status": "running",
                "next_token": token,
                "events": [],
            })
        events, next_token = get_query_page(
            execution_id,
            project_id,
            limit,
            payload.get("athena_token"),
        )
        return response(200, {
            "status": "complete",
            "events": events,
            "next_token": next_token,
        })

    try:
        limit = int(params.get("limit") or 100)
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        now = datetime.now(timezone.utc)
        end = parse_time(params.get("until"), now)
        start = parse_time(params.get("since"), end - timedelta(hours=24))
        if start > end:
            raise ValueError("since must be before until")
        if end - start > timedelta(days=7):
            raise ValueError("search window cannot exceed 7 days")
    except (ValueError, TypeError):
        return response(400, {"error": "invalid search parameters"})

    predicates = [
        f"payload.project_id = {sql_quote(project_id)}",
        f"from_iso8601_timestamp(timestamp) >= from_iso8601_timestamp({sql_quote(start.isoformat())})",
        f"from_iso8601_timestamp(timestamp) <= from_iso8601_timestamp({sql_quote(end.isoformat())})",
        hour_partition_predicate(start, end),
    ]

    event_name = (params.get("event") or "").strip()
    stage = (params.get("stage") or "").strip()
    if event_name:
        predicates.append(f"event = {sql_quote(event_name)}")
    if stage:
        predicates.append(f"payload.stage = {sql_quote(stage)}")

    query = (
        f'SELECT "$path" AS path FROM "{os.environ["ATHENA_DATABASE"]}"."{os.environ["ATHENA_TABLE"]}" '
        f'WHERE {" AND ".join(predicates)} '
        "ORDER BY timestamp DESC LIMIT 1000"
    )

    started = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": os.environ["ATHENA_DATABASE"]},
        WorkGroup=os.environ["ATHENA_WORKGROUP"],
    )
    execution_id = started["QueryExecutionId"]
    state = wait_for_query(execution_id)

    if state == "RUNNING":
        next_token = encode_token({
            "execution_id": execution_id,
            "athena_token": None,
            "project_id": project_id,
            "limit": limit,
        })
        return response(202, {
            "status": "running",
            "events": [],
            "next_token": next_token,
        })

    events, next_token = get_query_page(execution_id, project_id, limit)
    return response(200, {
        "status": "complete",
        "events": events,
        "next_token": next_token,
    })


def get_event(event_id, project_id):
    result = dynamodb.get_item(
        TableName=os.environ["EVENT_INDEX_TABLE_NAME"],
        Key={"event_id": {"S": event_id}},
        ConsistentRead=True,
    )
    item = result.get("Item")
    if not item or item.get("project_id", {}).get("S") != project_id:
        return response(404, {"error": "event not found"})

    raw_event = read_archived_event(item["s3_uri"]["S"])
    return response(200, raw_event)


def lambda_handler(event, _context):
    project_id = authorize(event)
    if not project_id:
        return response(403, {"error": "invalid credentials"})

    path_parameters = event.get("pathParameters") or {}
    event_id = path_parameters.get("event_id")
    if event_id:
        return get_event(event_id, project_id)

    try:
        return search_events(event, project_id)
    except ValueError as error:
        return response(400, {"error": str(error)})
    except RuntimeError as error:
        return response(502, {"error": "Athena query failed", "detail": str(error)})
