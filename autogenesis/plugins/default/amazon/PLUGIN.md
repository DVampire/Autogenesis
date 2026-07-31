---
id: amazon
name: Amazon Bedrock
category: data
type: model
icon: resources/icon.svg
tools: 4
implemented: 4
credentials: [AWS_ACCESS_KEY_ID, AWS_REGION, AWS_SECRET_ACCESS_KEY]
requirements: [boto3, langchain_aws, langchain_openai]
version: "1.0.0"
---
# Amazon Bedrock

Amazon Bedrock tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `amazon.amazon_bedrock_converse` | Amazon Bedrock Converse | ✅ | Amazon Bedrock Converse |
| `amazon.amazon_bedrock_embedding` | Amazon Bedrock Embeddings | ✅ | Generate embeddings using Amazon Bedrock models. |
| `amazon.amazon_bedrock_model` | Amazon Bedrock | ✅ | Amazon Bedrock |
| `amazon.s3_bucket_uploader` | S3 Bucket Uploader | ✅ | Uploads files to S3 bucket. |

All 4 tools are implemented.

## Credentials

`AWS_ACCESS_KEY_ID`, `AWS_REGION`, `AWS_SECRET_ACCESS_KEY`, an `api_key` argument on the call, or a `amazon_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
