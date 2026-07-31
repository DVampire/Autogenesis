import os
import sys
import json
from dotenv import load_dotenv
load_dotenv(verbose=True)

from pathlib import Path
import argparse
from mmengine import DictAction
import asyncio
import pytest
from pydantic import BaseModel, Field
from typing import List, Dict, Any

root = str(Path(__file__).resolve().parents[1])
sys.path.append(root)

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.model import model_manager
from autogenesis.message import (
    HumanMessage,
    SystemMessage,
    ContentPartText,
    ContentPartImage,
    ImageURL,
    ContentPartAudio,
    AudioURL,
    ContentPartVideo,
    VideoURL,
    ContentPartPdf,
    PdfURL,
)

from autogenesis.tool import tool_manager
from autogenesis.version import version_manager
from autogenesis.utils import assemble_workspace_path, make_file_url

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_chat():
    logger.info(f"| --------------------------------------------------")
    logger.info(f"| Testing chat with different models")
    models = [
        # OpenAI models
        # "openrouter/gpt-4o",
        # "openrouter/gpt-4.1",
        # "openrouter/gpt-5",
        # "openrouter/gpt-5.1",
        # "openrouter/gpt-5.2",
        # "openrouter/o3",
        # "openrouter/o3-mini",
        # "openrouter/gpt-5.4-pro",
        # "openrouter/gpt-5.3-codex",
        # "openai/gpt-4o",
        # "openai/gpt-4.1",
        # "openai/gpt-5",
        # "openai/gpt-5.1",
        # "openai/gpt-5.2",
        # "openai/gpt-5.4-pro",
        # "openai/o3",
        # "openai/o3-mini",
        # "newapi/gpt-5.4-pro",
        # "newapi/gpt-5.4",
        # "newapi/o3-mini",
        
        # Anthropic models
        # "openrouter/claude-sonnet-3.7",
        # "openrouter/claude-sonnet-4",
        # "openrouter/claude-opus-4",
        # "openrouter/claude-sonnet-4.5",
        # "openrouter/claude-opus-4.5",
        # "openrouter/claude-sonnet-4.6",
        # "openrouter/claude-opus-4.6",
        # "anthropic/claude-sonnet-3.7",
        # "anthropic/claude-sonnet-4",
        # "anthropic/claude-sonnet-4.5",
        # "newapi/claude-opus-4.6",

        # Aws claude models
        # "aws_claude/claude-opus-4.6",
        # "aws_claude/claude-opus-4.7",
        "aws_claude/claude-opus-4.8",
        
        # Gemini models
        # "openrouter/gemini-2.5-flash",
        # "openrouter/gemini-2.5-pro",
        # "openrouter/gemini-3-flash-preview",
        # "openrouter/gemini-3-pro-preview",
        # "openrouter/gemini-3.1-pro-preview",
        # "openrouter/gemini-3.1-pro-preview-plugins",
        # "google/gemini-2.5-flash",
        # "google/gemini-2.5-pro",
        # "google/gemini-3-pro-preview",
        # "newapi/gemini-3.1-pro-preview",
        
        # Grok models
        # "openrouter/grok-4.1-fast",

        # int openrouter models
        # "int_openrouter/gpt-5.4",
        # "int_openrouter/gpt-5.5",
        # "int_openrouter/gpt-5.4-pro",
        # "int_openrouter/gpt-5.5-pro",
        # "int_openrouter/o3-mini",
        # "int_openrouter/gemini-3.1-pro-preview",
        # "int_openrouter/grok-4.1-fast",
        # "int_openrouter/gemini-3-flash-preview",
    ]
    
    logger.info(f"| Testing Local Image.")
    logger.info(f"| --------------------------------------------------")
    image_url = make_file_url(file_path=assemble_workspace_path("tests/files/pokemon.jpg"))
    
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="What are the names of the Pokémon in the image? You can use deep research to find the answer. Please only return the names of the Pokémon."),
            ContentPartImage(image_url=ImageURL(url=image_url, detail="high")),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(
            name=model,
            input={"messages": messages},
        )
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")

    logger.info(f"| Testing Online Image.")
    logger.info(f"| --------------------------------------------------")
    image_url = "https://m.media-amazon.com/images/I/81Uuowxx0-L._AC_SX679_.jpg"
    
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="What are the names of the Pokémon in the image? You can use deep research to find the answer. Please only return the names of the Pokémon."),
            ContentPartImage(image_url=ImageURL(url=image_url, detail="high")),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(
            name=model,
            input={"messages": messages},
        )
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")

