"""Default plugins — one package per outside service.

Imported explicitly, the same way ``tool/default`` lists its tools: the
import is what runs each package's ``@PLUGIN.register_module`` decorator, so
this file is the registry's manifest. Adding a plugin means adding a line.
"""

from .agentql import AgentqlPlugin
from .aiml import AimlPlugin
from .altk import AltkPlugin
from .amazon import AmazonPlugin
from .anthropic import AnthropicPlugin
from .apify import ApifyPlugin
from .arxiv import ArxivPlugin
from .assemblyai import AssemblyaiPlugin
from .azure import AzurePlugin
from .baidu import BaiduPlugin
from .bing import BingPlugin
from .chroma import ChromaPlugin
from .cleanlab import CleanlabPlugin
from .clickhouse import ClickhousePlugin
from .cloudflare import CloudflarePlugin
from .codeagents import CodeagentsPlugin
from .cohere import CoherePlugin
from .cometapi import CometapiPlugin
from .composio import ComposioPlugin
from .confluence import ConfluencePlugin
from .couchbase import CouchbasePlugin
from .cuga import CugaPlugin
from .datastax import DatastaxPlugin
from .deepseek import DeepseekPlugin
from .docling import DoclingPlugin
from .duckduckgo import DuckduckgoPlugin
from .elastic import ElasticPlugin
from .empiriolabs import EmpiriolabsPlugin
from .exa import ExaPlugin
from .faiss import FaissPlugin
from .fmp import FMPPlugin
from .firecrawl import FirecrawlPlugin
from .git import GitPlugin
from .glean import GleanPlugin
from .google import GooglePlugin
from .groq import GroqPlugin
from .homeassistant import HomeassistantPlugin
from .huggingface import HuggingfacePlugin
from .ibm import IbmPlugin
from .icosacomputing import IcosacomputingPlugin
from .jigsawstack import JigsawstackPlugin
from .langwatch import LangwatchPlugin
from .litellm import LitellmPlugin
from .lmstudio import LmstudioPlugin
from .maritalk import MaritalkPlugin
from .mem0 import Mem0Plugin
from .milvus import MilvusPlugin
from .mistral import MistralPlugin
from .mongodb import MongodbPlugin
from .needle import NeedlePlugin
from .nextplaid import NextplaidPlugin
from .notdiamond import NotdiamondPlugin
from .notion import NotionPlugin
from .novita import NovitaPlugin
from .nvidia import NvidiaPlugin
from .olivya import OlivyaPlugin
from .ollama import OllamaPlugin
from .openai import OpenaiPlugin
from .openrouter import OpenrouterPlugin
from .oracle import OraclePlugin
from .paddle import PaddlePlugin
from .perplexity import PerplexityPlugin
from .pgvector import PgvectorPlugin
from .pinecone import PineconePlugin
from .qdrant import QdrantPlugin
from .redis import RedisPlugin
from .sambanova import SambanovaPlugin
from .scrapegraph import ScrapegraphPlugin
from .searchapi import SearchapiPlugin
from .serpapi import SerpapiPlugin
from .spider import SpiderPlugin
from .supabase import SupabasePlugin
from .tavily import TavilyPlugin
from .twelvelabs import TwelvelabsPlugin
from .unstructured import UnstructuredPlugin
from .upstash import UpstashPlugin
from .valkey import ValkeyPlugin
from .vectara import VectaraPlugin
from .vertexai import VertexaiPlugin
from .vlmrun import VlmrunPlugin
from .weaviate import WeaviatePlugin
from .wikipedia import WikipediaPlugin
from .wolframalpha import WolframalphaPlugin
from .xai import XaiPlugin
from .yahoo import YahooPlugin
from .yahoosearch import YahoosearchPlugin
from .youtube import YoutubePlugin
from .zep import ZepPlugin

__all__ = [
    "AgentqlPlugin",
    "AimlPlugin",
    "AltkPlugin",
    "AmazonPlugin",
    "AnthropicPlugin",
    "ApifyPlugin",
    "ArxivPlugin",
    "AssemblyaiPlugin",
    "AzurePlugin",
    "BaiduPlugin",
    "BingPlugin",
    "ChromaPlugin",
    "CleanlabPlugin",
    "ClickhousePlugin",
    "CloudflarePlugin",
    "CodeagentsPlugin",
    "CoherePlugin",
    "CometapiPlugin",
    "ComposioPlugin",
    "ConfluencePlugin",
    "CouchbasePlugin",
    "CugaPlugin",
    "DatastaxPlugin",
    "DeepseekPlugin",
    "DoclingPlugin",
    "DuckduckgoPlugin",
    "ElasticPlugin",
    "EmpiriolabsPlugin",
    "ExaPlugin",
    "FaissPlugin",
    "FirecrawlPlugin",
    "FMPPlugin",
    "GitPlugin",
    "GleanPlugin",
    "GooglePlugin",
    "GroqPlugin",
    "HomeassistantPlugin",
    "HuggingfacePlugin",
    "IbmPlugin",
    "IcosacomputingPlugin",
    "JigsawstackPlugin",
    "LangwatchPlugin",
    "LitellmPlugin",
    "LmstudioPlugin",
    "MaritalkPlugin",
    "Mem0Plugin",
    "MilvusPlugin",
    "MistralPlugin",
    "MongodbPlugin",
    "NeedlePlugin",
    "NextplaidPlugin",
    "NotdiamondPlugin",
    "NotionPlugin",
    "NovitaPlugin",
    "NvidiaPlugin",
    "OlivyaPlugin",
    "OllamaPlugin",
    "OpenaiPlugin",
    "OpenrouterPlugin",
    "OraclePlugin",
    "PaddlePlugin",
    "PerplexityPlugin",
    "PgvectorPlugin",
    "PineconePlugin",
    "QdrantPlugin",
    "RedisPlugin",
    "SambanovaPlugin",
    "ScrapegraphPlugin",
    "SearchapiPlugin",
    "SerpapiPlugin",
    "SpiderPlugin",
    "SupabasePlugin",
    "TavilyPlugin",
    "TwelvelabsPlugin",
    "UnstructuredPlugin",
    "UpstashPlugin",
    "ValkeyPlugin",
    "VectaraPlugin",
    "VertexaiPlugin",
    "VlmrunPlugin",
    "WeaviatePlugin",
    "WikipediaPlugin",
    "WolframalphaPlugin",
    "XaiPlugin",
    "YahoosearchPlugin",
    "YahooPlugin",
    "YoutubePlugin",
    "ZepPlugin",
]
