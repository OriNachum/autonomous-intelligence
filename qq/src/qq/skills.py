"""Skills loader - injects relevant skills into conversations."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass 
class Skill:
    """A loaded skill."""
    name: str
    description: str
    triggers: list[str]
    content: str
    path: Path


def find_skills_dir() -> Path:
    """Find the skills directory relative to project root."""
    package_dir = Path(__file__).parent.parent.parent
    skills_dir = package_dir / "skills"
    
    if skills_dir.exists():
        return skills_dir
    
    cwd_skills = Path.cwd() / "skills"
    if cwd_skills.exists():
        return cwd_skills
    
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def load_all_skills() -> list[Skill]:
    """Load all skills from the skills directory."""
    skills_dir = find_skills_dir()
    skills = []
    
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        
        skill = _parse_skill(skill_file)
        if skill:
            skills.append(skill)
    
    return skills


def _parse_skill(skill_file: Path) -> Optional[Skill]:
    """Parse a SKILL.md file with YAML frontmatter."""
    content = skill_file.read_text()
    
    # Parse YAML frontmatter (between --- markers)
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    
    if frontmatter_match:
        try:
            metadata = yaml.safe_load(frontmatter_match.group(1))
            body = frontmatter_match.group(2).strip()
        except yaml.YAMLError:
            return None
    else:
        # No frontmatter - use filename as name
        metadata = {"name": skill_file.parent.name}
        body = content.strip()
    
    return Skill(
        name=metadata.get("name", skill_file.parent.name),
        description=metadata.get("description", ""),
        triggers=metadata.get("triggers", []),
        content=body,
        path=skill_file,
    )


def find_relevant_skills(message: str, skills: list[Skill]) -> list[Skill]:
    """
    Find skills relevant to the given message based on triggers.
    
    Args:
        message: User message to check
        skills: List of loaded skills
        
    Returns:
        List of relevant skills
    """
    message_lower = message.lower()
    relevant = []
    
    for skill in skills:
        for trigger in skill.triggers:
            if trigger.lower() in message_lower:
                relevant.append(skill)
                break  # Only add skill once
    
    return relevant


def inject_skills(base_prompt: str, skills: list[Skill]) -> str:
    """
    Inject skill content into the system prompt.
    
    Args:
        base_prompt: Base system prompt
        skills: Skills to inject
        
    Returns:
        Enhanced prompt with skill content
    """
    if not skills:
        return base_prompt
    
    skill_sections = []
    for skill in skills:
        skill_sections.append(f"## Skill: {skill.name}\n{skill.content}")
    
    return f"""{base_prompt}

# Active Skills
The following specialized skills are relevant to this conversation:

{chr(10).join(skill_sections)}"""


def create_example_skill() -> None:
    """Create an example skill in the skills directory."""
    skills_dir = find_skills_dir()
    coding_dir = skills_dir / "coding"
    coding_dir.mkdir(parents=True, exist_ok=True)
    
    skill_content = """---
name: coding
description: Enhanced coding assistance
triggers:
  - code
  - python
  - javascript
  - debug
  - implement
  - function
  - class
---

# Coding Skill

When helping with code:

1. **Understand First**: Ask clarifying questions if requirements are unclear
2. **Explain Approach**: Briefly explain your solution strategy
3. **Write Clean Code**: Use meaningful names and add comments where helpful
4. **Handle Errors**: Include appropriate error handling
5. **Test Cases**: Suggest or provide test cases when applicable

For debugging:
- Ask for error messages and stack traces
- Request relevant code context
- Suggest systematic debugging approaches"""
    
    skill_file = coding_dir / "SKILL.md"
    if not skill_file.exists():
        skill_file.write_text(skill_content)
