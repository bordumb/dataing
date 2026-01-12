"""Type definitions for Git Hunter tool.

Frozen dataclasses for git blame results, author profiles,
file experts, and PR discussions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AuthorProfile:
    """Git commit author with optional GitHub enrichment.

    Attributes:
        git_email: Author email from git commit.
        git_name: Author name from git commit.
        github_username: GitHub username if resolved from email.
        github_avatar_url: GitHub avatar URL if resolved.
    """

    git_email: str
    git_name: str
    github_username: str | None = None
    github_avatar_url: str | None = None


@dataclass(frozen=True)
class BlameResult:
    """Result of git blame for a single line.

    Attributes:
        line_no: Line number that was blamed.
        content: Content of the line.
        author: Author who last modified the line.
        commit_hash: Full SHA of the commit.
        commit_date: UTC datetime of the commit (author date).
        commit_message: First line of commit message.
        is_boundary: True if this is a shallow clone boundary commit.
    """

    line_no: int
    content: str
    author: AuthorProfile
    commit_hash: str
    commit_date: datetime
    commit_message: str
    is_boundary: bool = False


@dataclass(frozen=True)
class FileExpert:
    """Code ownership expert for a file based on commit history.

    Attributes:
        author: The author profile.
        commit_count: Number of commits touching the file.
        last_commit_date: UTC datetime of most recent commit.
    """

    author: AuthorProfile
    commit_count: int
    last_commit_date: datetime


@dataclass(frozen=True)
class PRDiscussion:
    """Pull request discussion associated with a commit.

    Attributes:
        pr_number: PR number.
        title: PR title.
        body: PR description body.
        url: URL to the PR on GitHub.
        issue_comments: Top-level PR comments (not review comments).
    """

    pr_number: int
    title: str
    body: str
    url: str
    issue_comments: tuple[str, ...]  # Frozen, so use tuple instead of list
