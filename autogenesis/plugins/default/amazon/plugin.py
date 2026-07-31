"""Amazon Bedrock plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.bedrock_converse import AmazonBedrockConverseTool
from .tools.bedrock_embedding import AmazonBedrockEmbeddingTool
from .tools.bedrock_model import AmazonBedrockModelTool
from .tools.s3_bucket_uploader import AmazonS3BucketUploaderTool


@PLUGIN.register_module(force=True)
class AmazonPlugin(Plugin):
    """Amazon Bedrock tools."""

    tools = (
        AmazonBedrockConverseTool,
        AmazonBedrockEmbeddingTool,
        AmazonBedrockModelTool,
        AmazonS3BucketUploaderTool,
    )

    name: str = 'amazon'
    display_name: str = 'Amazon Bedrock'
    description: str = 'Amazon Bedrock tools.'
    category: str = 'data'
    type: str = 'model'
