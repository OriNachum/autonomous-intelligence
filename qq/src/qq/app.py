"""Main application orchestration.

Updated for parallel execution support:
- Session initialization from CLI args
- FileManager instance methods (no module globals)
- Embeddings preload is still daemon thread but safe (per-instance)
- Token limit recovery with progressive context reduction
- Source citation registry and alignment review
"""

import os
import sys
from pathlib import Path

from qq.recovery import execute_with_recovery
from qq.errors import is_token_error

from dotenv import load_dotenv


def main() -> None:
    """Main entry point for qq."""
    # Load environment variables from .env file
    # Try multiple locations
    for env_path in [
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]:
        if env_path.exists():
            load_dotenv(env_path)
            break

    from qq.cli import parse_args
    from qq.console import qqConsole, stream_to_console
    from qq.history import History
    from qq.agents import load_agent
    from qq.skills import load_all_skills, find_relevant_skills, inject_skills, create_example_skill
    from qq.mcp_loader import load_mcp_tools
    from qq.session import set_session_id, get_session_id

    # Parse arguments
    args = parse_args()

    # Initialize session based on CLI args
    if args.session:
        # Resume existing session
        set_session_id(args.session)
    elif args.new_session:
        # Force new session (get_session_id will generate one)
        pass
    # Otherwise, get_session_id() will auto-generate on first call

    # Initialize console
    console = qqConsole(no_color=args.no_color)

    try:
        # Load agent (now returns tuple of Agent, FileManager)
        agent, file_manager = load_agent(args.agent, cwd=args.cwd)
        if args.verbose:
            console.print_info(f"Loaded agent: {agent.name}")
            console.print_info(f"Session: {get_session_id()}")
    except FileNotFoundError as e:
        console.print_error(str(e))
        sys.exit(1)

    # Initialize history (now session-isolated)
    history = History(agent_name=agent.name)

    if args.clear_history:
        history.clear()
        console.print_info("History cleared")

    # Load MCP tools
    mcp_tools, tool_executor = load_mcp_tools()
    if args.verbose and mcp_tools:
        console.print_info(f"Loaded {len(mcp_tools)} MCP tools")

    # Load skills
    skills = load_all_skills()
    if not skills:
        # Create example skill on first run
        create_example_skill()
        skills = load_all_skills()
    if args.verbose and skills:
        console.print_info(f"Loaded {len(skills)} skills")


    # Create vLLM client - Removed in favor of strands Agent internal model
    # client = create_client() - DEPRECATED

    # Preload embeddings in background thread
    # Note: EmbeddingClient is per-instance, so this is safe for parallel execution
    import threading
    from qq.embeddings import EmbeddingClient

    shared_embeddings = EmbeddingClient()

    def preload_embeddings():
        """Load embeddings model in background."""
        try:
            # Trigger initialization
            if shared_embeddings.is_available:
                if args.verbose:
                    console.print_info(f"Embeddings backend: {shared_embeddings.backend_name}")
        except Exception as e:
            if args.verbose:
                console.print_info(f"Embeddings not available: {e}")

    embeddings_thread = threading.Thread(target=preload_embeddings, daemon=True)
    embeddings_thread.start()

    # Initialize memory agents (read path only — write path removed)
    from qq.agents.notes.notes import NotesAgent
    from qq.services.graph import KnowledgeGraphAgent
    from qq.context.retrieval_agent import ContextRetrievalAgent

    notes_agent = NotesAgent(model=agent.model, embeddings=shared_embeddings)
    knowledge_agent = KnowledgeGraphAgent(model=agent.model, embeddings=shared_embeddings)
    context_agent = ContextRetrievalAgent(
        notes_agent=notes_agent,
        knowledge_agent=knowledge_agent,
        embeddings=shared_embeddings,
    )

    # Initialize alignment agent (silent post-answer reviewer)
    from qq.services.alignment import AlignmentAgent
    alignment_enabled = os.getenv("QQ_ALIGNMENT_ENABLED", "true").lower() not in ("false", "0", "no")
    alignment_agent = AlignmentAgent(model=agent.model) if alignment_enabled else None

    if args.verbose:
        console.print_info("Agent initialized")

    # Check for daily backup (before first interaction)
    from qq.backup.manager import BackupManager

    backup_manager = BackupManager()
    if backup_manager.should_backup_today():
        if args.verbose:
            console.print_info("Creating daily memory backup...")
        try:
            backup_path = backup_manager.create_backup(trigger="daily")
            if args.verbose:
                console.print_info(f"Backup created: {backup_path}")
        except Exception as e:
            if args.verbose:
                console.print_info(f"Backup skipped: {e}")

    # Run in appropriate mode
    if args.mode == "cli":
        run_cli_mode(
            agent=agent,
            file_manager=file_manager,
            history=history,
            console=console,
            message=args.message or "",
            context_agent=context_agent,
            alignment_agent=alignment_agent,
        )
    else:
        run_console_mode(
            agent=agent,
            file_manager=file_manager,
            history=history,
            console=console,
            context_agent=context_agent,
            alignment_agent=alignment_agent,
        )


