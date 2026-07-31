"""Dynamic Module Manager for runtime code execution and class/function loading."""

import importlib
import importlib.util
import os
import sys
import inspect
import ast
import json
import re
from copy import deepcopy
from typing import Type, Optional, TypeVar, Any, Dict, List, Set, Callable, Union, get_type_hints, Tuple

import inflection
from pydantic import BaseModel, ConfigDict, Field, create_model

T = TypeVar('T')

# Constants
PYTHON_TYPE_FIELD = "x-python-type"
JSON_TO_PYTHON_TYPE = {
    "integer": "int",
    "number": "float",
    "string": "str",
    "boolean": "bool",
    "object": "dict",
    "array": "list",
}


class DynamicModuleManager:
    """Manager for dynamically creating Python modules and loading classes/functions.
    
    This class provides utilities for:
    - Creating virtual modules in memory (not on disk)
    - Loading classes and functions from source code strings
    - Managing dynamically generated code
    - Automatically injecting necessary imports based on code analysis
    - Building parameter schemas and Pydantic models
    """
    
    def __init__(self):
        """Initialize the dynamic module manager."""
        self._module_counter = 0
        self._loaded_modules: Dict[str, Any] = {}  # module_name -> module object
        # Symbol name -> object mapping for auto-injection
        self._symbol_registry: Dict[str, Any] = {}
        # Context-based import providers: context_name -> callable that returns imports dict
        self._context_providers: Dict[str, Callable[[], Dict[str, Any]]] = {}
    
    def default_parameters_schema(self) -> Dict[str, Any]:
        """Default empty parameters schema."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    
    def parse_docstring_descriptions(self, docstring: str) -> Dict[str, str]:
        """Parse parameter descriptions from Google-style docstrings.
        
        Args:
            docstring: The docstring to parse
            
        Returns:
            Dictionary mapping parameter names to descriptions
        """
        if not docstring:
            return {}

        descriptions: Dict[str, str] = {}
        lines = inspect.cleandoc(docstring).splitlines()
        in_args = False

        for line in lines:
            stripped = line.strip()
            if not in_args:
                if stripped.lower().startswith("args"):
                    in_args = True
                continue

            if stripped.lower().startswith(("returns:", "yields:", "raises:", "examples:")):
                break

            match = re.match(r"^\s*(\w+)\s*(?:\([^)]*\))?\s*:\s*(.+)$", stripped)
            if match:
                param_name = match.group(1)
                description = match.group(2).strip()
                descriptions[param_name] = description

        return descriptions


    def annotation_to_types(self, annotation: Any) -> Tuple[str, str]:
        """Convert Python type annotation to JSON type and Python type string.
        
        Args:
            annotation: Python type annotation
            
        Returns:
            Tuple of (json_type, python_type_string)
        """
        if annotation is inspect._empty or annotation is None:
            return "string", "Any"

        basic_map = {
            str: ("string", "str"),
            int: ("integer", "int"),
            float: ("number", "float"),
            bool: ("boolean", "bool"),
            dict: ("object", "dict"),
            list: ("array", "list"),
        }
        if annotation in basic_map:
            return basic_map[annotation]

        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())

        if origin is Union and len(args) == 2 and type(None) in args:
            inner_type = args[0] if args[1] is type(None) else args[1]
            json_type, python_type = self.annotation_to_types(inner_type)
            return json_type, f"Optional[{python_type}]"

        if origin is list or (hasattr(annotation, "__origin__") and "List" in str(annotation)):
            return "array", "list"

        if origin is dict or (hasattr(annotation, "__origin__") and "Dict" in str(annotation)):
            return "object", "dict"

        type_str = str(annotation).replace("typing.", "")
        return "string", type_str

    def annotation_to_item_schema(self, annotation: Any) -> Dict[str, Any]:
        """Return the JSON schema for the *element* type of an array annotation.

        JSON Schema (and strict consumers like the Gemini API) require every
        ``array`` to declare ``items``. Handles ``List[X]`` / ``list[X]`` and
        ``Optional[List[X]]``; recurses for nested lists; defaults to
        ``{"type": "string"}`` when the element type is unparametrized/unknown.
        """
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())

        # Unwrap Optional[List[X]] / Union[List[X], None]
        if origin is Union and len(args) == 2 and type(None) in args:
            inner = args[0] if args[1] is type(None) else args[1]
            return self.annotation_to_item_schema(inner)

        if origin is list or (hasattr(annotation, "__origin__") and "List" in str(annotation)):
            elem_args = getattr(annotation, "__args__", ())
            if elem_args and elem_args[0] is not type(None):
                elem = elem_args[0]
                elem_json, _ = self.annotation_to_types(elem)
                elem_schema: Dict[str, Any] = {"type": elem_json}
                if elem_json == "array":
                    elem_schema["items"] = self.annotation_to_item_schema(elem)
                return elem_schema

        return {"type": "string"}


    def parse_type_string(self, type_str: str) -> Type:
        """Parse a type string (e.g., 'str', 'Optional[str]', 'List[str]', 'Dict[str, Any]') to Python type.
        
        Supports both Python type names (str, int) and JSON schema type names (string, integer).
        Also handles 'typing.' prefix and detailed Dict[K, V] parsing.
        
        Args:
            type_str: Type string to parse
            
        Returns:
            Python type
        """
        # Remove typing. prefix if present
        type_str = type_str.replace("typing.", "").strip()
        
        # Handle common types (both Python and JSON schema names)
        mapping = {
            "str": str,
            "string": str,
            "int": int,
            "integer": int,
            "float": float,
            "number": float,
            "bool": bool,
            "boolean": bool,
            "dict": dict,
            "object": dict,
            "list": list,
            "array": list,
            "Any": Any,
        }
        if type_str in mapping:
            return mapping[type_str]
        
        # Handle Optional[Type]
        if type_str.startswith("Optional[") and type_str.endswith("]"):
            inner = type_str[9:-1].strip()
            return Optional[self.parse_type_string(inner)]  # type: ignore[index]
        
        # Handle List[Type]
        if type_str.startswith("List[") and type_str.endswith("]"):
            inner = type_str[5:-1].strip()
            return List[self.parse_type_string(inner)]  # type: ignore[index]
        
        # Handle Dict[K, V] - parse key and value types if provided
        if type_str.startswith("Dict[") and type_str.endswith("]"):
            inner = type_str[5:-1].strip()
            # Try to parse Dict[K, V] format
            if "," in inner:
                parts = inner.split(",", 1)
                if len(parts) == 2:
                    key_type = self.parse_type_string(parts[0].strip())
                    value_type = self.parse_type_string(parts[1].strip())
                    return Dict[key_type, value_type]  # type: ignore[index]
            # Fallback to generic dict if parsing fails
            return dict
        
        # Default to Any if can't parse
        return Any

    def json_type_to_python_type(self, json_type: str) -> Type:
        """Convert JSON schema type to Python type.
        
        Args:
            json_type: JSON schema type (e.g., "string", "integer", "number")
            
        Returns:
            Python type
        """
        mapping = {
            "integer": int,
            "number": float,
            "string": str,
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        return mapping.get(json_type, str)

    def remove_python_type_field(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Remove x-python-type field from schema recursively.
        
        Args:
            schema: Schema dictionary
            
        Returns:
            Cleaned schema dictionary
        """
        cleaned = deepcopy(schema)
        cleaned.pop(PYTHON_TYPE_FIELD, None)
        if "properties" in cleaned:
            for prop_info in cleaned["properties"].values():
                if isinstance(prop_info, dict):
                    prop_info.pop(PYTHON_TYPE_FIELD, None)
        return cleaned


    def build_args_schema(self, name: str, schema: Dict[str, Any]) -> Type[BaseModel]:
        """Create a Pydantic model from a parameter schema.
        
        Args:
            name: Name for the model (will be converted to PascalCase + "Input")
            schema: Parameter schema dictionary
            
        Returns:
            Pydantic BaseModel class
        """
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        model_name = inflection.camelize(name) + "Input"

        if not properties:
            return create_model(
                model_name,
                __config__=ConfigDict(arbitrary_types_allowed=True, extra="allow"),
            )

        field_definitions: Dict[str, Any] = {}
        for param_name, param_info in properties.items():
            python_type_str = param_info.get(PYTHON_TYPE_FIELD)
            if python_type_str:
                python_type = self.parse_type_string(python_type_str)
            else:
                json_type = param_info.get("type", "string")
                python_type = self.json_type_to_python_type(json_type)

            is_required = param_name in required
            if "default" in param_info:
                default_value = param_info["default"]
            elif is_required:
                default_value = ...  # Required
            else:
                default_value = None

            description = param_info.get("description", "")
            if is_required and default_value is ...:
                field_definitions[param_name] = (
                    python_type,
                    Field(description=description),
                )
            else:
                field_definitions[param_name] = (
                    Optional[python_type] if not is_required else python_type,
                    Field(default=default_value, description=description),
                )

        return create_model(
            model_name,
            __config__=ConfigDict(arbitrary_types_allowed=True, extra="allow"),
            **field_definitions,
        )

    def build_function_calling(self, name: str, description: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Build OpenAI-compatible function-calling representation.
        
        Args:
            name: Name of the tool/action
            description: Description of the tool/action
            schema: Parameter schema dictionary (will be cleaned by removing x-python-type fields)
            
        Returns:
            OpenAI-compatible function-calling dictionary
        """
        # Remove x-python-type field from schema as it's only for internal use
        cleaned_schema = self.remove_python_type_field(schema)
        
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": cleaned_schema,
            },
        }


    def build_text_representation(self, name: str, description: str, schema: Dict[str, Any], entity_type: str = "Tool") -> str:
        """Build a human-readable text representation.
        
        Args:
            name: Name of the tool/action
            description: Description
            schema: Parameter schema dictionary
            entity_type: Type of entity ("Tool" or "Action")
            
        Returns:
            Human-readable text representation
        """
        text = f"{entity_type}: {name}\nDescription: {description}\n"
        return text
    
    def _generate_module_name(self, prefix: str = "dynamic_module") -> str:
        """Generate a unique virtual module name.
        
        Args:
            prefix: Prefix for the module name
            
        Returns:
            A unique module name like "_dynamic_module_1", "_dynamic_module_2", etc.
        """
        self._module_counter += 1
        # This is a virtual module name - it will be added to sys.modules dynamically
        # It does NOT need to exist as a file on disk
        return f"_{prefix}_{self._module_counter}"
    
    def is_dynamic_class(self, cls: Type) -> bool:
        """Check if a class is dynamically generated (not from a real module file).
        
        Args:
            cls: The class to check
            
        Returns:
            True if the class appears to be dynamically generated
        """
        if not hasattr(cls, '__module__'):
            return True
        module_name = cls.__module__
        # Check if it's a dynamic module
        return (module_name in ('__main__', '<string>', '<exec>') or 
                module_name.startswith('_dynamic_') or
                '<' in module_name)
    
    def get_source_code(self, object: Union[Type['T'], Callable]) -> Optional[str]:
        """Extract source code of a class or callable object if possible.

        Args:
            object: The class or callable object to extract source code from

        Returns:
            Source code string if available, None otherwise
        """
        try:
            return inspect.getsource(object)
        except (OSError, TypeError):
            pass
        # Fallback: read from __source_file__ set by registration hooks on dynamically loaded classes
        source_file = getattr(object, "__source_file__", None)
        if source_file and os.path.isfile(source_file):
            try:
                with open(source_file, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                pass
        return None
    
    def get_full_module_source(self, cls: Type) -> str:
        """Get the full source code of the module containing the class, including all imports.
        
        This is more reliable than inspect.getsource() which only gets the class definition.
        By reading the entire module file, we preserve all import statements and module-level code,
        ensuring the complete context is available when loading from JSON.
        
        Args:
            cls: The class to get module source for
            
        Returns:
            Full module source code as string, or class source if file reading fails
        """
        try:
            # Get the module object
            module = inspect.getmodule(cls)
            if module is None:
                # Fallback to inspect.getsource if module is not available
                return inspect.getsource(cls)
            
            # Get the file path of the module
            file_path = inspect.getfile(module)
            
            # Read the entire file to preserve all imports and context
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except (OSError, TypeError, IOError, AttributeError) as e:
            # Fallback to inspect.getsource if file reading fails
            try:
                return inspect.getsource(cls)
            except Exception:
                return ""
    
    def extract_class_name_from_code(self, code: str) -> Optional[str]:
        """Extract the first class name from source code.
        
        Args:
            code: Source code string
            
        Returns:
            First class name found, or None
        """
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    return node.name
        except Exception:
            pass
        return None
    
    def register_symbol(self, name: str, obj: Any) -> None:
        """Register a symbol that can be auto-injected into dynamic code.
        
        Args:
            name: Symbol name (e.g., "TOOL", "Tool")
            obj: The object to inject
        """
        self._symbol_registry[name] = obj
    
    def register_context_provider(self, context_name: str, provider: Callable[[], Dict[str, Any]]) -> None:
        """Register a context-based import provider.
        
        Args:
            context_name: Context identifier (e.g., "tool", "agent")
            provider: Callable that returns a dict of {symbol_name: object} to inject
        """
        self._context_providers[context_name] = provider
    
    def _extract_used_symbols(self, code: str) -> Set[str]:
        """Extract all symbol names used in the code (excluding builtins and imports).
        
        Args:
            code: Source code string
            
        Returns:
            Set of symbol names used in the code
        """
        used_symbols = set()
        
        try:
            tree = ast.parse(code)
            
            class SymbolCollector(ast.NodeVisitor):
                def __init__(self):
                    self.imports = set()
                    self.names = set()
                    self.in_def = False  # Track if we're inside a function/class definition
                
                def visit_Import(self, node):
                    for alias in node.names:
                        self.imports.add(alias.asname or alias.name)
                
                def visit_ImportFrom(self, node):
                    for alias in node.names:
                        self.imports.add(alias.asname or alias.name)
                
                def visit_FunctionDef(self, node):
                    self.imports.add(node.name)  # Function name is not a used symbol
                    self.generic_visit(node)
                
                def visit_AsyncFunctionDef(self, node):
                    self.imports.add(node.name)  # Function name is not a used symbol
                    self.generic_visit(node)
                
                def visit_ClassDef(self, node):
                    self.imports.add(node.name)  # Class name is not a used symbol
                    self.generic_visit(node)
                
                def visit_Name(self, node):
                    # Only collect names that are loaded (used), not stored (assigned)
                    if isinstance(node.ctx, ast.Load):
                        self.names.add(node.id)
            
            collector = SymbolCollector()
            collector.visit(tree)
            
            # Return names that are used but not imported
            # Exclude common builtins and special names
            excluded = collector.imports | {
                'self', 'cls', 'super', '__name__', '__main__', '__file__', '__doc__',
                'True', 'False', 'None', 'Exception', 'BaseException',
                'object', 'type', 'str', 'int', 'float', 'bool', 'list', 'dict', 'tuple', 'set'
            }
            used_symbols = collector.names - excluded
            
        except Exception:
            # If parsing fails, return empty set
            pass
        
        return used_symbols
    
    def _auto_inject_imports(self, code: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Automatically determine which imports to inject based on code analysis.
        
        Args:
            code: Source code string
            context: Optional context name (e.g., "tool", "agent") for context-specific imports
            
        Returns:
            Dict of {symbol_name: object} to inject
        """
        imports = {}
        
        # Add context-specific imports if context is provided
        if context and context in self._context_providers:
            context_imports = self._context_providers[context]()
            imports.update(context_imports)
        
        # Extract symbols used in code
        used_symbols = self._extract_used_symbols(code)
        
        # Auto-inject symbols that are used and registered
        for symbol_name in used_symbols:
            if symbol_name in self._symbol_registry:
                imports[symbol_name] = self._symbol_registry[symbol_name]
        
        return imports
    
    def load_code(self, 
                        code: str, 
                        module_name: Optional[str] = None, 
                        context: Optional[str] = None,
                        inject_imports: Optional[Dict[str, Any]] = None) -> str:
        """Load code into a virtual module and return the module name.
        
        Args:
            code: Source code string to execute
            module_name: Optional module name. If None, a unique name will be generated.
            context: Optional context name (e.g., "tool", "agent") for auto-injection
            inject_imports: Optional dict of {symbol_name: object} to inject manually.
                           If None, will auto-detect based on code analysis.
            
        Returns:
            The module name that was used
            
        Raises:
            Exception: If code execution fails
        """
        if module_name is None:
            module_name = self._generate_module_name()
        
        # Create a new module object (virtual, in memory only)
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        
        # Determine imports to inject
        if inject_imports is None:
            inject_imports = self._auto_inject_imports(code, context)
        else:
            # Merge with auto-detected imports
            auto_imports = self._auto_inject_imports(code, context)
            inject_imports = {**auto_imports, **inject_imports}
        
        # Inject imports into module namespace
        for name, obj in inject_imports.items():
            setattr(module, name, obj)
        
        # Execute the code in the module namespace
        exec(code, module.__dict__)
        
        # Add to sys.modules so Python treats it as a real importable module
        # This is a runtime virtual module - no file on disk needed
        sys.modules[module_name] = module
        
        # Store reference
        self._loaded_modules[module_name] = module
        
        return module_name
    
    def load_class(self, 
                   code: str, 
                   class_name: Optional[str] = None, 
                   base_class: Optional[Type[T]] = None, 
                   module_name: Optional[str] = None,
                   context: Optional[str] = None,
                   inject_imports: Optional[Dict[str, Any]] = None) -> Type[T]:
        """Dynamically load a class from source code.
        
        This function creates a virtual Python module in memory (not on disk) by:
        1. Generating a unique module name (doesn't need to exist as a file)
        2. Creating a module object using importlib
        3. Executing the code in the module's namespace
        4. Adding it to sys.modules so Python treats it as a real module
        
        Args:
            code: Source code string containing the class definition
            class_name: Name of the class to extract. If None, will try to extract from code.
            base_class: Optional base class to validate against (e.g., Tool, Agent)
            module_name: Optional module name. If None, a unique name will be generated.
            context: Optional context name (e.g., "tool", "agent") for auto-injection
            inject_imports: Optional dict of {symbol_name: object} to inject manually.
                           If None, will auto-detect based on code analysis.
            
        Returns:
            The loaded class
            
        Raises:
            ValueError: If the class cannot be found or loaded, or doesn't inherit from base_class
        """
        # Determine context from base_class if not provided
        if context is None and base_class is not None:
            # Try to infer context from base class name
            base_name = base_class.__name__.lower()
            if 'tool' in base_name:
                context = "tool"
            elif 'agent' in base_name:
                context = "agent"
            elif 'prompt' in base_name:
                context = "prompt"
        
        # Load code into module first (needed to find classes)
        if module_name is None:
            module_name = self.load_code(code, context=context, inject_imports=inject_imports)
        else:
            if module_name not in self._loaded_modules:
                self.load_code(code, module_name, context=context, inject_imports=inject_imports)
        
        # Get module
        module = self._loaded_modules[module_name]
        
        # Extract class name if not provided
        if class_name is None:
            if base_class is not None:
                # Find all classes that inherit from base_class
                candidate_classes = []
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, base_class) and 
                        attr is not base_class):
                        candidate_classes.append((attr_name, attr))
                
                if len(candidate_classes) == 0:
                    raise ValueError(f"No class found in code that inherits from {base_class.__name__}")
                elif len(candidate_classes) == 1:
                    class_name = candidate_classes[0][0]
                else:
                    # Multiple candidates - prefer classes with @AGENT/@TOOL/@PROMPT decorator or matching naming patterns
                    preferred = []
                    for name, cls in candidate_classes:
                        try:
                            source = inspect.getsource(cls)
                            if '@AGENT' in source or '@TOOL' in source or '@PROMPT' in source or name.endswith('Agent') or name.endswith('Tool') or name.endswith('Prompt'):
                                preferred.append((name, cls))
                        except:
                            if name.endswith('Agent') or name.endswith('Tool') or name.endswith('Prompt'):
                                preferred.append((name, cls))
                    
                    if preferred:
                        class_name = preferred[0][0]
                    else:
                        # Fall back to first candidate
                        class_name = candidate_classes[0][0]
            else:
                # No base_class provided, extract first class from code
                class_name = self.extract_class_name_from_code(code)
                if not class_name:
                    raise ValueError("Cannot determine class name from code. Please provide class_name or base_class.")
        
        # Extract the class
        if not hasattr(module, class_name):
            raise ValueError(f"Class {class_name} not found in the provided code")
        
        cls = getattr(module, class_name)
        
        # Validate base class if provided
        if base_class is not None:
            if not issubclass(cls, base_class):
                raise ValueError(f"Class {class_name} is not a subclass of {base_class.__name__}")

        return cls

    def load_class_from_path(self,
                             file_path: str,
                             class_name: Optional[str] = None,
                             base_class: Optional[Type[T]] = None,
                             module_name: Optional[str] = None,
                             context: Optional[str] = None,
                             inject_imports: Optional[Dict[str, Any]] = None) -> Type[T]:
        """Load a class from a Python file on disk.

        Thin wrapper over :meth:`load_class` that reads the file first. Pass an
        explicit, version-scoped ``module_name`` (e.g. ``ext.v1_0_0.tool.calculator``)
        so dynamically loaded extensions never collide in ``sys.modules`` across
        versions and can be cleanly unloaded with :meth:`unload_module`.

        Args:
            file_path: Path to the .py file containing the class.
            class_name: Class to extract (auto-detected from base_class if None).
            base_class: Optional base class to validate against.
            module_name: Optional explicit (version-scoped) module name.
            context: Optional context ("tool"/"agent"/...) for auto-injection.
            inject_imports: Optional manual import injections.

        Returns:
            The loaded class.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        # Force a fresh load when an explicit module_name is reused (hot-reload).
        if module_name is not None and module_name in self._loaded_modules:
            self.unload_module(module_name)
        return self.load_class(
            code,
            class_name=class_name,
            base_class=base_class,
            module_name=module_name,
            context=context,
            inject_imports=inject_imports,
        )

    def unload_module(self, module_name: str) -> None:
        """Remove a dynamically loaded virtual module from memory and sys.modules.

        Used when hot-unloading / swapping an extension version so stale code does
        not linger. Safe to call on unknown module names.
        """
        self._loaded_modules.pop(module_name, None)
        sys.modules.pop(module_name, None)
    
    def load_function(self, 
                      code: str, 
                      function_name: Optional[str] = None,
                      module_name: Optional[str] = None) -> Any:
        """Dynamically load a function from source code.
        
        Args:
            code: Source code string containing the function definition
            function_name: Name of the function to extract. If None, will try to extract from code.
            module_name: Optional module name. If None, a unique name will be generated.
            
        Returns:
            The loaded function
            
        Raises:
            ValueError: If the function cannot be found
        """
        # Extract function name if not provided
        if function_name is None:
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        function_name = node.name
                        break
            except Exception:
                pass
            
            if not function_name:
                raise ValueError("Cannot determine function name from code. Please provide function_name.")
        
        # Load code into module
        if module_name is None:
            module_name = self.load_code(code)
        else:
            if module_name not in self._loaded_modules:
                self.load_code(code, module_name)
        
        # Get module
        module = self._loaded_modules[module_name]
        
        # Extract the function
        if not hasattr(module, function_name):
            raise ValueError(f"Function {function_name} not found in the provided code")
        
        return getattr(module, function_name)
    
    def get_module(self, module_name: str) -> Optional[Any]:
        """Get a loaded module by name.
        
        Args:
            module_name: The module name
            
        Returns:
            The module object, or None if not found
        """
        return self._loaded_modules.get(module_name)
    
    def get_class_string(self, cls: Type) -> Optional[str]:
        """Get the '<module_name.class_name>' string representation of a class.
        
        Args:
            cls (Type): The class object
            
        Returns:
            String in format '<module_name.class_name>', or None if cannot determine
        """
        if not isinstance(cls, type):
            return None
        
        # Get module name
        module_name = getattr(cls, '__module__', None)
        if not module_name:
            return None
        
        # Get class name
        class_name = getattr(cls, '__name__', None)
        if not class_name:
            return None
        
        return f"<{module_name}.{class_name}>"
    
    def list_loaded_modules(self) -> List[str]:
        """List all loaded dynamic module names.
        
        Returns:
            List of module names
        """
        return list(self._loaded_modules.keys())
    
    def get_parameters(self, object: Union[Type['T'], Callable]) -> Dict[str, Any]:
        """Get the parameters of a function or class from source code.
        
        Args:
            object (Union[Type['T'], Callable]): The function or class to get parameters for
        """
        try:
            if isinstance(object, Type):
                signature = inspect.signature(object.__call__)
                hints = get_type_hints(object.__call__)
                docstring = inspect.getdoc(object.__call__) or ""
            elif isinstance(object, Callable):
                signature = inspect.signature(object)
                hints = get_type_hints(object)
                docstring = inspect.getdoc(object) or ""
        except Exception as e:
            raise ValueError(f"Failed to get parameters for {object}: {e}")

        # Get descriptions
        doc_descriptions = self.parse_docstring_descriptions(docstring)

        properties = {}
        required = []
        
        for name, param in signature.parameters.items():
            if name == "self":
                continue
            
            # Skip generic "input" parameter
            if name == "input" and len(signature.parameters) == 2:  # self + input
                continue
            
            # Skip VAR_KEYWORD (**kwargs) and VAR_POSITIONAL (*args) parameters
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            
            # Get type annotation
            annotation = hints.get(name, param.annotation)
            json_type, python_type = self.annotation_to_types(annotation)
            
            # Determine if required
            is_required = param.default is inspect._empty
            
            # Build schema
            schema: Dict[str, Any] = {
                "type": json_type,
                "description": doc_descriptions.get(name, ""),
            }
            # Arrays MUST declare their element type (`items`) — strict consumers
            # like the Gemini API reject an array schema without it.
            if json_type == "array":
                schema["items"] = self.annotation_to_item_schema(annotation)
            schema[PYTHON_TYPE_FIELD] = python_type
            
            if not is_required:
                schema["default"] = param.default
            
            properties[name] = schema
            if is_required:
                required.append(name)

        if not properties:
            return self.default_parameters_schema()

        result: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            result["required"] = required
        return result
    
    def serialize_args_schema(self, args_schema: Type[BaseModel]) -> Optional[Dict[str, Any]]:
        """Serialize a BaseModel type to a dictionary with class name and field information.
        
        Args:
            args_schema: BaseModel class type
            
        Returns:
            Dictionary with class_name and fields info, or None if serialization fails
        """
        try:
            schema_info = {
                "class_name": args_schema.__name__,
                "fields": {}
            }
            
            # Extract field information from model_fields
            for field_name, field_info in args_schema.model_fields.items():
                field_data = {
                    "type": str(field_info.annotation) if hasattr(field_info, 'annotation') else "Any",
                    "required": field_info.is_required() if hasattr(field_info, 'is_required') else True,
                }
                
                # Add description if available
                if hasattr(field_info, 'description') and field_info.description:
                    field_data["description"] = field_info.description
                
                # Add default value if available
                if hasattr(field_info, 'default') and field_info.default is not ...:
                    if field_info.default is not None:
                        # Try to serialize default value
                        try:
                            json.dumps(field_info.default)
                            field_data["default"] = field_info.default
                        except (TypeError, ValueError):
                            field_data["default"] = None
                    else:
                        field_data["default"] = None
                
                schema_info["fields"][field_name] = field_data
            
            return schema_info
        except Exception as e:
            raise ValueError(f"Failed to serialize args_schema {args_schema.__name__}: {e}")
        
    def deserialize_args_schema(self, schema_info: Dict[str, Any]) -> Optional[Type[BaseModel]]:
        """Deserialize a BaseModel type from saved schema information.
        
        Args:
            schema_info: Dictionary with class_name and fields info
            
        Returns:
            BaseModel class type, or None if deserialization fails
        """
        try:
            
            class_name = schema_info.get("class_name")
            fields_info = schema_info.get("fields", {})
            
            if not class_name:
                return None
            
            # Build field definitions for create_model
            field_definitions = {}
            for field_name, field_data in fields_info.items():
                # Parse type string (e.g., "str", "Optional[str]", "List[str]")
                type_str = field_data.get("type", "Any")
                python_type = self.parse_type_string(type_str)
                
                # Get default value
                default_value = field_data.get("default")
                is_required = field_data.get("required", True)
                
                if default_value is None and not is_required:
                    # Optional field
                    python_type = Optional[python_type] if python_type != Any else Any
                    default_value = None
                elif default_value is None and is_required:
                    default_value = ...  # Required field
                
                # Create Field with description if available
                description = field_data.get("description", "")
                if description:
                    field_definitions[field_name] = (python_type, Field(default=default_value, description=description))
                else:
                    field_definitions[field_name] = (python_type, default_value)
            
            # Create the model dynamically
            model = create_model(
                class_name,
                __config__=ConfigDict(arbitrary_types_allowed=True, extra="allow"),
                **field_definitions
            )
            
            return model
        except Exception as e:
            raise ValueError(f"Failed to deserialize args_schema: {e}")
        


# Global instance for convenience
dynamic_manager = DynamicModuleManager()

