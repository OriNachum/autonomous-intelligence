"""CLI argument parsing."""

import argparse
from dataclasses import dataclass
from typing import Optional


@dataclass
class CLIArgs:
    """Parsed CLI arguments."""
    agent: str
    mode: str  # "cli" or "console"
    message: Optional[str]
    clear_history: bool
    no_color: bool
    verbose: bool


def parse_args() -> CLIArgs:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="qq",
        description="qq - CLI/Console conversational AI with vLLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  qq                          # Start console mode with default agent
  qq --agent coder            # Use the 'coder' agent
  qq -m "Explain Python GIL"  # CLI mode with a message
  qq --clear-history          # Clear conversation history
        """,
    )
    
    parser.add_argument(
        "-a", "--agent",
        default="default",
        help="Agent to use (from agents/ folder). Default: default",
    )
    
    parser.add_argument(
        "--mode",
        choices=["cli", "console"],
        default="console",
        help="Mode: 'cli' for one-shot, 'console' for REPL. Default: console",
    )
    
    parser.add_argument(
        "-m", "--message",
        help="Message to send (implies --mode cli)",
    )
    
    parser.add_argument(
        "--clear-history",
        action="store_true",
        help="Clear conversation history before starting",
    )
    
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    
    args = parser.parse_args()
    
    # If message is provided, force CLI mode
    mode = "cli" if args.message else args.mode
    
    return CLIArgs(
        agent=args.agent,
        mode=mode,
        message=args.message,
        clear_history=args.clear_history,
        no_color=args.no_color,
        verbose=args.verbose,
    )
