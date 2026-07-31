from typing import overload, Any, Union, List, Dict, Type
import base64
import os

try:
    from openai.types.chat import (
        ChatCompletionAssistantMessageParam,
        ChatCompletionContentPartImageParam,
        ChatCompletionContentPartRefusalParam,
        ChatCompletionContentPartTextParam,
        ChatCompletionMessageFunctionToolCallParam,
        ChatCompletionMessageParam,
        ChatCompletionSystemMessageParam,
        ChatCompletionUserMessageParam,
    )
    from openai.types.chat.chat_completion_content_part_image_param import ImageURL as OpenAIImageURL
    from openai.types.chat.chat_completion_message_function_tool_call_param import Function as OpenAIFunction
except ImportError:
    # Fallback types if openai package is not available
    ChatCompletionAssistantMessageParam = dict
    ChatCompletionContentPartImageParam = dict
    ChatCompletionContentPartRefusalParam = dict
    ChatCompletionContentPartTextParam = dict
    ChatCompletionMessageFunctionToolCallParam = dict
    ChatCompletionMessageParam = dict
    ChatCompletionSystemMessageParam = dict
    ChatCompletionUserMessageParam = dict
    OpenAIImageURL = dict
    OpenAIFunction = dict

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel

from autogenesis.message.types import (
    AssistantMessage,
    ContentPartAudio,
    ContentPartImage,
    ContentPartPdf,
    ContentPartRefusal,
    ContentPartText,
    ContentPartVideo,
    HumanMessage,
    Message,
    SystemMessage,
    ToolCall,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autogenesis.tool.types import Tool

from autogenesis.utils import assemble_workspace_path, encode_file_base64


def _strict_incompatible(o: Any) -> bool:
    """True if a JSON schema cannot be used with OpenAI strict structured outputs.

    Strict mode requires, for EVERY object: (1) additionalProperties: false, and
    (2) `required` to list every key in `properties`. A Dict[str, Any] field
    violates (1); any optional/defaulted field violates (2). Either one makes
    strict=true 400 with invalid_json_schema (observed on openai/gpt-5.5). When this
    returns True the caller sends strict=false — OpenAI then relaxes both rules and
    the result is still validated downstream via pydantic.
    """
    if isinstance(o, dict):
        if o.get("additionalProperties") is True:
            return True
        if o.get("type") == "object" or "properties" in o:
            props = set((o.get("properties") or {}).keys())
            req = set(o.get("required") or [])
            if props - req:
                return True
        return any(_strict_incompatible(v) for v in o.values())
    if isinstance(o, list):
        return any(_strict_incompatible(v) for v in o)
    return False


class OpenRouterChatSerializer:
    """
    Serializer for converting between custom message types and OpenRouter chat completions API message param types.
    
    OpenRouter uses OpenAI-compatible API format, so this serializer is essentially the same as OpenAIChatSerializer.
    """

    @staticmethod
    def _serialize_content_part_text(part: ContentPartText) -> ChatCompletionContentPartTextParam:
        return ChatCompletionContentPartTextParam(text=part.text, type='text')

    @staticmethod
    def _serialize_content_part_image(part: ContentPartImage) -> ChatCompletionContentPartImageParam:
        return ChatCompletionContentPartImageParam(
            image_url=OpenAIImageURL(url=part.image_url.url, detail=part.image_url.detail),
            type='image_url',
        )

    @staticmethod
    def _serialize_content_part_refusal(part: ContentPartRefusal) -> ChatCompletionContentPartRefusalParam:
        return ChatCompletionContentPartRefusalParam(refusal=part.refusal, type='refusal')

    @staticmethod
    def _serialize_content_part_audio(part: ContentPartAudio) -> dict[str, Any]:
        """Serialize audio content part for OpenRouter API.
        
        OpenRouter expects: {"type": "input_audio", "input_audio": {"data": "...", "format": "wav"}}
        """
        audio_url = part.audio_url.url
        audio_format = part.audio_url.media_type.split('/')[-1]  # Extract format from media_type (e.g., "audio/mp3" -> "mp3")
        
        # Handle data URLs (base64 encoded)
        if audio_url.startswith("data:"):
            # Extract base64 data from data URL
            # Format: data:audio/mp3;base64,<base64_data>
            if "," in audio_url:
                header, data = audio_url.split(",", 1)
                # Extract format from header if available
                if "audio/" in header:
                    format_part = header.split("audio/")[1].split(";")[0]
                    if format_part:
                        audio_format = format_part
                return {
                    "type": "input_audio",
                    "input_audio": {
                        "data": data,
                        "format": audio_format,
                    }
                }
        elif audio_url.startswith("file://"):
            # File path - read and encode to base64
            file_path = audio_url[7:]
            if not os.path.isabs(file_path):
                file_path = assemble_workspace_path(file_path)
            if os.path.exists(file_path):
                # Read file and encode to base64
                with open(file_path, "rb") as f:
                    audio_data = f.read()
                base64_data = base64.b64encode(audio_data).decode("utf-8")
                return {
                    "type": "input_audio",
                    "input_audio": {
                        "data": base64_data,
                        "format": audio_format,
                    }
                }
        elif os.path.exists(audio_url):
            # Direct file path
            with open(audio_url, "rb") as f:
                audio_data = f.read()
            base64_data = base64.b64encode(audio_data).decode("utf-8")
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": base64_data,
                    "format": audio_format,
                }
            }
        elif os.path.exists(assemble_workspace_path(audio_url)):
            # Relative file path
            file_path = assemble_workspace_path(audio_url)
            with open(file_path, "rb") as f:
                audio_data = f.read()
            base64_data = base64.b64encode(audio_data).decode("utf-8")
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": base64_data,
                    "format": audio_format,
                }
            }
        else:
            # URL - OpenRouter may support URLs, but for now we'll try to use URL directly
            # Note: OpenRouter may require base64 data, so this might need adjustment
            # For now, assume it's a URL that OpenRouter can handle
            return {
                "type": "input_audio",
                "input_audio": {
                    "url": audio_url,
                    "format": audio_format,
                }
            }

    @staticmethod
    def _serialize_content_part_video(part: ContentPartVideo) -> dict[str, Any]:
        """Serialize video content part for OpenRouter API.
        
        OpenRouter expects: {"type": "video_url", "video_url": {"url": "..."}}
        """
        return {
            "type": "video_url",
            "video_url": {
                "url": part.video_url.url,
            }
        }

    @staticmethod
    def _serialize_content_part_pdf(part: ContentPartPdf) -> dict[str, Any]:
        """Serialize PDF content part for OpenRouter API.
        
        OpenRouter expects: {"type": "file", "file": {"filename": "document.pdf", "file_data": data_url}}
        """
        pdf_url = part.pdf_url.url
        
        # Handle data URLs (base64 encoded)
        if pdf_url.startswith("data:"):
            # Already a data URL, extract filename from URL or use default
            filename = "document.pdf"
            # Try to extract filename from URL if it's a file:// URL converted to data URL
            if "file://" in pdf_url or "filename=" in pdf_url:
                # Could parse filename if available
                pass
            return {
                "type": "file",
                "file": {
                    "filename": filename,
                    "file_data": pdf_url,
                }
            }
        elif pdf_url.startswith("file://"):
            # File path - read and encode to base64
            file_path = pdf_url[7:]
            if not os.path.isabs(file_path):
                file_path = assemble_workspace_path(file_path)
            if os.path.exists(file_path):
                # Read file and encode to base64
                with open(file_path, "rb") as f:
                    pdf_data = f.read()
                base64_data = base64.b64encode(pdf_data).decode("utf-8")
                filename = os.path.basename(file_path)
                data_url = f"data:application/pdf;base64,{base64_data}"
                return {
                    "type": "file",
                    "file": {
                        "filename": filename,
                        "file_data": data_url,
                    }
                }
        elif os.path.exists(pdf_url):
            # Direct file path
            with open(pdf_url, "rb") as f:
                pdf_data = f.read()
            base64_data = base64.b64encode(pdf_data).decode("utf-8")
            filename = os.path.basename(pdf_url)
            data_url = f"data:application/pdf;base64,{base64_data}"
            return {
                "type": "file",
                "file": {
                    "filename": filename,
                    "file_data": data_url,
                }
            }
        elif os.path.exists(assemble_workspace_path(pdf_url)):
            # Relative file path
            file_path = assemble_workspace_path(pdf_url)
            with open(file_path, "rb") as f:
                pdf_data = f.read()
            base64_data = base64.b64encode(pdf_data).decode("utf-8")
            filename = os.path.basename(file_path)
            data_url = f"data:application/pdf;base64,{base64_data}"
            return {
                "type": "file",
                "file": {
                    "filename": filename,
                    "file_data": data_url,
                }
            }
        else:
            # URL - try to use as data URL if it's already base64 encoded
            # Otherwise, assume it's a URL that needs to be downloaded
            return {
                "type": "file",
                "file": {
                    "filename": "document.pdf",
                    "file_data": pdf_url if pdf_url.startswith("data:") else f"data:application/pdf;base64,{pdf_url}",
                }
            }

    @staticmethod
    def _serialize_user_content(
        content: str | list[ContentPartText | ContentPartImage | ContentPartAudio | ContentPartVideo | ContentPartPdf],
    ) -> str | list[Union[ChatCompletionContentPartTextParam, ChatCompletionContentPartImageParam, dict[str, Any]]]:
        """Serialize content for user messages (text, images, audio, video, and PDF allowed)."""
        if isinstance(content, str):
            return content
        serialized_parts: list[Union[ChatCompletionContentPartTextParam, ChatCompletionContentPartImageParam, dict[str, Any]]] = []
        for part in content:
            if part.type == 'text':
                serialized_parts.append(OpenRouterChatSerializer._serialize_content_part_text(part))
            elif part.type == 'image_url':
                serialized_parts.append(OpenRouterChatSerializer._serialize_content_part_image(part))
            elif part.type == 'audio_url':
                serialized_parts.append(OpenRouterChatSerializer._serialize_content_part_audio(part))
            elif part.type == 'video_url':
                serialized_parts.append(OpenRouterChatSerializer._serialize_content_part_video(part))
            elif part.type == 'pdf_url':
                serialized_parts.append(OpenRouterChatSerializer._serialize_content_part_pdf(part))
        return serialized_parts

    @staticmethod
    def _serialize_system_content(
        content: str | list[ContentPartText],
    ) -> str | list[ChatCompletionContentPartTextParam]:
        """Serialize content for system messages (text only)."""
        if isinstance(content, str):
            return content
        serialized_parts: list[ChatCompletionContentPartTextParam] = []
        for part in content:
            if part.type == 'text':
                serialized_parts.append(OpenRouterChatSerializer._serialize_content_part_text(part))
        return serialized_parts

    @staticmethod
    def _serialize_assistant_content(
        content: str | list[ContentPartText | ContentPartRefusal] | None,
    ) -> str | list[ChatCompletionContentPartTextParam | ChatCompletionContentPartRefusalParam] | None:
        """Serialize content for assistant messages (text and refusal allowed)."""
        if content is None:
            return None
        if isinstance(content, str):
            return content
        serialized_parts: list[ChatCompletionContentPartTextParam | ChatCompletionContentPartRefusalParam] = []
        for part in content:
            if part.type == 'text':
                serialized_parts.append(OpenRouterChatSerializer._serialize_content_part_text(part))
            elif part.type == 'refusal':
                serialized_parts.append(OpenRouterChatSerializer._serialize_content_part_refusal(part))
        return serialized_parts

    @staticmethod
    def _serialize_tool_call(tool_call: ToolCall) -> ChatCompletionMessageFunctionToolCallParam:
        return ChatCompletionMessageFunctionToolCallParam(
            id=tool_call.id,
            function=OpenAIFunction(name=tool_call.function.name, arguments=tool_call.function.arguments),
            type='function',
        )

    # region - Serialize overloads

    @overload
    @staticmethod
    def serialize_message(message: HumanMessage) -> ChatCompletionUserMessageParam: ...

    @overload
    @staticmethod
    def serialize_message(message: SystemMessage) -> ChatCompletionSystemMessageParam: ...

    @overload
    @staticmethod
    def serialize_message(message: AssistantMessage) -> ChatCompletionAssistantMessageParam: ...

    @staticmethod
    def serialize_message(message: Message) -> ChatCompletionMessageParam:
        """Serialize a custom message to an OpenRouter message param."""
        if isinstance(message, HumanMessage):
            user_result: ChatCompletionUserMessageParam = {
                'role': 'user',
                'content': OpenRouterChatSerializer._serialize_user_content(message.content),
            }
            if message.name is not None:
                user_result['name'] = message.name
            return user_result

        elif isinstance(message, SystemMessage):
            system_result: ChatCompletionSystemMessageParam = {
                'role': 'system',
                'content': [
                    {
                        'type': 'text',
                        'text': OpenRouterChatSerializer._serialize_system_content(message.content),
                        "cache_control": {
                            "type": "ephemeral"
                        }
                    }
                ],
            }
            if message.name is not None:
                system_result['name'] = message.name
            return system_result

        elif isinstance(message, AssistantMessage):
            # Handle content serialization
            content = None
            if message.content is not None:
                content = OpenRouterChatSerializer._serialize_assistant_content(message.content)
            assistant_result: ChatCompletionAssistantMessageParam = {'role': 'assistant'}
            # Only add content if it's not None
            if content is not None:
                assistant_result['content'] = content
            if message.name is not None:
                assistant_result['name'] = message.name
            if message.refusal is not None:
                assistant_result['refusal'] = message.refusal
            if message.tool_calls:
                assistant_result['tool_calls'] = [OpenRouterChatSerializer._serialize_tool_call(tc) for tc in message.tool_calls]
            return assistant_result

        else:
            raise ValueError(f'Unknown message type: {type(message)}')

    @staticmethod
    def serialize_messages(messages: list[Message]) -> list[ChatCompletionMessageParam]:
        return [OpenRouterChatSerializer.serialize_message(m) for m in messages]

    @staticmethod
    def serialize_tool(tool: "Tool") -> Dict[str, Any]:
        """Serialize a Tool instance to an OpenRouter tool param."""
        return tool.function_calling
    
    @staticmethod
    def serialize_tools(tools: List["Tool"]) -> List[Dict[str, Any]]:
        """Serialize a list of Tool instances to an OpenRouter tools param."""
        return [OpenRouterChatSerializer.serialize_tool(tool) for tool in tools]
    
    @staticmethod
    def serialize_response_format(
        response_format: Union[Type[BaseModel], BaseModel],
        model_name: str = "openrouter/gemini-3-flash-preview",
    ) -> Dict[str, Any]:
        """
        Format response_format from Pydantic model to OpenRouter JSON schema format.
            
        Example 1:
        class BashToolInputArgs(BaseModel):
            command: str = Field(description="The command to execute.")
            file_path: Optional[str] = Field(default=None, description="The file path to execute the command.")
            
        output:
        {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The command to execute.",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "The file path to execute the command.",
                        },
                    },
                    "additionalProperties": False,
                    "required": ["command"],
                },
            },
        }
        
        Example 2:
        class Tool(BaseModel):
            name: str
            args: Optional[Dict[str, Any]] = Field(default=None, description="The arguments to the tool.")
            
        class ThinkOutput(BaseModel):
            thinking: str = Field(description="The thinking to complete the task.")
            evaluation_previous_goal: str = Field(description="The evaluation of the previous goal.")
            memory: str = Field(description="The memory to complete the task.")
            next_goal: str = Field(description="The next goal to complete the task.")
            tool: List[Tool] = Field(description="The tool to complete the task.")
            
        output:
        {
            "type": "json_schema",
            "json_schema": {
                "name": "think_output_response",
                "strict": true,
                "schema": {
                "type": "object",
                "properties": {
                    "thinking": { "type": "string", "description": "The thinking to complete the task." },
                    "evaluation_previous_goal": { "type": "string", "description": "The evaluation of the previous goal." },
                    "memory": { "type": "string", "description": "The memory to complete the task." },
                    "next_goal": { "type": "string", "description": "The next goal to complete the task." },
                    "tool": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                        "name": { "type": "string", "description": "The name of the tool." },
                        "args": {
                                "type": "object",
                                "description": "The arguments to the tool.",
                                "additionalProperties": true
                            }
                        },
                        "required": ["name"],
                        "additionalProperties": false
                    }
                    }
                },
                "required": ["thinking", "evaluation_previous_goal", "memory", "next_goal", "tool"],
                "additionalProperties": false
                }
            }
        }
        """
        model_class = response_format if isinstance(response_format, type) else type(response_format)
        schema = model_class.model_json_schema()
        defs = schema.pop("$defs", {})  # Remove $defs to avoid appearing in the final result

        def transform(obj: Any) -> Any:
            if not isinstance(obj, dict):
                return obj
            
            # Expand all references to ensure full inlining
            if "$ref" in obj:
                ref_path = obj["$ref"]
                if ref_path.startswith("#/$defs/"):
                    def_name = ref_path.split("/")[-1]
                    if def_name in defs:
                        return transform(defs[def_name])
                return {"type": "object", "additionalProperties": False}
            
            # Handle Union structures (anyOf, oneOf, allOf) - used for handling Optional fields
            for k in ["anyOf", "oneOf", "allOf"]:
                if k in obj:
                    items = obj[k]
                    non_null = [i for i in items if isinstance(i, dict) and i.get("type") != "null"]
                    if len(non_null) == 1:
                        # Retain original object's description and title
                        result = transform(non_null[0])
                        if isinstance(result, dict):
                            if "description" in obj and "description" not in result:
                                result["description"] = obj["description"]
                            if "title" in obj and "title" not in result:
                                result["title"] = obj["title"]
                        return result
                    else:
                        return {
                            "type": "object",
                            "description": obj.get("description", "Simplified Object"),
                            "additionalProperties": False
                        }

            # Handle objects
            if obj.get("type") == "object" or "properties" in obj:
                props = obj.get("properties", {})
                required = obj.get("required", [])
                new_props = {}
                new_required = []

                for k, v in props.items():
                    new_props[k] = transform(v)
                    if k in required:
                        new_required.append(k)

                # Handle additionalProperties which can be a boolean or an inline schema (dict),
                # e.g. for Dict[str, ImprovedVariable] pydantic emits:
                # "additionalProperties": {"$ref": "#/$defs/ImprovedVariable"}
                ap = obj.get("additionalProperties", None)
                if isinstance(ap, dict):
                    # Recursively transform the inline schema so $ref inside additionalProperties is expanded
                    transformed_ap = transform(ap)
                    additional_props = transformed_ap
                else:
                    # Preserve the original boolean semantics for simple Dict[str, Any] cases.
                    # If there are no explicit properties and additionalProperties is True,
                    # keep it permissive. Otherwise use strict mode.
                    if not new_props and ap is True:
                        additional_props = True
                    else:
                        additional_props = False

                result = {
                    "type": "object",
                    "properties": new_props,
                    "required": new_required,
                    "additionalProperties": additional_props
                }
                # Retain metadata such as description and title
                if "description" in obj:
                    result["description"] = obj["description"]
                if "title" in obj:
                    result["title"] = obj["title"]
                return result

            # Handle arrays
            if obj.get("type") == "array":
                result = {
                    "type": "array",
                    "items": transform(obj.get("items", {}))
                }
                # Retain metadata such as description and title
                if "description" in obj:
                    result["description"] = obj["description"]
                if "title" in obj:
                    result["title"] = obj["title"]
                return result

            # For other types, retain all fields (including description, title, etc.)
            return obj

        transformed = transform(schema)

        strict = not _strict_incompatible(transformed)

        return {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": strict,
                "schema": transformed,
            },
        }
