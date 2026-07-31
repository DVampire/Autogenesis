"""Todo tool for managing todo.md files with task decomposition and step tracking.

This is a coroutine-safe version that uses per-id caching and locking.
"""

import json
import uuid
import os
import asyncio
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.utils import assemble_workspace_path
from autogenesis.utils import file_lock
from autogenesis.registry import TOOL
from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.tool.types import ToolContext


class Step(BaseModel):
    """Step model for todo management."""
    id: str = Field(description="Unique step ID")
    name: str = Field(description="Step name/description")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Step parameters")
    status: str = Field(default="pending", description="Step status: pending, success, failed")
    result: Optional[str] = Field(default=None, description="Step result (1-3 sentences)")
    priority: str = Field(default="medium", description="Step priority: high, medium, low")
    category: Optional[str] = Field(default=None, description="Step category")
    created_at: str = Field(description="Creation timestamp")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp")


class Todo(BaseModel):
    """Todo - A state container for managing todo steps."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    id: str = Field(description="Unique identifier for this todo instance")
    todo_file: str = Field(description="Path to the todo.md file")
    steps_file: str = Field(description="Path to the steps JSON file")
    steps: List[Step] = Field(default_factory=list, description="List of steps")

    def __init__(self, id: str, todo_file: str, steps_file: str, steps: Optional[List[Step]] = None, **kwargs):
        super().__init__(id=id, todo_file=todo_file, steps_file=steps_file, **kwargs)
        if steps is not None:
            self.steps = steps

    def _generate_step_id(self) -> str:
        """Generate a unique step ID using UUID + timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"{timestamp}_{unique_id}"

    async def _save_steps(self) -> None:
        """Save steps to JSON file."""
        try:
            async with file_lock(self.steps_file):
                with open(self.steps_file, 'w', encoding='utf-8') as f:
                    json.dump([step.model_dump() for step in self.steps], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"| ❌ Error saving steps: {e}")

    async def _sync_to_markdown(self) -> None:
        """Sync steps list to markdown file."""
        try:
            async with file_lock(self.todo_file):
                content = "# Todo List\n\n"
                
                for step in self.steps:
                    priority_emoji = {
                        "high": "🔴", 
                        "medium": "🟡", 
                        "low": "🟢"
                    }.get(step.priority, "🟡")
                    
                    status_emoji = {
                        "pending": "⏳",
                        "success": "✅",
                        "failed": "❌"
                    }.get(step.status, "⏳")
                    
                    category_text = f" [{step.category}]" if step.category else ""
                    
                    # Create step line
                    if step.status == "pending":
                        checkbox = "[ ]"
                    else:
                        checkbox = "[x]"
                    
                    step_line = f"- {checkbox} **{step.id}** {priority_emoji} {status_emoji} {step.name}{category_text}"
                    
                    if step.parameters:
                        step_line += f" *(params: {json.dumps(step.parameters)})*"
                    
                    step_line += f" *(created: {step.created_at}*"
                    
                    if step.updated_at:
                        step_line += f", updated: {step.updated_at}"
                    
                    if step.result:
                        step_line += f", result: {step.result}"
                    
                    step_line += ")"
                    content += step_line + "\n"
                
                with open(self.todo_file, 'w', encoding='utf-8') as f:
                    f.write(content)
        except Exception as e:
            logger.error(f"| ❌ Error syncing to markdown: {e}")

    async def add_step(
        self,
        task: str, 
        priority: str = "medium",
        category: Optional[str] = None, 
        parameters: Optional[Dict[str, Any]] = None, 
        after_step_id: Optional[str] = None,
        step_id: Optional[str] = None
    ) -> Step:
        """Add a new step to the todo list.
        
        Args:
            task: Step description
            priority: Priority level (high, medium, low)
            category: Category label
            parameters: Arbitrary metadata for the step
            after_step_id: Insert new step after the specified ID
            step_id: Optional custom step ID
            
        Returns:
            Step: The newly created step
            
        Raises:
            ValueError: If task is empty or step_id already exists
        """
        if not task:
            raise ValueError("Step description is required")
        
        # Use provided step_id or generate a new one
        if step_id is None:
            step_id = self._generate_step_id()
        else:
            # Check if step_id already exists
            for step in self.steps:
                if step.id == step_id:
                    raise ValueError(f"Step ID {step_id} already exists")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        new_step = Step(
            id=step_id,
            name=task,
            parameters=parameters,
            status="pending",
            priority=priority,
            category=category,
            created_at=timestamp
        )
        
        # Insert step at the right position
        if after_step_id:
            # Try to find by ID first
            insert_index = -1
            for i, step in enumerate(self.steps):
                if step.id == after_step_id:
                    insert_index = i + 1
                    break
            
            # If not found by ID, try to find by numeric index (0-based)
            if insert_index == -1:
                try:
                    index = int(after_step_id)
                    if 0 <= index < len(self.steps):
                        insert_index = index + 1
                except ValueError:
                    pass
            
            if insert_index == -1:
                # Not found, add to end
                self.steps.append(new_step)
            else:
                # Insert at the found position
                self.steps.insert(insert_index, new_step)
        else:
            # Add to end of list
            self.steps.append(new_step)
        
        # Save and sync
        await self._save_steps()
        await self._sync_to_markdown()
        
        return new_step

    async def complete_step(
        self, 
        step_id: str, 
        status: str, 
        result: Optional[str] = None
    ) -> Step:
        """Mark step as completed.
        
        Args:
            step_id: The ID of the step to complete
            status: Completion status ("success" or "failed")
            result: Result description
            
        Returns:
            Step: The completed step
            
        Raises:
            ValueError: If step_id is invalid or status is wrong
        """
        if not step_id:
            raise ValueError("Step ID is required")
        
        if status not in ["success", "failed"]:
            raise ValueError("Status must be 'success' or 'failed'")
        
        # Find the step
        step = None
        for s in self.steps:
            if s.id == step_id:
                step = s
                break
        
        if not step:
            raise ValueError(f"Step {step_id} not found")
        
        if step.status != "pending":
            raise ValueError(f"Step {step_id} is already completed with status: {step.status}")
        
        # Update step
        step.status = status
        step.result = result
        step.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Save and sync
        await self._save_steps()
        await self._sync_to_markdown()
        
        return step

    async def update_step(
        self, 
        step_id: str, 
        task: Optional[str] = None, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> Step:
        """Update step information.
        
        Args:
            step_id: The ID of the step to update
            task: New step description
            parameters: New step parameters
            
        Returns:
            Step: The updated step
            
        Raises:
            ValueError: If step_id is invalid
        """
        if not step_id:
            raise ValueError("Step ID is required")
        
        # Find the step
        step = None
        for s in self.steps:
            if s.id == step_id:
                step = s
                break
        
        if not step:
            raise ValueError(f"Step {step_id} not found")
        
        # Update step fields
        if task:
            step.name = task
        if parameters is not None:
            step.parameters = parameters
        
        step.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Save and sync
        await self._save_steps()
        await self._sync_to_markdown()
        
        return step

    async def clear_completed(self) -> List[Step]:
        """Remove all completed steps from the todo list.
        
        Returns:
            List[Step]: The removed steps
        """
        completed_steps = [step for step in self.steps if step.status in ["success", "failed"]]
        
        # Remove completed steps
        self.steps = [step for step in self.steps if step.status == "pending"]
        
        # Save and sync
        await self._save_steps()
        await self._sync_to_markdown()
        
        return completed_steps

    @staticmethod
    def read_content(path: str) -> str:
        """Read a todo.md file's content, or an empty-plan hint if it doesn't exist yet.

        The single source of truth for reading todo content — used both by a Todo
        instance (get_content) and directly by TodoTool.content (no instance needed).
        """
        empty = "[Current todo.md is empty, fill it with your plan when applicable]"
        if not os.path.exists(path):
            return empty
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return empty

    def get_content(self) -> str:
        """Get the content of this todo's markdown file."""
        return self.read_content(self.todo_file)


_DESCRIPTION = "Manage a todo.md file with task decomposition and step tracking."

_INSTRUCTION = """
## Function
Manage a todo.md file with task decomposition and step tracking.

## Guidance
Only provide parameters relevant to the specific operation you are performing; do not include unnecessary parameters. The todo.md file is maintained in the base directory and follows a structured format for task management.

Available `action` values:
1. add: Add a new step to the todo list at the end or after a specific step (task, priority, category, parameters, after_step_id).
2. complete: Mark a step as completed (step_id, status "success"/"failed", result).
3. update: Update step information (step_id, task, parameters).
4. list: List all steps with their status.
5. clear: Clear completed steps.
6. show: Show the complete todo.md file content.
7. export: Export todo.md to a specified path (export_path).
8. cleanup: Clean up and remove the todo from cache (call when done with the todo list).

## Parameters
- action (str): One of add, complete, update, list, clear, show, export, cleanup.
- task (str, optional): Step description (add/update).
- priority (str, optional): Step priority (add).
- category (str, optional): Step category (add).
- parameters (dict, optional): Extra step parameters (add/update).
- after_step_id (str, optional): Step ID to insert after (add).
- step_id (str, optional): Target step ID (complete/update).
- status (str, optional): Completion status "success" or "failed" (complete).
- result (str, optional): Result description (complete).
- export_path (str, optional): Target path for export.

## Example
{"name": "todo_tool", "args": {"action": "add", "task": "Task description", "priority": "high", "category": "work"}}
{"name": "todo_tool", "args": {"action": "complete", "step_id": "step_1", "status": "success", "result": "Completed successfully"}}
"""


@TOOL.register_module(force=True)
class TodoTool(Tool):
    """A coroutine-safe tool for managing todo.md files with task decomposition and step tracking."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    name: str = "todo_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")
    
    # Configuration parameters.  When unset, todo files live under the
    # configured workspace root (``config.workspace_root``), which the gateway
    # binds per-session under ``output/``.  A ``None`` default avoids anchoring
    # to a literal ``workspace_root/`` folder in the process cwd.
    base_dir: Optional[str] = Field(
        default=None,
        description="The base directory for saving todo files. Defaults to <workspace_root>/todo_tool."
    )
    
    def __init__(
        self, 
        base_dir: Optional[str] = None, 
        enable_evolving: bool = False,
        **kwargs
    ):
        """Initialize the todo tool."""
        super().__init__(enable_evolving=enable_evolving, **kwargs)
        
        if base_dir is not None:
            self.base_dir = assemble_workspace_path(base_dir)
        else:
            # Anchor to the configured workspace root (bound per-session by the
            # gateway under output/), never to the process cwd.
            self.base_dir = os.path.join(config.workspace_root, "todo_tool")

        if self.base_dir is not None:
            os.makedirs(self.base_dir, exist_ok=True)
        
        # Per-id cache and locks for concurrent safety
        # Key: id (str), Value: Todo instance
        self._todo_cache: Dict[str, Todo] = {}
        # Key: id (str), Value: asyncio.Lock for that todo
        self._todo_locks: Dict[str, asyncio.Lock] = {}
        # Lock for managing the cache dictionaries themselves
        self._cache_lock = asyncio.Lock()
    
    def _file_path(self, id: str, name: str) -> str:
        """Per-id file path under base_dir, e.g. `<safe_id>_todo.md` / `<safe_id>_steps.json`."""
        safe_id = re.sub(r'[^\w\s-]', '', id).strip().replace(' ', '_') or "todo"
        return os.path.join(self.base_dir, f"{safe_id}_{name}")

    async def content(self, id: str) -> str:
        """Current todo.md content for `id`, read directly — no Todo instance is created.

        Injects the running todo into an agent's prompt each step (like memory), so the
        agent always sees its plan without spending a `show` action.
        """
        return Todo.read_content(self._file_path(id, "todo.md"))

    async def _get_or_create_todo(self, id: str) -> tuple[Todo, asyncio.Lock]:
        """Get or create a Todo instance for the given id with proper locking.
        
        Args:
            id: The unique identifier for the call
            
        Returns:
            tuple[Todo, asyncio.Lock]: The todo instance and its lock
        """
        async with self._cache_lock:
            # Get or create lock for this id
            if id not in self._todo_locks:
                self._todo_locks[id] = asyncio.Lock()
            
            # Get or create todo for this id
            if id not in self._todo_cache:
                todo_file = self._file_path(id, "todo.md")
                steps_file = self._file_path(id, "steps.json")
                
                # Load existing steps if file exists
                steps = []
                if os.path.exists(steps_file):
                    try:
                        with open(steps_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            steps = [Step(**step_data) for step_data in data]
                    except Exception:
                        steps = []
                
                self._todo_cache[id] = Todo(
                    id=id,
                    todo_file=todo_file,
                    steps_file=steps_file,
                    steps=steps
                )
                logger.info(f"| 📝 Created new todo cache for id: {id} (file_path: {todo_file})")
            else:
                logger.info(f"| 📂 Using existing todo cache for id: {id} (steps: {len(self._todo_cache[id].steps)})")
            
            return self._todo_cache[id], self._todo_locks[id]
    
    async def _cleanup_todo(self, id: str):
        """Remove todo from cache after completion."""
        async with self._cache_lock:
            if id in self._todo_cache:
                del self._todo_cache[id]
                logger.info(f"| 🧹 Removed todo from cache: {id}")
            if id in self._todo_locks:
                del self._todo_locks[id]

    async def __call__(
        self, 
        action: str,
        task: Optional[str] = None, 
        step_id: Optional[str] = None,
        status: Optional[str] = None,
        result: Optional[str] = None,
        priority: Optional[str] = "medium",
        category: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        after_step_id: Optional[str] = None,
        export_path: Optional[str] = None,
        **kwargs
    ) -> Response:
        """Execute a todo action asynchronously with coroutine safety.

        Args:
            action (str): One of add, complete, update, list, clear, show, export, cleanup.
            task (Optional[str]): Step description for add/update.
            step_id (Optional[str]): Step identifier for complete/update actions.
            status (Optional[str]): Completion status for complete action.
            result (Optional[str]): Result summary for complete action.
            priority (Optional[str]): Priority for add action.
            category (Optional[str]): Category label for add action.
            parameters (Optional[Dict[str, Any]): Arbitrary metadata for steps.
            after_step_id (Optional[str]): Insert new step after the specified ID.
            export_path (Optional[str]): Target path for export action.
        """
        try:
            # Get tool context
            ctx = kwargs.get("ctx")
            id = ctx.id
            
            # Handle cleanup action
            if action == "cleanup":
                await self._cleanup_todo(id)
                return Response(type=ResponseType.TOOL, 
                    success=True,
                    message=f"✅ Cleaned up todo cache for id: {id}"
                )
            
            # Get or create todo instance and its lock
            todo, todo_lock = await self._get_or_create_todo(id)
            
            # Use the lock to ensure coroutine-safe access to this specific todo
            async with todo_lock:
                logger.info(f"| 📝 TodoTool action: {action} (id: {id}, todo_file: {todo.todo_file}, steps: {len(todo.steps)})")
                
                if action == "add":
                    return await self._handle_add(todo, task, priority, category, parameters, after_step_id, step_id)
                if action == "complete":
                    return await self._handle_complete(todo, step_id, status, result)
                if action == "update":
                    return await self._handle_update(todo, step_id, task, parameters)
                if action == "list":
                    return self._handle_list(todo)
                if action == "clear":
                    return await self._handle_clear(todo)
                if action == "show":
                    return self._handle_show(todo)
                if action == "export":
                    return await self._handle_export(todo, export_path)
                
                return Response(type=ResponseType.TOOL, 
                    success=False,
                    message=(
                        f"Unknown action: {action}. "
                        "Available actions: add, complete, update, list, clear, show, export, cleanup"
                    ),
                )
                
        except Exception as e:
            logger.error(f"| ❌ Error in TodoTool: {e}")
            import traceback
            return Response(type=ResponseType.TOOL, 
                success=False, 
                message=f"Error executing todo action '{action}': {str(e)}\n{traceback.format_exc()}"
            )

    async def _handle_add(
        self,
        todo: Todo,
        task: str,
        priority: str,
        category: Optional[str],
        parameters: Optional[Dict[str, Any]],
        after_step_id: Optional[str],
        step_id: Optional[str]
    ) -> Response:
        """Handle add action."""
        if not task:
            return Response(type=ResponseType.TOOL, success=False, message="Error: Step description is required for add action")
        
        try:
            new_step = await todo.add_step(
                task=task,
                priority=priority,
                category=category,
                parameters=parameters,
                after_step_id=after_step_id,
                step_id=step_id
            )
            
            message = f"✅ Added step {new_step.id}: {task} (priority: {priority})"
            if after_step_id:
                message = f"✅ Added step {new_step.id} after {after_step_id}: {task} (priority: {priority})"
            
            logger.info(f"| {message}")
            return Response(type=ResponseType.TOOL, 
                success=True,
                message=message,
                files=[todo.todo_file],
                data={
                    "step_id": new_step.id,
                    "after_step_id": after_step_id,
                    "task": task,
                    "priority": priority,
                    "category": category,
                    "parameters": parameters
                }
            )
        except ValueError as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error: {str(e)}")

    async def _handle_complete(
        self,
        todo: Todo,
        step_id: str,
        status: str,
        result: Optional[str]
    ) -> Response:
        """Handle complete action."""
        if not step_id:
            return Response(type=ResponseType.TOOL, success=False, message="Error: Step ID is required for complete action")
        
        if not status:
            return Response(type=ResponseType.TOOL, success=False, message="Error: Status is required for complete action")
        
        try:
            step = await todo.complete_step(step_id=step_id, status=status, result=result)
            
            return Response(type=ResponseType.TOOL, 
                success=True,
                message=f"✅ Completed step {step_id} with status: {status}",
                files=[todo.todo_file],
                data={
                    "step_id": step_id,
                    "status": status,
                    "result": result,
                    "updated_at": step.updated_at,
                    "step_name": step.name
                }
            )
        except ValueError as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error: {str(e)}")

    async def _handle_update(
        self,
        todo: Todo,
        step_id: str,
        task: Optional[str],
        parameters: Optional[Dict[str, Any]]
    ) -> Response:
        """Handle update action."""
        if not step_id:
            return Response(type=ResponseType.TOOL, success=False, message="Error: Step ID is required for update action")
        
        try:
            step = await todo.update_step(step_id=step_id, task=task, parameters=parameters)
            
            return Response(type=ResponseType.TOOL, 
                success=True,
                message=f"✅ Updated step {step_id}",
                files=[todo.todo_file],
                data={
                    "step_id": step_id,
                    "updated_fields": {
                        "task": task if task else None,
                        "parameters": parameters if parameters is not None else None
                    },
                    "updated_at": step.updated_at,
                    "step_name": step.name
                }
            )
        except ValueError as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error: {str(e)}")

    def _handle_list(self, todo: Todo) -> Response:
        """Handle list action."""
        if not todo.steps:
            return Response(type=ResponseType.TOOL, success=False, message="No steps found. Use 'add' action to create your first step.")
        
        result = "📋 Todo Steps:\n\n"
        for step in todo.steps:
            status_emoji = {
                "pending": "⏳",
                "success": "✅",
                "failed": "❌"
            }.get(step.status, "⏳")
            
            priority_emoji = {
                "high": "🔴", 
                "medium": "🟡", 
                "low": "🟢"
            }.get(step.priority, "🟡")
            
            category_text = f" [{step.category}]" if step.category else ""
            result += f"**{step.id}** {priority_emoji} {status_emoji} {step.name}{category_text}\n"
            
            if step.parameters:
                result += f"  Parameters: {json.dumps(step.parameters)}\n"
            
            if step.result:
                result += f"  Result: {step.result}\n"
            
            result += f"  Created: {step.created_at}"
            if step.updated_at:
                result += f", Updated: {step.updated_at}"
            result += "\n\n"
        
        return Response(type=ResponseType.TOOL, 
            success=True,
            message=result,
            files=[todo.todo_file],
            data={
                "total_steps": len(todo.steps),
                "steps": [step.model_dump() for step in todo.steps],
                "pending_count": len([s for s in todo.steps if s.status == "pending"]),
                "completed_count": len([s for s in todo.steps if s.status in ["success", "failed"]])
            }
        )

    async def _handle_clear(self, todo: Todo) -> Response:
        """Handle clear action."""
        completed_steps = await todo.clear_completed()
        
        if not completed_steps:
            return Response(type=ResponseType.TOOL, success=False, message="No completed steps to remove")
        
        return Response(type=ResponseType.TOOL, 
            success=True,
            message=f"✅ Removed {len(completed_steps)} completed step(s)",
            files=[todo.todo_file],
            data={
                "removed_count": len(completed_steps),
                "removed_steps": [step.model_dump() for step in completed_steps],
                "remaining_steps": len(todo.steps)
            }
        )

    def _handle_show(self, todo: Todo) -> Response:
        """Handle show action."""
        content = todo.get_content()
        
        if content.startswith("[Current todo.md is empty"):
            return Response(type=ResponseType.TOOL, success=False, message="No todo file found. Use 'add' action to create your first step.")
        
        return Response(type=ResponseType.TOOL, 
            success=True,
            message=f"📄 Todo.md content:\n\n```markdown\n{content}\n```",
            files=[todo.todo_file],
            data={
                "content": content,
                "file_size": len(content),
                "total_steps": len(todo.steps)
            }
        )

    async def _handle_export(self, todo: Todo, export_path: str) -> Response:
        """Handle export action."""
        if not export_path:
            return Response(type=ResponseType.TOOL, success=False, message="Error: Export path is required for export action")
        
        try:
            # Ensure the todo.md file is up to date
            await todo._sync_to_markdown()
            
            content = todo.get_content()
            if content.startswith("[Current todo.md is empty"):
                return Response(type=ResponseType.TOOL, success=False, message="No todo file found. Use 'add' action to create your first step.")
            
            # Create parent directories if they don't exist
            export_dir = os.path.dirname(export_path)
            if export_dir:
                os.makedirs(export_dir, exist_ok=True)
            
            # Write to the export path
            with open(export_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return Response(type=ResponseType.TOOL, 
                success=True,
                message=f"✅ Successfully exported todo.md to: {export_path}",
                files=[todo.todo_file, export_path],
                data={
                    "source_file": todo.todo_file,
                    "export_path": export_path,
                    "file_size": len(content),
                    "total_steps": len(todo.steps)
                }
            )
            
        except Exception as e:
            return Response(type=ResponseType.TOOL, success=False, message=f"Error exporting todo.md: {str(e)}")