async def test_audio():
    logger.info(f"| --------------------------------------------------")
    logger.info(f"| Testing audio with different models")
    models = [
        "openrouter/gemini-3.1-pro-preview-plugins",
    ]
    
    logger.info(f"| Testing Local Audio.")
    logger.info(f"| --------------------------------------------------")

    audio_url = make_file_url(file_path=assemble_workspace_path("tests/files/audio.mp3"))

    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="Please transcribe the audio file and provide the transcription. Only return the transcription, no other text or formatting."),
            ContentPartAudio(audio_url=AudioURL(url=audio_url)),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(name=model, input={"messages": messages})
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")

    logger.info(f"| Testing Online Audio.") # ！！！不支持audio的url
    logger.info(f"| --------------------------------------------------")
    
    audio_url = "https://www.mmsp.ece.mcgill.ca/Documents/AudioFormats/WAVE/Samples/AFsp/M1F1-Alaw-AFsp.wav"

    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="Please transcribe the audio file and provide the transcription. Only return the transcription, no other text or formatting."),
            ContentPartAudio(audio_url=AudioURL(url=audio_url)),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(name=model, input={"messages": messages})
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")


async def test_embedding():
    logger.info(f"| --------------------------------------------------")
    logger.info(f"| Testing embedding with different models")
    models = [
        # "openai/text-embedding-3-small",
        "openai/text-embedding-3-large",
        # "openai/text-embedding-ada-002",
    ]
    
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="Please embed the text and provide the embedding."),
            ContentPartText(text="The text is: The quick brown fox jumps over the lazy dog."),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(name=model, input={"messages": messages})
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")

async def test_video():
    logger.info(f"| --------------------------------------------------")
    logger.info(f"| Testing video with different models")
    models = [
        "openrouter/gemini-2.5-flash",
        # "google/gemini-2.5-flash",
    ]
    
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="Please analyze the video and provide the analysis. Only return the analysis, no other text or formatting."),
            ContentPartVideo(video_url=VideoURL(url=make_file_url(file_path="tests/files/video.MOV"))),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(name=model, input={"messages": messages})
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")


async def test_pdf():
    logger.info(f"| --------------------------------------------------")
    logger.info(f"| Testing PDF with different models")
    models = [
        "openrouter/gemini-3-flash-preview-plugins"
    ]
    
    logger.info(f"| Testing Local PDF.")
    logger.info(f"| --------------------------------------------------")

    pdf_url = make_file_url(file_path=assemble_workspace_path("tests/files/pdf.pdf"))

    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="Please analyze the PDF and provide the analysis. Only return the analysis, no other text or formatting."),
            ContentPartPdf(pdf_url=PdfURL(url=pdf_url)),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(name=model, input={"messages": messages})
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")

    logger.info(f"| Testing Online PDF.")
    logger.info(f"| --------------------------------------------------")

    pdf_url = "https://arxiv.org/pdf/2302.11312" # ！！！不支持pdf的url

    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="Please analyze the PDF and provide the analysis. Only return the analysis, no other text or formatting."),
            ContentPartPdf(pdf_url=PdfURL(url=pdf_url)),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(name=model, input={"messages": messages})
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")


