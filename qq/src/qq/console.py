"""Rich console UI for colored output."""

from typing import Iterator, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.theme import Theme


# Custom theme for qq
qq_THEME = Theme({
    "user": "bold cyan",
    "assistant": "green",
    "system": "dim white",
    "tool": "yellow",
    "error": "bold red",
    "info": "blue",
})


class qqConsole:
    """Rich console interface for qq."""
    
    def __init__(self, no_color: bool = False):
        self.console = Console(
            theme=qq_THEME,
            force_terminal=not no_color,
            no_color=no_color,
        )
        self.no_color = no_color
    
    def print_welcome(self, agent_name: str, history_count: int) -> None:
        """Print welcome message."""
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]qq[/bold] - Conversational AI\n"
                f"Agent: [info]{agent_name}[/info] | "
                f"History: [info]{history_count}[/info] messages",
                border_style="blue",
            )
        )
        self.console.print("[dim]Type 'exit' or 'quit' to leave, 'clear' to reset history[/dim]")
        self.console.print()
    
    def get_input(self) -> str:
        """Get user input with styled prompt."""
        try:
            return Prompt.ask("[user]You[/user]")
        except (EOFError, KeyboardInterrupt):
            return "exit"
    
    def print_user_message(self, message: str) -> None:
        """Print user message (for CLI mode display)."""
        self.console.print(f"[user]You:[/user] {message}")
    
    def print_assistant_start(self) -> None:
        """Print assistant label before streaming."""
        self.console.print("[assistant]Assistant:[/assistant] ", end="")
    
    def print_stream_chunk(self, chunk: str) -> None:
        """Print a streaming chunk."""
        self.console.print(chunk, end="", highlight=False)
    
    def print_stream_end(self) -> None:
        """End streaming output."""
        self.console.print()
        self.console.print()
    
    def print_assistant_message(self, message: str) -> None:
        """Print complete assistant message with markdown rendering."""
        self.console.print("[assistant]Assistant:[/assistant]")
        if self.no_color:
            self.console.print(message)
        else:
            self.console.print(Markdown(message))
        self.console.print()
    
    def print_tool_call(self, name: str, args: dict) -> None:
        """Print tool call info."""
        import json
        args_str = json.dumps(args, indent=2) if args else "{}"
        self.console.print(f"[tool]🔧 Tool:[/tool] {name}")
        self.console.print(f"[dim]{args_str}[/dim]")
    
    def print_tool_result(self, result: str) -> None:
        """Print tool result."""
        # Truncate long results
        if len(result) > 500:
            result = result[:500] + "..."
        self.console.print(f"[tool]→[/tool] [dim]{result}[/dim]")
        self.console.print()
    
    def print_error(self, message: str) -> None:
        """Print error message."""
        self.console.print(f"[error]Error:[/error] {message}")
    
    def print_info(self, message: str) -> None:
        """Print info message."""
        self.console.print(f"[info]{message}[/info]")
    
    def print_system(self, message: str) -> None:
        """Print system message."""
        self.console.print(f"[system]{message}[/system]")
    
    def print_goodbye(self) -> None:
        """Print goodbye message."""
        self.console.print()
        self.console.print("[dim]Goodbye! 👋[/dim]")


def stream_to_console(
    console: qqConsole,
    stream: Iterator[str],
) -> str:
    """Stream response to console and return full text."""
    console.print_assistant_start()
    
    full_response = []
    try:
        for chunk in stream:
            console.print_stream_chunk(chunk)
            full_response.append(chunk)
    except KeyboardInterrupt:
        console.print_stream_end()
        console.print_info("[Interrupted]")
        return "".join(full_response)
    
    console.print_stream_end()
    return "".join(full_response)

