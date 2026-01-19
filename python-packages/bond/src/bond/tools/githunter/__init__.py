"""Git Hunter: Forensic code ownership tool.

Provides tools for investigating git history to determine:
- Who last modified a specific line (blame)
- What PR discussion led to a change
- Who are the experts for a file based on commit frequency
"""

from ._adapter import GitHunterAdapter
from ._exceptions import (
    BinaryFileError,
    FileNotFoundInRepoError,
    GitHubUnavailableError,
    GitHunterError,
    LineOutOfRangeError,
    RateLimitedError,
    RepoNotFoundError,
    ShallowCloneError,
)
from ._protocols import GitHunterProtocol
from ._types import AuthorProfile, BlameResult, FileExpert, PRDiscussion

__all__ = [
    # Adapter
    "GitHunterAdapter",
    # Types
    "AuthorProfile",
    "BlameResult",
    "FileExpert",
    "PRDiscussion",
    # Protocol
    "GitHunterProtocol",
    # Exceptions
    "GitHunterError",
    "RepoNotFoundError",
    "FileNotFoundInRepoError",
    "LineOutOfRangeError",
    "BinaryFileError",
    "ShallowCloneError",
    "RateLimitedError",
    "GitHubUnavailableError",
]
