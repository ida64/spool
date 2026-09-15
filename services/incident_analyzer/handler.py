import json
from datetime import datetime, timedelta

import boto3

logs = boto3.client("logs")
bedrock = boto3.client("bedrock-runtime")

MODEL_ID = "us.amazon.nova-2-lite-v1:0"

def get_function_name(alarm):
    dimensions = alarm.get("Trigger", {}).get("Dimensions", [])

    for dimension in dimensions:
        if dimension.get("name") == "FunctionName":
            return dimension.get("value")

    return None

def get_evidence(function_name, state_change):
    start = state_change - timedelta(minutes=10)

    response = logs.filter_log_events(
        logGroupName=f"/aws/lambda/{function_name}",
        startTime=int(start.timestamp() * 1000),
        endTime=int(state_change.timestamp() * 1000),
        limit=100,
    )

    evidence = []

    for item in response.get("events", []):
        message = item["message"].strip()

        # Skip routine Lambda runtime noise.
        if (
            message.startswith("START RequestId:")
            or message.startswith("END RequestId:")
            or message.startswith("REPORT RequestId:")
            or message.startswith("INIT_START")
        ):
            continue

        evidence.append({
            "timestamp": item["timestamp"],
            "message": message,
        })

    return evidence


def analyze_incident(incident, function_name, evidence):
    context = {
        "alarm": incident.get("AlarmName"),
        "function": function_name,
        "reason": incident.get("NewStateReason"),
        "state_change_time": incident.get("StateChangeTime"),
        "evidence": evidence,
    }

    prompt = f"""
You are an incident analysis system for a distributed application.

Analyze the following incident using ONLY the supplied evidence.

Return a concise technical analysis containing:

1. Severity
2. Summary
3. Likely root cause
4. Impact
5. Supporting evidence
6. Recommended investigation or remediation steps

Do not invent facts that are not supported by the alarm or logs.
If the evidence is insufficient, explicitly say so.

Incident:

{json.dumps(context, indent=2)}
"""

    response = bedrock.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt
                    }
                ],
            }
        ],
        inferenceConfig={
            "maxTokens": 1000,
            "temperature": 0.1,
        },
    )

    return response["output"]["message"]["content"][0]["text"]


def lambda_handler(event, _context):
    for record in event.get("Records", []):
        sns = record.get("Sns", {})
        incident = json.loads(sns.get("Message", "{}"))

        if incident.get("NewStateValue") != "ALARM":
            continue

        function_name = get_function_name(incident)

        if not function_name:
            raise ValueError(
                "Alarm does not contain a FunctionName dimension"
            )

        state_change = datetime.strptime(
            incident["StateChangeTime"],
            "%Y-%m-%dT%H:%M:%S.%f%z",
        )

        evidence = get_evidence(
            function_name,
            state_change,
        )

        analysis = analyze_incident(
            incident,
            function_name,
            evidence,
        )

        print(json.dumps({
            "message": "incident_analyzed",
            "alarm": incident["AlarmName"],
            "function": function_name,
            "evidence_count": len(evidence),
            "analysis": analysis,
        }))

    return {
        "statusCode": 200
    }