def _format_file_quote(file_read: dict) -> str:
    """Format a file read as a quoted history entry."""
    name = file_read["name"]
    content = file_read["content"]
    start = file_read["start_line"]
    end = file_read["end_line"]
    total = file_read["total_lines"]

    return f"""[Quote from file: {name} (lines {start}-{end} of {total})]
---
{content}
---
[End of quote from {name}]"""


def _capture_file_reads_to_history(file_manager, history) -> None:
    """Capture any pending file reads and add them to history.

    Now uses FileManager instance methods instead of module globals.
    """
    file_reads = file_manager.get_pending_file_reads()
    for file_read in file_reads:
        formatted = _format_file_quote(file_read)
        history.add("file_content", formatted)

    file_manager.clear_pending_file_reads()


def _run_alignment_review(alignment_agent, response_text, source_registry, context_text, console):
    """Run silent alignment review if sources were used.

    Args:
        alignment_agent: AlignmentAgent instance (or None)
        response_text: The agent's response string
        source_registry: SourceRegistry for this turn
        context_text: Context text that was injected
        console: Console for warning output

    Returns:
        Possibly corrected response text
    """
    if not alignment_agent or not source_registry or not source_registry.has_sources:
        return response_text

    try:
        review = alignment_agent.review(
            answer=response_text,
            sources=source_registry.sources,
            context_text=context_text,
        )
        if not review.get("pass", True):
            corrections = review.get("corrections")
            if corrections:
                return corrections
            # No full correction — warn about individual issues
            for issue in review.get("issues", []):
                claim = issue.get("claim", "")[:80]
                console.print_warning(
                    f"[Alignment: {issue.get('type', 'issue')}] {claim}"
                )
    except Exception:
        pass  # Alignment failure is non-fatal

    return response_text


def run_cli_mode(
    agent,
    file_manager,
    history,
    console,
    message: str,
    context_agent=None,
    alignment_agent=None,
) -> None:
    """Run in CLI mode - single message and response."""

    if not message:
        console.print_error("No message provided. Use -m 'your message'")
        sys.exit(1)

    from qq.services.source_registry import SourceRegistry

    # Strands Agent execution with token recovery
    try:
        # Create source registry for this turn
        source_registry = SourceRegistry()
        file_manager.source_registry = source_registry

        # Prepare context with source indexing
        formatted_message = message
        context_text = ""
        if context_agent:
            context_data = context_agent.prepare_context(
                message, source_registry=source_registry
            )
            context_text = context_data.get("context_text", "")
            if context_text:
                formatted_message = f"{context_text}\n\n{message}"

        # Execute with automatic token limit recovery
        def on_retry(attempt, strategy):
            console.print_warning(f"[Token limit: retrying with {strategy}]")

        result = execute_with_recovery(
            agent_fn=lambda msg: agent(msg),
            message=formatted_message,
            history=history,
            max_retries=4,
            on_retry=on_retry,
        )

        if not result.success:
            if result.overflow_severity == 'catastrophic':
                console.print_error(
                    "[Tool output too large]\n"
                    "A tool returned more data than the model can process.\n"
                    "Tip: Use count_files() before list_files() on large directories."
                )
                return
            if result.warnings:
                for warn in result.warnings:
                    console.print_warning(warn)
            raise result.error or Exception("Token recovery failed")

        response = result.response

        # Log recovery if it happened
        if result.attempts > 1:
            console.print_warning(
                f"[Recovered: {result.strategy}, {result.attempts} attempts]"
            )

        response_text = str(response)

        # Run alignment review (silent unless issues found)
        response_text = _run_alignment_review(
            alignment_agent, response_text, source_registry, context_text, console
        )

        # Append source citation footer
        source_footer = source_registry.format_footer()
        if source_footer:
            response_text += source_footer

        # Save to history
        history.add("user", message)
        _capture_file_reads_to_history(file_manager, history)
        history.add("assistant", response_text)

        # Output response
        console.print_assistant_message(response_text)

        # Clean up for next turn
        source_registry.clear()
        file_manager.source_registry = None

    except Exception as e:
        console.print_error(f"Error executing agent: {e}")


