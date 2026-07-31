"""Mdify tool for converting various file formats to markdown text."""

import asyncio
import os
from typing import Any, Optional, Dict
from pydantic import Field

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.tool.default.markdown.mdconvert import MarkitdownConverter
from autogenesis.logger import logger
from autogenesis.registry import TOOL

_DESCRIPTION = "Convert various file formats to markdown text using markitdown and save to base_dir folder."

_INSTRUCTION = """
## Function
Convert various file formats to markdown text using markitdown and save to base_dir folder.

## Guidance
This tool converts files to markdown format and saves the converted markdown text to the base_dir folder for easy text processing and analysis.
The input should be a file path (absolute path recommended) to the file you want to convert.

Supported file formats:
- Documents: PDF, DOCX, PPTX, XLSX, XLS, CSV, TXT, HTML, EPUB
- Images: PNG, JPG, JPEG, GIF, BMP, TIFF, WEBP (with OCR text extraction)
- Audio: MP3, WAV, MP4, M4A (with speech-to-text transcription)
- Archives: ZIP (extracts and converts contents)
- Data: IPYNB (Jupyter notebooks), RSS feeds
- Email: MSG (Outlook messages)
- Web: Wikipedia pages, YouTube videos (metadata and transcripts)
- Plain text files

The tool will extract text content, tables, metadata, and other structured information from these files, convert them into readable markdown format, and save the result as a .md file in the base_dir folder.

## Parameters
- file_path (str): The absolute path to the file to convert.
- output_format (str): The output format.

## Example
{"name": "mdify_tool", "args": {"file_path": "/path/to/file.pdf", "output_format": "markdown"}}
"""

@TOOL.register_module(force=True)
class MdifyTool(Tool):
    """A tool for converting various file formats to markdown text asynchronously."""

    name: str = "mdify_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    
    timeout: int = Field(description="Timeout in seconds for file conversion", default=60)
    converter: Optional[MarkitdownConverter] = None
    base_dir: Optional[str] = Field(default=None, description="The base directory to use for the mdify tool.")
    
    def __init__(self, base_dir: Optional[str] = None, enable_evolving: bool = False, **kwargs):
        """A tool for converting various file formats to markdown text asynchronously."""
        super().__init__(enable_evolving=enable_evolving, **kwargs)

        if base_dir is not None:
            self.base_dir = base_dir
        
        if self.base_dir is not None:
            os.makedirs(self.base_dir, exist_ok=True)
        logger.info(f"| Mdify tool base directory: {self.base_dir}")

    def model_post_init(self, __context: Any) -> None:
        """Lazily construct the MarkitdownConverter after pydantic model init.

        Runs once the tool's fields are populated so the converter can honor the
        configured ``timeout``; skipped if a converter was already supplied.
        """
        if self.converter is None:
            self.converter = MarkitdownConverter(timeout=self.timeout)

    async def __call__(self, file_path: str, output_format: str = "markdown", **kwargs) -> Response:
        """
        Convert a file to markdown asynchronously.

        Args:
            file_path (str): Absolute path to the file to convert.
            output_format (str): Output format.
        """
        try:
            # Validate input
            if not file_path.strip():
                return Response(type=ResponseType.TOOL, success=False, message="Error: Empty file path provided")
            
            # Check if file exists
            if not os.path.exists(file_path):
                return Response(type=ResponseType.TOOL, success=False, message=f"Error: File not found: {file_path}")
            
            # Check if it's a file (not directory)
            if not os.path.isfile(file_path):
                return Response(type=ResponseType.TOOL, success=False, message=f"Error: Path is not a file: {file_path}")
            
            # Get file info
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # Check file size (limit to 100MB for safety)
            max_size = 100 * 1024 * 1024  # 100MB
            if file_size > max_size:
                return Response(type=ResponseType.TOOL, 
                    success=False, message=f"Error: File too large ({file_size / (1024*1024):.1f}MB). "
                           f"Maximum allowed size is {max_size / (1024*1024)}MB"
                )
            
            # Run conversion in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._convert_file, 
                file_path, 
                output_format
            )
            
            if result is None:
                return Response(type=ResponseType.TOOL, success=False, message="Error: Conversion failed - unable to process the file")
            
            # Save to base_dir if specified
            saved_path = None
            if self.base_dir:
                # Create base_dir if it doesn't exist
                os.makedirs(self.base_dir, exist_ok=True)
                
                # Generate output filename (replace original extension with .md)
                base_name = os.path.splitext(file_name)[0]
                output_filename = f"{base_name}.md"
                saved_path = os.path.join(self.base_dir, output_filename)
                
                # Save markdown content to file
                with open(saved_path, 'w', encoding='utf-8') as f:
                    f.write(result)
                
                logger.info(f"| Saved converted markdown to: {saved_path}")
            
            # Format the response
            response_content = f"Successfully converted file: {file_name}\n"
            response_content += f"File size: {file_size / 1024:.1f} KB\n"
            response_content += f"File extension: {file_ext}\n"
            response_content += f"Output format: {output_format}\n"
            if saved_path:
                response_content += f"Saved to: {saved_path}\n"
            response_content += result
            
            message = response_content
            logger.info(f"| ✅ Converted file {file_path} to {output_format} and saved to {saved_path}")
            return Response(type=ResponseType.TOOL, 
                success=True,
                message=message,
                files=[saved_path] if saved_path else None,
                data={
                    "file_name": file_name,
                    "file_size": file_size,
                    "file_ext": file_ext,
                    "output_format": output_format,
                    "saved_path": saved_path
                }
            )
            
        except asyncio.TimeoutError:
            return Response(type=ResponseType.TOOL, success=False, 
                                message=f"Error: Conversion timed out after {self.timeout} seconds")
        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, 
                                message=f"Error during conversion: {str(e)}")

    def _convert_file(self, file_path: str, output_format: str) -> Optional[str]:
        """Convert file to markdown (synchronous helper method)."""
        try:
            result = self.converter.convert(file_path)
            if result and hasattr(result, 'markdown'):
                return result.markdown
            elif isinstance(result, str):
                return result
            else:
                return None
        except Exception as e:
            # Log the error but don't raise it
            logger.error(f"Conversion error: {e}")
            return None