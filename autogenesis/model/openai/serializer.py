from typing import overload, Any

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

from typing import Optional, List, Dict, Any, Union, Type, TYPE_CHECKING
from pydantic import BaseModel

from autogenesis.message.types import (
    AssistantMessage,
    ContentPartImage,
    ContentPartRefusal,
    ContentPartText,
    HumanMessage,
    Message,
    SystemMessage,
    ToolCall,
)

if TYPE_CHECKING:
    from autogenesis.tool.types import Tool


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


class OpenAIChatSerializer:
    """Serializer for converting between custom message types and OpenAI chat completions API message param types."""

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
    def _serialize_user_content(
        content: str | list[ContentPartText | ContentPartImage],
    ) -> str | list[ChatCompletionContentPartTextParam | ChatCompletionContentPartImageParam]:
        """Serialize content for user messages (text and images allowed)."""
        if isinstance(content, str):
            return content
        serialized_parts: list[ChatCompletionContentPartTextParam | ChatCompletionContentPartImageParam] = []
        for part in content:
            if part.type == 'text':
                serialized_parts.append(OpenAIChatSerializer._serialize_content_part_text(part))
            elif part.type == 'image_url':
                serialized_parts.append(OpenAIChatSerializer._serialize_content_part_image(part))
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
                serialized_parts.append(OpenAIChatSerializer._serialize_content_part_text(part))
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
                serialized_parts.append(OpenAIChatSerializer._serialize_content_part_text(part))
            elif part.type == 'refusal':
                serialized_parts.append(OpenAIChatSerializer._serialize_content_part_refusal(part))
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
    def serialize(message: HumanMessage) -> ChatCompletionUserMessageParam: ...

    @overload
    @staticmethod
    def serialize(message: SystemMessage) -> ChatCompletionSystemMessageParam: ...

    @overload
    @staticmethod
    def serialize(message: AssistantMessage) -> ChatCompletionAssistantMessageParam: ...

    @staticmethod
    def serialize(message: Message) -> ChatCompletionMessageParam:
        """Serialize a custom message to an OpenAI message param."""
        if isinstance(message, HumanMessage):
            user_result: ChatCompletionUserMessageParam = {
                'role': 'user',
                'content': OpenAIChatSerializer._serialize_user_content(message.content),
            }
            if message.name is not None:
                user_result['name'] = message.name
            return user_result

        elif isinstance(message, SystemMessage):
            system_result: ChatCompletionSystemMessageParam = {
                'role': 'system',
                'content': OpenAIChatSerializer._serialize_system_content(message.content),
            }
            if message.name is not None:
                system_result['name'] = message.name
            return system_result

        elif isinstance(message, AssistantMessage):
            # Handle content serialization
            content = None
            if message.content is not None:
                content = OpenAIChatSerializer._serialize_assistant_content(message.content)
            assistant_result: ChatCompletionAssistantMessageParam = {'role': 'assistant'}
            # Only add content if it's not None
            if content is not None:
                assistant_result['content'] = content
            if message.name is not None:
                assistant_result['name'] = message.name
            if message.refusal is not None:
                assistant_result['refusal'] = message.refusal
            if message.tool_calls:
                assistant_result['tool_calls'] = [OpenAIChatSerializer._serialize_tool_call(tc) for tc in message.tool_calls]
            return assistant_result

        else:
            raise ValueError(f'Unknown message type: {type(message)}')

    @staticmethod
    def serialize_messages(messages: list[Message]) -> list[ChatCompletionMessageParam]:
        return [OpenAIChatSerializer.serialize(m) for m in messages]

    @staticmethod
    def serialize_tools(tools: List["Tool"]) -> List[Dict[str, Any]]:
        """
        Serialize tools for OpenAI API calls. Convert Tool instances to function call format.
        
        Args:
            tools: List of Tool instances
            
        Returns:
            List of function call format dicts
        """
        return [tool.function_calling for tool in tools]
    
    @staticmethod
    def serialize_response_format(
        response_format: Union[Type[BaseModel], BaseModel]
    ) -> Dict[str, Any]:
        """
        Format response_format from Pydantic model to OpenAI-compatible JSON schema format.
        
        OpenAI requires additionalProperties: false for all object types (similar to OpenRouter).
        
        Args:
            response_format: BaseModel class or instance
            
        Returns:
            Dictionary containing response format configuration with:
            - type: "json_schema"
            - json_schema: Contains name, strict mode, and optimized schema
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
                return {"type": "object", "additionalProperties": True}
            
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
                            "additionalProperties": True 
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
                
                # For Dict[str, Any] types (no properties or empty properties), retain additionalProperties: True
                # Otherwise, set to False (strict mode)
                if not new_props and obj.get("additionalProperties") is True:
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


class OpenAIResponseSerializer:
    """Serializer for converting between custom message types and OpenAI responses API input format."""

    @staticmethod
    def _serialize_content_part_text(part: ContentPartText) -> dict[str, Any]:
        """Serialize text content part for responses API."""
        return {
            "type": "input_text",
            "text": part.text,
        }

    @staticmethod
    def _serialize_content_part_image(part: ContentPartImage) -> dict[str, Any]:
        """Serialize image content part for responses API."""
        return {
            "type": "input_image",
            "image_url": part.image_url.url,
        }

    @staticmethod
    def _serialize_content(
        content: str | list[ContentPartText | ContentPartImage],
    ) -> list[dict[str, Any]]:
        """Serialize content for responses API."""
        if isinstance(content, str):
            return [{"type": "input_text", "text": content}]
        
        serialized_parts: list[dict[str, Any]] = []
        for part in content:
            if part.type == 'text':
                serialized_parts.append(OpenAIResponseSerializer._serialize_content_part_text(part))
            elif part.type == 'image_url':
                serialized_parts.append(OpenAIResponseSerializer._serialize_content_part_image(part))
        
        return serialized_parts

    @staticmethod
    def serialize(message: Message) -> dict[str, Any]:
        """Serialize a custom message to OpenAI responses API input format."""
        if isinstance(message, HumanMessage):
            result: dict[str, Any] = {
                "role": "user",
                "content": OpenAIResponseSerializer._serialize_content(message.content),
            }
            if message.name is not None:
                result["name"] = message.name
            return result

        elif isinstance(message, SystemMessage):
            # System messages are typically included in the first user message or handled separately
            # For responses API, we'll include them as system role
            result: dict[str, Any] = {
                "role": "system",
                "content": OpenAIResponseSerializer._serialize_content(message.content),
            }
            if message.name is not None:
                result["name"] = message.name
            return result

        elif isinstance(message, AssistantMessage):
            # Assistant messages are typically not in input, but we serialize them for completeness
            result: dict[str, Any] = {
                "role": "assistant",
            }
            if message.content is not None:
                result["content"] = OpenAIResponseSerializer._serialize_content(message.content)
            if message.name is not None:
                result["name"] = message.name
            return result

        else:
            raise ValueError(f'Unknown message type: {type(message)}')

    @staticmethod
    def serialize_messages(messages: list[Message]) -> list[dict[str, Any]]:
        """Serialize a list of messages to OpenAI responses API input format."""
        return [OpenAIResponseSerializer.serialize(m) for m in messages]

