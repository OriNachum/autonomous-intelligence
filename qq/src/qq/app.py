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
    
    # Create vLLM client
    client = create_client()
    
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
    
    # Initialize memory agents
    # Add agents directory to path for agent module imports
    agents_dir = Path(__file__).parent.parent.parent / "agents"
    if str(agents_dir) not in sys.path:
        sys.path.insert(0, str(agents_dir))
    
    from notes.notes import NotesAgent
    from qq.knowledge import KnowledgeGraphAgent
    from qq.context import ContextRetrievalAgent
    
    notes_agent = NotesAgent(llm_client=client, embeddings=shared_embeddings)
    knowledge_agent = KnowledgeGraphAgent(llm_client=client, embeddings=shared_embeddings)
    context_agent = ContextRetrievalAgent(
        notes_agent=notes_agent,
        knowledge_agent=knowledge_agent,
        embeddings=shared_embeddings,
    )
    
    if args.verbose:
        console.print_info("Memory agents initialized")
    
    # Run in appropriate mode
    if args.mode == "cli":
        run_cli_mode(
            client=client,
            agent=agent,
            history=history,
            skills=skills,
            mcp_tools=mcp_tools,
            tool_executor=tool_executor,
            console=console,
            message=args.message or "",
            notes_agent=notes_agent,
            knowledge_agent=knowledge_agent,
            context_agent=context_agent,
        )
    else:
        run_console_mode(
            client=client,
            agent=agent,
            history=history,
            skills=skills,
            mcp_tools=mcp_tools,
            tool_executor=tool_executor,
            console=console,
            notes_agent=notes_agent,
            knowledge_agent=knowledge_agent,
            context_agent=context_agent,
        )


def run_cli_mode(
    client,
    agent,
    history,
    skills,
    mcp_tools,
    tool_executor,
    console,
    message: str,
    notes_agent=None,
    knowledge_agent=None,
    context_agent=None,
) -> None:
    """Run in CLI mode - single message and response."""
    from qq.skills import find_relevant_skills, inject_skills
    
    if not message:
        console.print_error("No message provided. Use -m 'your message'")
        sys.exit(1)
    
    # Find relevant skills
    relevant_skills = find_relevant_skills(message, skills)
    system_prompt = inject_skills(agent.system_prompt, relevant_skills)
    
    # Inject retrieved context from memory agents
    if context_agent:
        system_prompt = context_agent.inject_context(system_prompt, message)
    
    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history.get_messages())
    messages.append({"role": "user", "content": message})
    
    # Get response
    if mcp_tools:
        response, _ = client.chat_with_tools(
            messages=messages,
            tools=mcp_tools,
            tool_executor=tool_executor,
        )
    else:
        response = client.chat(messages=messages, stream=False)
    
    # Save to history
    history.add("user", message)
    history.add("assistant", response)
    
    # Update memory agents with new conversation
    full_history = history.get_messages()
    if notes_agent:
        try:
            notes_agent.process_messages(full_history)
        except Exception:
            pass  # Silently handle if storage unavailable
    if knowledge_agent:
        try:
            knowledge_agent.process_messages(full_history)
        except Exception:
            pass
    
    # Output response
    console.print_assistant_message(response)


def run_console_mode(
    client,
    agent,
    history,
    skills,
    mcp_tools,
    tool_executor,
    console,
    notes_agent=None,
    knowledge_agent=None,
    context_agent=None,
) -> None:
    """Run in console mode - interactive REPL."""
    from qq.skills import find_relevant_skills, inject_skills
    from qq.console import stream_to_console
    
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
            
            if user_input.lower() == "memory":
                # Show memory summary
                if context_agent:
                    summary = context_agent.get_full_context_summary()
                    console.print_info(summary)
                else:
                    console.print_info("Memory agents not initialized")
                continue
            
            if not user_input.strip():
                continue
            
            # Find relevant skills for this message
            relevant_skills = find_relevant_skills(user_input, skills)
            system_prompt = inject_skills(agent.system_prompt, relevant_skills)
            
            # Inject retrieved context from memory agents
            if context_agent:
                system_prompt = context_agent.inject_context(system_prompt, user_input)
            
            # Build messages
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history.get_messages())
            messages.append({"role": "user", "content": user_input})
            
            # Get response
            if mcp_tools:
                # Tool calling mode (non-streaming for simplicity)
                response, _ = client.chat_with_tools(
                    messages=messages,
                    tools=mcp_tools,
                    tool_executor=tool_executor,
                )
                console.print_assistant_message(response)
            else:
                # Streaming mode
                stream = client.chat(messages=messages, stream=True)
                response = stream_to_console(console, stream)
            
            # Save to history
            history.add("user", user_input)
            history.add("assistant", response)
            
            # Update memory agents with new conversation (background)
            full_history = history.get_messages()
            if notes_agent:
                try:
                    notes_agent.process_messages(full_history)
                except Exception:
                    pass  # Silently handle if storage unavailable
            if knowledge_agent:
                try:
                    knowledge_agent.process_messages(full_history)
                except Exception:
                    pass
            
        except KeyboardInterrupt:
            console.print_goodbye()
            break
        except Exception as e:
            console.print_error(str(e))


if __name__ == "__main__":
    main()