def run_console_mode(
    agent,
    file_manager,
    history,
    console,
    context_agent=None,
    alignment_agent=None,
) -> None:
    """Run in console mode - interactive REPL."""

    from qq.services.source_registry import SourceRegistry

    console.print_welcome(agent.name, history.windowed_count)

    while True:
        try:
            # Get user input
            user_input = console.get_input()

            # Handle special commands
            if user_input.lower() in ("exit", "quit", "q"):
                console.print_goodbye()
                break

            if user_input.lower() == "clear":
                history.clear()
                console.print_info("History cleared")
                continue

            if user_input.lower() == "history":
                console.print_info(f"History: {history.count} total, {history.windowed_count} in window")
                continue

            if user_input.lower() == "backup":
                from qq.backup.manager import BackupManager
                try:
                    manager = BackupManager()
                    backup_path = manager.create_backup(trigger="manual")
                    console.print_info(f"Backup created: {backup_path}")
                except Exception as e:
                    console.print_error(f"Backup failed: {e}")
                continue

            if not user_input.strip():
                continue

            # Create source registry for this turn
            source_registry = SourceRegistry()
            file_manager.source_registry = source_registry

            # Prepare context with source indexing
            formatted_input = user_input
            context_text = ""
            if context_agent:
                context_data = context_agent.prepare_context(
                    user_input, source_registry=source_registry
                )
                context_text = context_data.get("context_text", "")
                if context_text:
                    formatted_input = f"{context_text}\n\n{user_input}"

            # Execute with automatic token limit recovery
            def on_retry(attempt, strategy):
                console.print_warning(f"[Token limit: retrying with {strategy}]")

            result = execute_with_recovery(
                agent_fn=lambda msg: agent(msg),
                message=formatted_input,
                history=history,
                max_retries=4,
                on_retry=on_retry,
            )

            if not result.success:
                if result.overflow_severity == 'catastrophic':
                    # Tool output too large - clear and inform user
                    console.print_error(
                        "[Tool output too large]\n"
                        "A tool returned more data than the model can process.\n"
                        "Session context cleared. Try a more specific query.\n"
                        "Tip: Use count_files() before list_files() on large directories."
                    )
                    history.clear()
                    file_manager.clear_pending_file_reads()
                    source_registry.clear()
                    file_manager.source_registry = None
                    continue
                elif is_token_error(result.error):
                    # Last resort: clear history and retry once
                    console.print_warning("[Clearing history for fresh start]")
                    history.clear()
                    try:
                        response = agent(user_input)  # No context
                    except Exception as final_err:
                        console.print_error(f"Unrecoverable: {final_err}")
                        source_registry.clear()
                        file_manager.source_registry = None
                        continue
                else:
                    raise result.error or Exception("Agent execution failed")
            else:
                response = result.response

            # Log recovery if it happened
            if result.attempts > 1:
                console.print_warning(
                    f"[Recovered: {result.strategy}, {result.attempts} attempts]"
                )

            response_text = str(response)

            # Run alignment review (silent unless issues found)
            response_text = _run_alignment_review(
                alignment_agent, response_text, source_registry, context_text, console
            )

            # Append source citation footer
            source_footer = source_registry.format_footer()
            if source_footer:
                response_text += source_footer

            # Save to history
            history.add("user", user_input)
            _capture_file_reads_to_history(file_manager, history)
            history.add("assistant", response_text)

            # Output response
            console.print_assistant_message(response_text)

            # Clean up for next turn
            source_registry.clear()
            file_manager.source_registry = None

        except KeyboardInterrupt:
            console.print_goodbye()
            break
        except Exception as e:
            console.print_error(str(e))



if __name__ == "__main__":
    main()
