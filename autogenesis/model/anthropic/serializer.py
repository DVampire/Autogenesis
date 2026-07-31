from typing import overload, Any, List, Union, Optional, Type
import base64
import os

from typing import Optional, List, Dict, Any, Union
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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autogenesis.tool.types import Tool

from autogenesis.utils import assemble_workspace_path, decode_file_base64

try:
    from anthropic import transform_schema
except ImportError:
    transform_schema = None


class AnthropicChatSerializer:
    """
    Serializer for converting between custom message types and Anthropic messages API format.
    
    Anthropic API format:
    - system: string (top-level field, not in messages)
    - messages: list of {"role": "user"|"assistant", "content": [...]}
    - content for user: list of {"type": "text"|"image", ...}
    - content for assistant: list of {"type": "text"|"tool_use", ...}
    - images: {"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}
    """

    @staticmethod
    def _serialize_content_part_text(part: ContentPartText) -> dict[str, Any]:
        return {"type": "text", "text": part.text}

    @staticmethod
    def _normalize_media_type(media_type: str) -> str:
        """Normalize media type to Anthropic-supported formats.
        
        Anthropic only supports: 'image/jpeg', 'image/png', 'image/gif', 'image/webp'
        """
        media_type = media_type.lower().strip()
        
        # Map common variations to supported types
        if media_type in ['image/jpeg', 'image/jpg']:
            return 'image/jpeg'
        elif media_type == 'image/png':
            return 'image/png'
        elif media_type == 'image/gif':
            return 'image/gif'
        elif media_type == 'image/webp':
            return 'image/webp'
        else:
            # Default to jpeg for unknown types
            return 'image/jpeg'

    @staticmethod
    def _serialize_content_part_image(part: ContentPartImage) -> dict[str, Any]:
        """Serialize image content part for Anthropic API.
        
        Anthropic expects: {"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}
        Anthropic only supports: 'image/jpeg', 'image/png', 'image/gif', 'image/webp'
        """
        image_url = part.image_url.url
        
        # Handle data URLs (base64 encoded)
        if image_url.startswith("data:"):
            # Extract media type and base64 data from data URL
            # Format: data:image/jpeg;base64,<base64_data>
            header, data = image_url.split(",", 1)
            media_type = "image/jpeg"  # default
            if "image/" in header:
                extracted_type = header.split("image/")[1].split(";")[0]
                media_type = AnthropicChatSerializer._normalize_media_type(f"image/{extracted_type}")
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                }
            }
        elif image_url.startswith("file://"):
            # File path - read and encode to base64
            file_path = image_url[7:]
            if not os.path.isabs(file_path):
                file_path = assemble_workspace_path(file_path)
            if os.path.exists(file_path):
                # Read file and encode to base64
                with open(file_path, "rb") as f:
                    image_data = f.read()
                base64_data = base64.b64encode(image_data).decode("utf-8")
                # Guess media type from file extension
                import mimetypes
                guessed_type, _ = mimetypes.guess_type(file_path)
                if not guessed_type or not guessed_type.startswith("image/"):
                    media_type = "image/jpeg"  # default
                else:
                    media_type = AnthropicChatSerializer._normalize_media_type(guessed_type)
                return {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64_data,
                    }
                }
        elif os.path.exists(image_url):
            # Direct file path
            with open(image_url, "rb") as f:
                image_data = f.read()
            base64_data = base64.b64encode(image_data).decode("utf-8")
            import mimetypes
            guessed_type, _ = mimetypes.guess_type(image_url)
            if not guessed_type or not guessed_type.startswith("image/"):
                media_type = "image/jpeg"  # default
            else:
                media_type = AnthropicChatSerializer._normalize_media_type(guessed_type)
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data,
                }
            }
        elif os.path.exists(assemble_workspace_path(image_url)):
            # Relative file path
            file_path = assemble_workspace_path(image_url)
            with open(file_path, "rb") as f:
                image_data = f.read()
            base64_data = base64.b64encode(image_data).decode("utf-8")
            import mimetypes
            guessed_type, _ = mimetypes.guess_type(file_path)
            if not guessed_type or not guessed_type.startswith("image/"):
                media_type = "image/jpeg"  # default
            else:
                media_type = AnthropicChatSerializer._normalize_media_type(guessed_type)
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data,
                }
            }
        elif image_url.startswith(("http://", "https://")):
            # Remote URL — the Anthropic API fetches it server-side.
            return {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": image_url,
                }
            }
        else:
            raise ValueError(f"Unsupported image source for Anthropic API: {image_url}")

    @staticmethod
    def _serialize_user_content(
        content: Union[str, List[Union[ContentPartText, ContentPartImage]]],
    ) -> List[dict[str, Any]]:
        """Serialize content for user messages (text and images allowed).
        
        Anthropic requires content to always be an array, even for text-only messages.
        """
        serialized_parts: List[dict[str, Any]] = []
        
        if isinstance(content, str):
            # Convert string to text content block
            serialized_parts.append({"type": "text", "text": content})
        else:
            # Process content parts
            for part in content:
                if part.type == 'text':
                    serialized_parts.append(AnthropicChatSerializer._serialize_content_part_text(part))
                elif part.type == 'image_url':
                    serialized_parts.append(AnthropicChatSerializer._serialize_content_part_image(part))
        
        return serialized_parts

    @staticmethod
    def _serialize_assistant_content(
        content: Optional[Union[str, List[ContentPartText]]],
    ) -> List[dict[str, Any]]:
        """Serialize content for assistant messages (text only, tool_use handled separately).
        
        Anthropic requires content to always be an array, even for text-only messages.
        """
        serialized_parts: List[dict[str, Any]] = []
        
        if content is None:
            return serialized_parts
        
        if isinstance(content, str):
            # Convert string to text content block
            serialized_parts.append({"type": "text", "text": content})
        else:
            # Process content parts
            for part in content:
                if part.type == 'text':
                    serialized_parts.append(AnthropicChatSerializer._serialize_content_part_text(part))
        
        return serialized_parts

    @staticmethod
    def _serialize_tool_call(tool_call: ToolCall) -> dict[str, Any]:
        """Serialize tool call for Anthropic API.
        
        Anthropic expects: {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
        """
        import json
        try:
            input_data = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
        except json.JSONDecodeError:
            input_data = {}
        
        return {
            "type": "tool_use",
            "id": tool_call.id,
            "name": tool_call.function.name,
            "input": input_data,
        }

    @overload
    @staticmethod
    def serialize(message: HumanMessage) -> dict[str, Any]: ...

    @overload
    @staticmethod
    def serialize(message: SystemMessage) -> dict[str, Any]: ...

    @overload
    @staticmethod
    def serialize(message: AssistantMessage) -> dict[str, Any]: ...

    @staticmethod
    def serialize(message: Message) -> dict[str, Any]:
        """Serialize a custom message to an Anthropic message format."""
        if isinstance(message, HumanMessage):
            content = AnthropicChatSerializer._serialize_user_content(message.content)
            result: dict[str, Any] = {
                'role': 'user',
                'content': content,
            }
            return result

        elif isinstance(message, SystemMessage):
            # System messages are handled separately (top-level system field)
            # Return None or empty dict to indicate it should be extracted
            content = message.content
            if isinstance(content, str):
                return {'role': 'system', 'content': content}
            elif isinstance(content, list):
                # Extract text from content parts
                text_parts = []
                for part in content:
                    if isinstance(part, ContentPartText):
                        text_parts.append(part.text)
                return {'role': 'system', 'content': ' '.join(text_parts)}
            else:
                return {'role': 'system', 'content': str(content)}

        elif isinstance(message, AssistantMessage):
            content_parts = AnthropicChatSerializer._serialize_assistant_content(message.content)
            result: dict[str, Any] = {'role': 'assistant'}
            
            # Add tool calls to content array
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    content_parts.append(AnthropicChatSerializer._serialize_tool_call(tool_call))
            
            # Content is always an array (may be empty)
            result['content'] = content_parts
            
            return result

        else:
            raise ValueError(f'Unknown message type: {type(message)}')

    @staticmethod
    def serialize_messages(messages: List[Message]) -> tuple[Optional[str], List[dict[str, Any]]]:
        """
        Serialize messages to Anthropic format.
        
        Returns:
            Tuple of (system_message, messages_list)
            system_message: Optional string for system prompt (extracted from SystemMessage)
            messages_list: List of message dicts (excluding SystemMessage)
        """
        system_message = None
        anthropic_messages: List[dict[str, Any]] = []
        
        for message in messages:
            if isinstance(message, SystemMessage):
                # Extract system message
                serialized = AnthropicChatSerializer.serialize(message)
                if serialized.get('content'):
                    if system_message is None:
                        system_message = serialized['content']
                    else:
                        system_message += "\n" + serialized['content']
            else:
                # Serialize user/assistant messages
                anthropic_messages.append(AnthropicChatSerializer.serialize(message))
        
        return system_message, anthropic_messages

    @staticmethod
    def serialize_tools(tools: List["Tool"]) -> List[Dict[str, Any]]:
        """
        Serialize tools for Anthropic API calls. Convert Tool instances to Anthropic tools format.
        
        Anthropic tools format:
        [
            {
                "name": "...",
                "description": "...",
                "input_schema": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            }
        ]
        
        Args:
            tools: List of Tool instances
            
        Returns:
            List of Anthropic tools format dicts
        """
        formatted_tools = []
        for tool in tools:
            # Accept a Tool-like instance (carries .function_calling) OR a raw
            # OpenAI-style function_calling dict. Avoid isinstance(Tool) — Tool is
            # only imported under TYPE_CHECKING here, and native tool assembly passes
            # schema-only Tool shims / dicts.
            fc = tool if isinstance(tool, dict) else getattr(tool, "function_calling", None)
            if not fc:
                continue
            function_def = fc.get("function", {})
            formatted_tools.append({
                "name": function_def.get("name") or getattr(tool, "name", ""),
                "description": function_def.get("description") or getattr(tool, "description", ""),
                "input_schema": function_def.get("parameters") or {"type": "object", "properties": {}},
            })

        return formatted_tools
    
    @staticmethod
    def serialize_response_format(
        response_format: Union[Type[BaseModel], BaseModel, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Format response_format to Anthropic's output_format parameter.
        
        Anthropic uses output_format with beta API:
        - Requires beta API: client.beta.messages.create()
        - Requires betas parameter: ['structured-outputs-2025-11-13']
        - Format: {"type": "json_schema", "schema": {...}}
        - CRITICAL: Anthropic has strict schema requirements, optimized here to reduce complexity
        
        Args:
            response_format: BaseModel class, instance, or dict
            
        Returns:
            Dictionary containing output_format configuration:
            - type: "json_schema"
            - schema: JSON schema (optimized to reduce complexity and resolve references)
        """
        if isinstance(response_format, dict):
            # Dict format - check if it's already in output_format format
            if "type" in response_format and "schema" in response_format:
                return response_format
            elif "type" in response_format and "json_schema" in response_format:
                json_schema_obj = response_format["json_schema"]
                schema = json_schema_obj.get("schema", {})
                return {
                    'type': 'json_schema',
                    'schema': schema
                }
            else:
                return {
                    'type': 'json_schema',
                    'schema': response_format
                }

        model_class = response_format if isinstance(response_format, type) else type(response_format)
        if not issubclass(model_class, BaseModel):
            raise ValueError(f"Unsupported response_format type: {type(response_format)}")

        # Use Anthropic's transform_schema if available, but we'll still apply our transform
        # to ensure $defs are resolved and optional fields are simplified
        if transform_schema is not None:
            schema = transform_schema(model_class)
        else:
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

        return {
            'type': 'json_schema',
            'schema': transform(schema)
        }
