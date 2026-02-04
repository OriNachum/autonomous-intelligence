"""Main application orchestration.

Updated for parallel execution support:
- Session initialization from CLI args
- FileManager instance methods (no module globals)
- Embeddings preload is still daemon thread but safe (per-instance)
"""

import sys
from pathlib import Path

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
        agent, file_manager = load_agent(args.agent)
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

    # Memory agents initialization commented out for Phase 1
    # Will be migrated to Tools in Phase 3

    # Initialize memory agents
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

    if args.verbose:
        console.print_info("Agent initialized (Memory agents pending migration)")

    # Run in appropriate mode
    if args.mode == "cli":
        run_cli_mode(
            agent=agent,
            file_manager=file_manager,
            history=history,
            console=console,
            message=args.message or "",
            context_agent=context_agent,
            notes_agent=notes_agent,
            knowledge_agent=knowledge_agent,
        )
    else:
        run_console_mode(
            agent=agent,
            file_manager=file_manager,
            history=history,
            console=console,
            context_agent=context_agent,
            notes_agent=notes_agent,
            knowledge_agent=knowledge_agent,
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


def run_cli_mode(
    agent,
    file_manager,
    history,
    console,
    message: str,
    context_agent=None,
    notes_agent=None,
    knowledge_agent=None,
) -> None:
    """Run in CLI mode - single message and response."""

    if not message:
        console.print_error("No message provided. Use -m 'your message'")
        sys.exit(1)

    # Note: Skills and Context injection disabled for Phase 1


    # Strands Agent execution
    try:
        # Prepare context
        formatted_message = message
        if context_agent:
            # We inject context by prepending it to the message essentially
            # Or by modifying system prompt. Strands Agent might not allow easy dynamic system prompt modification per call
            # So standard way: Prepend context to user message
            context_data = context_agent.prepare_context(message)
            if context_data.get("context_text"):
                formatted_message = f"{context_data['context_text']}\n\n{message}"

        # Strands Agent execution
        response = agent(formatted_message)

        # Save to history match real user message
        history.add("user", message)

        # Capture file reads to history (before assistant response)
        _capture_file_reads_to_history(file_manager, history)

        history.add("assistant", str(response))

        # Update memory in background (or sync for CLI)
        messages = history.get_messages()
        if notes_agent:
             notes_agent.process_messages(messages)
        if knowledge_agent:
             knowledge_agent.process_messages(messages)

        # Output response
        console.print_assistant_message(str(response))

    except Exception as e:
        console.print_error(f"Error executing agent: {e}")


def run_console_mode(
    agent,
    file_manager,
    history,
    console,
    context_agent=None,
    notes_agent=None,
    knowledge_agent=None,
) -> None:
    """Run in console mode - interactive REPL."""

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

            # Memory command disabled for now
            # if user_input.lower() == "memory": ...

            if not user_input.strip():
                continue

            # Note: Skills and Context injection disabled for Phase 1

            # Prepare context
            formatted_input = user_input
            if context_agent:
                context_data = context_agent.prepare_context(user_input)
                if context_data.get("context_text"):
                     # Debug print
                     # console.print_info("Context injected")
                     formatted_input = f"{context_data['context_text']}\n\n{user_input}"

            # Strands Agent execution
            # Streaming support to be verified. agent() might return full response.
            response = agent(formatted_input)

            # Save to history
            history.add("user", user_input)

            # Capture file reads to history (before assistant response)
            _capture_file_reads_to_history(file_manager, history)

            history.add("assistant", str(response))

            # Update memory
            messages = history.get_messages()
            if notes_agent:
                 # TODO: Thread this?
                 notes_agent.process_messages(messages)
            if knowledge_agent:
                 knowledge_agent.process_messages(messages)

            # Output Result (Streaming handled by Agent callbacks if configured,
            # otherwise we print the result)
            console.print_assistant_message(str(response))

        except KeyboardInterrupt:
            console.print_goodbye()
            break
        except Exception as e:
            console.print_error(str(e))



if __name__ == "__main__":
    main()
