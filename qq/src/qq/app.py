"""Main application orchestration."""

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
    from qq.client import create_client
    from qq.history import History
    from qq.agents import load_agent
    from qq.skills import load_all_skills, find_relevant_skills, inject_skills, create_example_skill
    from qq.mcp_loader import load_mcp_tools
    
    # Parse arguments
    args = parse_args()
    
    # Initialize console
    console = qqConsole(no_color=args.no_color)
    
    try:
        # Load agent
        agent = load_agent(args.agent)
        if args.verbose:
            console.print_info(f"Loaded agent: {agent.name}")
    except FileNotFoundError as e:
        console.print_error(str(e))
        sys.exit(1)
    
    # Initialize history
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
    # client = create_client()
    
    # Preload embeddings in background thread
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
    # from qq.agents.notes.notes import NotesAgent
    # from qq.services.graph import KnowledgeGraphAgent
    # from qq.context import ContextRetrievalAgent
    
    # notes_agent = NotesAgent(llm_client=client, embeddings=shared_embeddings)
    # knowledge_agent = KnowledgeGraphAgent(llm_client=client, embeddings=shared_embeddings)
    # context_agent = ContextRetrievalAgent(
    #     notes_agent=notes_agent,
    #     knowledge_agent=knowledge_agent,
    #     embeddings=shared_embeddings,
    # )
    
    if args.verbose:
        console.print_info("Agent initialized (Memory agents pending migration)")
    
    # Run in appropriate mode
    if args.mode == "cli":
        run_cli_mode(
            agent=agent,
            history=history,
            console=console,
            message=args.message or "",
        )
    else:
        run_console_mode(
            agent=agent,
            history=history,
            console=console,
        )


def run_cli_mode(
    agent,
    history,
    console,
    message: str,
) -> None:
    """Run in CLI mode - single message and response."""
    
    if not message:
        console.print_error("No message provided. Use -m 'your message'")
        sys.exit(1)
    
    # Note: Skills and Context injection disabled for Phase 1
    
    # Strands Agent execution
    try:
        # We pass the message directly. 
        # TODO: Handle history if Strands Agent doesn't automatically load persistence
        response = agent(message)
        
        # Save to history
        history.add("user", message)
        history.add("assistant", str(response))
        
        # Output response
        console.print_assistant_message(str(response))
        
    except Exception as e:
        console.print_error(f"Error executing agent: {e}")


def run_console_mode(
    agent,
    history,
    console,
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
            
            # Strands Agent execution
            # Streaming support to be verified. agent() might return full response.
            response = agent(user_input)
            
            # Save to history
            history.add("user", user_input)
            history.add("assistant", str(response))
            
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
