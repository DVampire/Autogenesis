import contextvars
import logging
import os
import sys
import threading
from enum import IntEnum
from typing import Any, Optional
from queue import Queue, Empty

from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree
from rich.logging import RichHandler

from autogenesis.utils import Singleton

YELLOW_HEX = "#d4b702"

# Context variable for session_id — set by Bus, read by Logger
_session_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "session_id", default=None
)


def set_session_id(session_id: Optional[str]) -> None:
    """Set the current session_id for log prefixing."""
    _session_id_var.set(session_id)


def get_session_id() -> Optional[str]:
    """Get the current session_id."""
    return _session_id_var.get()

class LogLevel(IntEnum):
    CRITICAL = logging.CRITICAL
    FATAL = logging.FATAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    WARN = logging.WARN
    INFO = logging.INFO
    DEBUG = logging.DEBUG

class Logger(logging.Logger, metaclass=Singleton):
    """
    Async logger with synchronous interface.
    Uses background thread for file I/O to avoid blocking event loop,
    while maintaining API compatibility.
    """
    def __init__(self, name="logger", level=logging.INFO):
        # Initialize the parent class
        super().__init__(name, level)

        # Define a formatter for log messages
        self.formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s:%(levelname)s - %(filename)s:%(lineno)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        
        # Async log writing related
        self._log_queue: Optional[Queue] = None
        self._log_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._log_path: Optional[str] = None
        self._file_handler = None          # Rich handler for the current file sink
        self._level: int = LogLevel.INFO
        self._initialized = False

    def _log_writer_thread(self, log_path: str):
        """Background thread: reads logs from queue and writes to file."""
        with open(log_path, "a", encoding="utf-8") as log_file:
            while not self._stop_event.is_set():
                try:
                    # Get log entry from queue (with timeout to avoid blocking forever)
                    log_entry = self._log_queue.get(timeout=0.1)
                    if log_entry is None:  # Stop signal
                        break
                    
                    # Write to file
                    log_file.write(log_entry)
                    log_file.flush()  # Ensure immediate write
                    self._log_queue.task_done()
                    
                except Empty:
                    continue
                except Exception as e:
                    # If write fails, at least output to stderr
                    import sys
                    print(f"Logger write error: {e}", file=sys.stderr)
    
    def _enqueue_log(self, level: str, msg: str, *args, **kwargs):
        """Enqueue log message to background thread (non-blocking)."""
        if not self._initialized or self._log_queue is None:
            # Fallback to synchronous logging if not initialized
            return
        
        try:
            # Format log message
            record = self.makeRecord(
                self.name, 
                getattr(logging, level.upper()),
                "", 0, msg, args, None
            )
            formatted = self.formatter.format(record)
            
            # Non-blocking enqueue
            try:
                self._log_queue.put_nowait(formatted + "\n")
            except:
                # If queue is full, drop oldest log (avoid blocking)
                try:
                    self._log_queue.get_nowait()
                    self._log_queue.put_nowait(formatted + "\n")
                except:
                    pass  # If still fails, drop this log entry
                    
        except Exception:
            pass  # Logging failure should not affect main program

    def initialize(
        self,
        config,
        level: int = LogLevel.INFO,
        console_stream=None,
        file_logging: bool = True,
    ):
        """
        Initialize the logger with a file path and optional main process check.

        Args:
            config: Config object with log_path attribute.
            level (int, optional): The logging level. Defaults to logging.INFO.
            file_logging: Write to ``config.log_path`` immediately. Long-lived hosts
                (the Gateway) pass ``False`` so no tag-level log file is created
                before a session exists, then call :meth:`rebind` once bound.
        """

        log_path = config.log_path
        self._log_path = log_path
        self._level = level
        self.handlers.clear()

        # Console output (synchronous, but fast)
        self.console = Console(
            width=None,
            markup=True,
            color_system="truecolor",
            force_terminal=True,
            file=console_stream or sys.stdout,
        )
        rich_handler = RichHandler(
            console=self.console,
            rich_tracebacks=True,
            show_time=False,
            show_level=False,
            show_path=False,
            markup=True,
            omit_repeated_times=False
        )
        rich_handler.setLevel(level)
        rich_handler.setFormatter(self.formatter)
        self.addHandler(rich_handler)

        if file_logging:
            self._attach_file_sink(log_path, level)

        self.propagate = False
        self._initialized = True

    def _attach_file_sink(self, log_path: str, level: int) -> None:
        """Start the async writer thread and Rich file handler for ``log_path``."""
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # File output - use queue for async writing
        self._log_queue = Queue(maxsize=1000)  # Limit queue size to avoid memory overflow
        self._stop_event.clear()

        # Start background log writing thread
        self._log_thread = threading.Thread(
            target=self._log_writer_thread,
            args=(log_path,),
            daemon=True,
            name="Logger-Writer"
        )
        self._log_thread.start()

        # File console for Rich objects (still needs file handle for Rich)
        self.file_console = Console(
            width=None,
            markup=True,
            color_system="truecolor",
            force_terminal=True,
            file=open(log_path, "a", encoding="utf-8")
        )
        rich_file_handler = RichHandler(
            console=self.file_console,
            rich_tracebacks=True,
            show_time=False,
            show_level=False,
            show_path=False,
            markup=True,
            omit_repeated_times=False,
        )
        rich_file_handler.setLevel(level)
        rich_file_handler.setFormatter(self.formatter)
        self.addHandler(rich_file_handler)
        self._file_handler = rich_file_handler
        self._log_path = log_path

    def rebind(self, log_path: str) -> None:
        """Redirect file logging to ``log_path`` (called when a session is bound).

        Long-lived hosts initialize the logger before any session exists; binding a
        session moves the log file under that session's own log root. The console
        sink is untouched, so nothing is lost while switching.
        """
        if log_path == self._log_path and getattr(self, "_file_handler", None) is not None:
            return

        # Stop the current writer thread and detach the old file sink.
        self._stop_event.set()
        if self._log_thread is not None:
            self._log_thread.join(timeout=2.0)
            self._log_thread = None
        old_handler = getattr(self, "_file_handler", None)
        if old_handler is not None:
            self.removeHandler(old_handler)
            self._file_handler = None
        old_console = getattr(self, "file_console", None)
        if old_console is not None:
            try:
                old_console.file.close()
            except Exception:
                pass

        self._attach_file_sink(log_path, getattr(self, "_level", LogLevel.INFO))

    def _prefix_msg(self, msg):
        """Add [session_id] prefix if available."""
        sid = _session_id_var.get(None)
        if sid and isinstance(msg, str):
            return f"[{sid}] {msg}"
        return msg

    def info(self, msg, *args, **kwargs):
        """
        Only for string messages, not for rich objects.
        Console output is synchronous (fast), file output is async (non-blocking).
        """
        kwargs.setdefault("stacklevel", 2)

        if "style" in kwargs:
            kwargs.pop("style")
        if "level" in kwargs:
            kwargs.pop("level")

        msg = self._prefix_msg(msg)

        # Console output (synchronous, but fast)
        super().info(msg, *args, **kwargs)

        # File output (async queue, non-blocking)
        self._enqueue_log("info", msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """
        Only for string messages, not for rich objects.
        Console output is synchronous (fast), file output is async (non-blocking).
        """
        kwargs.setdefault("stacklevel", 2)
        msg = self._prefix_msg(msg)
        super().warning(msg, *args, **kwargs)
        self._enqueue_log("warning", msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Console output is synchronous (fast), file output is async (non-blocking)."""
        kwargs.setdefault("stacklevel", 2)
        msg = self._prefix_msg(msg)
        super().error(msg, *args, **kwargs)
        self._enqueue_log("error", msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """Console output is synchronous (fast), file output is async (non-blocking)."""
        kwargs.setdefault("stacklevel", 2)
        msg = self._prefix_msg(msg)
        super().critical(msg, *args, **kwargs)
        self._enqueue_log("critical", msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        """Console output is synchronous (fast), file output is async (non-blocking)."""
        kwargs.setdefault("stacklevel", 2)
        msg = self._prefix_msg(msg)
        super().debug(msg, *args, **kwargs)
        self._enqueue_log("debug", msg, *args, **kwargs)

    def log(self,
            msg: Optional[Any] = None,
            level: LogLevel = LogLevel.INFO,
            **kwargs):
        """
        Log a rich object or a string message to both console and file.
        Rich objects are printed directly (synchronous), strings use async file writing.
        """
        if isinstance(msg, str):
            self.info(msg, **kwargs)
        elif isinstance(msg, (Group, Panel, Rule, Syntax, Table, Tree)):
            # Rich objects are printed directly (synchronous but fast)
            if self.console:
                self.console.print(msg, **kwargs)
            if self.file_console:
                self.file_console.print(msg, **kwargs)
    
    def shutdown(self):
        """Shutdown logger, wait for queued logs to be written."""
        if self._log_thread and self._log_thread.is_alive():
            # Send stop signal
            if self._log_queue:
                self._log_queue.put(None)
            self._stop_event.set()
            self._log_thread.join(timeout=5)  # Wait up to 5 seconds

logger = Logger()
