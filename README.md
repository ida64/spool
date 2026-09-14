# spool

Minimal telemetry pipeline:

`POST /events → API Gateway → ingest Lambda → Kinesis → processor Lambda → DynamoDB`

## Setup

Requirements: AWS credentials configured for Terraform, Terraform >= 1.5, and permission to create the listed AWS resources.

```sh
cd infra
terraform init
terraform plan
terraform apply
```

The default region is `us-east-1`; override it with `terraform apply -var='aws_region=us-west-2'`.

## Send an event

```sh
curl -X POST "$(terraform output -raw api_endpoint)" \
  -H 'content-type: application/json' \
  -d '{"event_name":"signup","user_id":"user-123"}'
```

The API returns `202` and a generated event ID. Invalid JSON or a missing/empty `event_name` returns `400`.

## Verify

Allow a few seconds for Kinesis and Lambda processing, then inspect the count:

```sh
aws dynamodb get-item \
  --table-name "$(terraform output -raw dynamodb_table_name)" \
  --key '{"event_name":{"S":"signup"}}'
```

The response contains an atomic `count` attribute. Lambda logs are available with:

```sh
aws logs tail "/aws/lambda/$(terraform output -raw processor_lambda_name)" --follow
```

## Cleanup

```sh
terraform destroy
```

