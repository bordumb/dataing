"""Prompt builders for investigation agents.

Each prompt module exposes:
- SYSTEM_PROMPT: Static system prompt template
- build_system(**kwargs) -> str: Build system prompt with dynamic values
- build_user(**kwargs) -> str: Build user prompt from context
"""

from . import hypothesis, interpretation, query, reflexion, synthesis

__all__ = [
    "hypothesis",
    "interpretation",
    "query",
    "reflexion",
    "synthesis",
]
