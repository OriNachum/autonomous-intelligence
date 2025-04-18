# Convert Responses format to Chat Completions format
def convert_responses_to_chat_completions(request, messages):
    chat_request = {
        "model": request.model,
        "messages": messages,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_completion_tokens": request.max_output_tokens,  # Correct mapping
        "stream": request.stream,
        "store": request.store,
        "parallel_tool_calls": request.parallel_tool_calls,
        "tool_choice": request.tool_choice,
        "tools": request.tools,
        "user": request.user,
        "metadata": request.metadata,
    }
    
    # Optional mappings - only add if present in original request
    if hasattr(request, "frequency_penalty"):
        chat_request["frequency_penalty"] = request.frequency_penalty
    
    if hasattr(request, "presence_penalty"):
        chat_request["presence_penalty"] = request.presence_penalty
        
    if hasattr(request, "logprobs"):
        chat_request["logprobs"] = request.logprobs
        
    if hasattr(request, "n"):
        chat_request["n"] = request.n
        
    if hasattr(request, "stop"):
        chat_request["stop"] = request.stop
        
    if hasattr(request, "stream_options"):
        chat_request["stream_options"] = request.stream_options
    
    if hasattr(request, "reasoning_effort") and request.reasoning_effort:
        chat_request["reasoning_effort"] = request.reasoning_effort
    elif hasattr(request, "reasoning") and request.reasoning and request.reasoning.get("effort"):
        # Map reasoning.effort to reasoning_effort
        chat_request["reasoning_effort"] = request.reasoning.get("effort")
    
    if hasattr(request, "response_format"):
        chat_request["response_format"] = request.response_format
    
    if hasattr(request, "seed"):
        chat_request["seed"] = request.seed
        
    if hasattr(request, "service_tier"):
        chat_request["service_tier"] = request.service_tier
    
    if hasattr(request, "modalities"):
        chat_request["modalities"] = request.modalities
        
    if hasattr(request, "audio"):
        chat_request["audio"] = request.audio
    
    # Remove any None values
    return {k: v for k, v in chat_request.items() if v is not None}
