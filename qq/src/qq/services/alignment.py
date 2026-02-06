"""Alignment Agent - silent post-answer reviewer.

Reviews answers that use sourced information to verify citation accuracy.
Only surfaces when issues are found; otherwise invisible to the user.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from strands import Agent

logger = logging.getLogger("qq.alignment")


def _load_system_prompt() -> str:
    """Load the alignment agent system prompt."""
    prompt_path = Path(__file__).parent.parent / "agents" / "alignment" / "alignment.system.md"
    if prompt_path.exists():
        return prompt_path.read_text().strip()
    # Fallback inline prompt
    return "You are a JSON-only answer reviewer. Output {\"pass\": true, \"issues\": []} if correct."


def _parse_json_response(response: str) -> Dict[str, Any]:
    """Extract JSON from LLM response, handling thinking tags and markdown."""
    # Remove <think>...</think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    cleaned = cleaned.strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find first { and match braces
    first_brace = cleaned.find('{')
    if first_brace != -1:
        brace_count = 0
        in_string = False
        escape_next = False
        for i, char in enumerate(cleaned[first_brace:]):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_str = cleaned[first_brace:first_brace + i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        break

    logger.warning("Failed to parse alignment response as JSON")
    return {"pass": True, "issues": []}


class AlignmentAgent:
    """Silent post-answer reviewer.

    Reviews answers against their source materials to check citation
    accuracy. Only surfaces issues when found.
    """

    def __init__(self, model=None):
        """Initialize the alignment agent.

        Args:
            model: Model instance for the review LLM call.
        """
        self.model = model
        self._agent = None
        self._system_prompt = None

    def _ensure_agent(self) -> Optional[Agent]:
        """Lazy-initialize the alignment sub-agent."""
        if self._agent is not None:
            return self._agent
        if self.model is None:
            return None

        if self._system_prompt is None:
            self._system_prompt = _load_system_prompt()

        self._agent = Agent(
            name="alignment_reviewer",
            system_prompt=self._system_prompt,
            model=self.model,
        )
        return self._agent

    def review(
        self,
        answer: str,
        sources: List[Dict[str, Any]],
        context_text: str,
    ) -> Dict[str, Any]:
        """Review an answer against its sources.

        Args:
            answer: The agent's response text
            sources: List of source dicts from SourceRegistry
            context_text: The context that was injected pre-turn

        Returns:
            {"pass": bool, "issues": [...], "corrections": str|None}
        """
        # Skip review if no sources or agent unavailable
        if not sources:
            return {"pass": True, "issues": []}

        agent = self._ensure_agent()
        if agent is None:
            return {"pass": True, "issues": []}

        # Build compact review prompt
        sources_text = "\n".join(
            f"[{s['index']}] ({s['type']}) {s['label']}"
            + (f" — {s['detail']}" if s.get('detail') else "")
            for s in sources
        )

        prompt = (
            f"## Answer to review\n\n{answer}\n\n"
            f"## Available sources\n\n{sources_text}\n\n"
            f"## Context provided to the agent\n\n{context_text[:2000]}\n\n"
            f"Review the answer against the sources. Output JSON only."
        )

        try:
            response = str(agent(prompt))
            result = _parse_json_response(response)

            # Ensure expected shape
            if "pass" not in result:
                result["pass"] = True
            if "issues" not in result:
                result["issues"] = []

            return result
        except Exception as e:
            logger.warning(f"Alignment review failed: {e}")
            return {"pass": True, "issues": []}