async def test_response_format():
    """Structured output — the mechanism is DERIVED from whether tools are passed:

    - no tools  → native response_format / output_format / response_schema
    - w/ tools  → the schema rides along as a synthetic tool (native structured
                  output and native tool calling can't coexist), folded back into
                  parsed_model

    Every combination (× stream) must yield a validated ``parsed_model``, and the
    structured Response shape must stay consistent (same data key set) whether or
    not tools are present.
    """
    logger.info(f"| --------------------------------------------------")
    logger.info(f"| Testing response format: native (no tools) vs synthetic (w/ tools)")
    models = [
        "openrouter/claude-opus-4.8",
        "openrouter/gemini-3.5-flash",
    ]

    class ToolInputArgs(BaseModel):
        name: str = Field(description="The name of the tool")
        args: Dict[str, Any] = Field(description="The arguments of the tool")

    class ThinkOutput(BaseModel):
        """Structured reasoning plus the tools to call next."""
        thinking: str = Field(description="The reasoning of the assistant")
        next_goal: str = Field(description="The immediate next goal")
        tool: List[ToolInputArgs] = Field(description="The tools to call next")

    prompt = (
        "Plan the task 'add 1 and 2 and report the result'. Return the structured "
        "result only — reasoning in `thinking`, the immediate next goal in "
        "`next_goal`, and the tool(s) you would call in `tool`. Do not run anything."
    )
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[ContentPartText(text=prompt)]),
    ]
    # Any tool present → triggers the synthetic path (schema rides along as a
    # tool). This one is a real-shaped, irrelevant no-op (carries .function_calling
    # like a real tool), so a well-behaved model calls the structured-output tool.
    class _NoopTool:
        name = "noop"
        description = "Does nothing. Never call this."
        function_calling = {
            "type": "function",
            "function": {
                "name": "noop",
                "description": "Does nothing. Never call this.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }
    distractor = _NoopTool()

    async def _run(model: str, with_tools: bool, stream: bool):
        inp = {"messages": messages, "response_format": ThinkOutput, "stream": stream}
        if with_tools:
            inp["tools"] = [distractor]
        response = await model_manager(name=model, input=inp)
        kind = "synthetic(w/ tools)" if with_tools else "native(no tools)"
        tag = f"{model} {kind} stream={stream}"
        assert response.success, f"{tag} failed: {response.message}"
        assert isinstance(response.parsed_model, ThinkOutput), f"{tag}: parsed_model not ThinkOutput"
        print(f"[OK] {tag} -> {response.parsed_model}")
        return response

    for model in models:
        for stream in (False, True):
            native = await _run(model, with_tools=False, stream=stream)
            synthetic = await _run(model, with_tools=True, stream=stream)
            n_keys = set((native.data or {}).keys())
            s_keys = set((synthetic.data or {}).keys())
            assert n_keys == s_keys, (
                f"{model} stream={stream}: data keys differ — "
                f"native={sorted(n_keys)} synthetic={sorted(s_keys)}"
            )
            print(f"[MATCH] {model} stream={stream}: native ≡ synthetic shape (data keys={sorted(n_keys)})")

    logger.info(f"| --------------------------------------------------")


async def test_tool_calling():
    logger.info(f"| --------------------------------------------------")
    logger.info(f"| Testing tool calling with different models")
    models = [
        # OpenAI models
        "openrouter/gpt-4o",
        "openrouter/gpt-4.1",
        "openrouter/gpt-5",
        "openrouter/gpt-5.1",
        "openrouter/gpt-5.2",
        "openrouter/o3",
        # "openai/gpt-4o",
        # "openai/gpt-4.1",
        # "openai/gpt-5",
        # "openai/gpt-5.1",
        # "openai/o3",
        
        # Anthropic models
        # "openrouter/claude-sonnet-3.7",
        # "openrouter/claude-sonnet-4",
        # "openrouter/claude-opus-4",
        # "openrouter/claude-sonnet-4.5",
        # "openrouter/claude-opus-4.5",
        # "anthropic/claude-sonnet-3.7",
        # "anthropic/claude-sonnet-4",
        # "anthropic/claude-sonnet-4.5",
        
        # Gemini models
        # "openrouter/gemini-2.5-flash",
        # "openrouter/gemini-2.5-pro",
        # "openrouter/gemini-3-pro-preview",
        # "google/gemini-2.5-flash",
        # "google/gemini-2.5-pro",
        # "google/gemini-3-pro-preview",
    ]
    
    tools = [
        await tool_manager.get('bash'),
    ]
    
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="Please run the command 'ls -l' and return the output."),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(
            name=model,
            input={"messages": messages, "tools": tools},
        )
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")

async def test_search():
    logger.info(f"| --------------------------------------------------")
    logger.info(f"| Testing search with different models")
    models = [
        "openrouter/gemini-3.1-pro-preview-plugins",
        # "openrouter/gemini-3-flash-preview-plugins"
    ]
    
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="Please search the web for the latest news about the AAPL stock."),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(name=model, input={"messages": messages})
        logger.info(f"| {model} Response: {json.dumps(response.message, indent=4)}")
    logger.info(f"| --------------------------------------------------")


async def test_music():
    logger.info(f"| --------------------------------------------------")
    logger.info(f"| Testing music with different models")
    models = [
        "openrouter/gemini-3.1-pro-preview-plugins",
    ]
    
    logger.info(f"| Testing Local Image.")
    logger.info(f"| --------------------------------------------------")
    image_url = make_file_url(file_path=assemble_workspace_path("tests/files/0075.png"))
    
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content=[
            ContentPartText(text="Search the web then guess the music."),
            ContentPartImage(image_url=ImageURL(url=image_url, detail="high")),
        ]),
    ]
    
    for model in models:
        logger.info(f"| Testing {model}")
        response = await model_manager(
            name=model,
            input={"messages": messages},
        )
        logger.info(f"| {model} Response: {json.dumps(response.model_dump(), indent=4)}")
    logger.info(f"| --------------------------------------------------")


def parse_args():
    parser = argparse.ArgumentParser(description='main')
    parser.add_argument("--config", default=os.path.join(root, "configs", "meta_agent.py"), help="config file path")

    parser.add_argument(
        '--cfg-options',
        nargs='+',
        action=DictAction,
        help='override some settings in the used config, the key-value pair '
        'in xxx=yyy format will be merged into config file. If the value to '
        'be overwritten is a list, it should be like key="[a,b]" or key=a,b '
        'It also allows nested list/tuple values, e.g. key="[(a,b),(c,d)]" '
        'Note that the quotation marks are necessary and that no white space '
        'is allowed.')
    args = parser.parse_args()
    return args

async def main():
    args = parse_args()
    
    config.initialize(config_path=args.config, args=args)
    logger.initialize(config=config)
    logger.info(f"| Config: {config.pretty_text}")

    # Initialize version manager
    await version_manager.initialize()
    logger.info(f"| Version manager initialized: {await version_manager.list()}")
    
    # Initialize model manager
    await model_manager.initialize()
    logger.info(f"| Model manager initialized: {model_manager.list()}")
    
    # Initialize tools
    await tool_manager.initialize(tool_names=config.tool_names)
    logger.info(f"| Tools initialized: {await tool_manager.list()}")

    await test_response_format()
    # await test_chat()
    # await test_tool_calling()
    # await test_audio()
    # await test_embedding()
    # await test_video()
    # await test_pdf()
    # await test_search()
    # await test_music()

if __name__ == "__main__":
    asyncio.run(main())
