"""Protocol interface for prompt builders.

All prompt modules should follow this interface pattern,
though they don't need to formally implement it.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class PromptBuilder(Protocol):
    """Interface for agent prompt builders.

    Each prompt module should expose:
    - SYSTEM_PROMPT: str - Static system prompt template
    - build_system(**kwargs) -> str - Build system prompt with dynamic values
    - build_user(**kwargs) -> str - Build user prompt from context
    """

    SYSTEM_PROMPT: str

    @staticmethod
    def build_system(**kwargs: object) -> str:
        """Build system prompt, optionally with dynamic values."""
        ...

    @staticmethod
    def build_user(**kwargs: object) -> str:
        """Build user prompt from context."""
        ...
