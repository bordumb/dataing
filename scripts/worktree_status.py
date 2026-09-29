#!/usr/bin/env python3
"""Show which git worktrees still hold work that is not on origin/main.

Usage:
    just worktrees               # every worktree: branch, merged yes/no, and why not
    just worktrees --branches    # also local branches that no worktree has checked out
    python3 scripts/worktree_status.py [--branches]

PRs here are squash-merged, and the merge train often rebases a branch before merging
it, so `git branch --merged` misses most merged branches. Instead, every commit a branch
has that main lacks is matched against the commits of all merged PRs and of main itself:

1. the same commit is in a merged PR
2. a commit with the same patch is in a merged PR or on main (a clean rebase or squash)
3. a commit with the same title is (a rebase that resolved conflicts; noted "by title")

A branch is merged when all of its commits match, or when merging it into main would
change nothing. A worktree is "yes" only when its branch is merged and main already has
its uncommitted edits (changed and untracked files; ignored ones such as .env never
count): merging them onto main, with the worktree's HEAD as the base, changes nothing.
The edits are snapshotted in a throwaway index, so no worktree's index or files change.

Needs git 2.40+ (merge-tree --merge-base). gh is optional: without it, commits are only
matched against main.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAIN = "origin/main"
SQUASH_SUFFIX = re.compile(r" \(#(\d+)\)$")


def git(
    *args: str, cwd: str | None = None, stdin: str | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "color.ui=never", *args],
        cwd=cwd,
        input=stdin,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def out(*args: str, stdin: str | None = None) -> str:
    result = git(*args, stdin=stdin)
    if result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def ok(*args: str) -> bool:
    return git(*args).returncode == 0


def patch_ids(*log_args: str, stdin: str | None = None) -> dict[str, str]:
    """Map commit -> stable patch-id for the commits `git log` selects."""
    log = out("log", "-p", "--no-ext-diff", "--no-merges", *log_args, stdin=stdin)
    ids = out("patch-id", "--stable", stdin=log + "\n")
    return {commit: pid for pid, commit in (line.split() for line in ids.splitlines())}


def titles(*log_args: str, stdin: str | None = None) -> dict[str, str]:
    """Map commit -> subject line."""
    lines = out("log", "--no-merges", "--format=%H%x09%s", *log_args, stdin=stdin).splitlines()
    return dict(line.split("\t", 1) for line in lines if "\t" in line)


@dataclass
class Landed:
    """Where each merged commit, patch and title can be found ("#123" or "main")."""

    commits: dict[str, str] = field(default_factory=dict)
    patches: dict[str, str] = field(default_factory=dict)
    titles: dict[str, str] = field(default_factory=dict)


def landed_index(prs: list[dict[str, Any]]) -> Landed:
    index = Landed()
    merged = [pr for pr in prs if pr["state"] == "MERGED"]
    check = out(
        "cat-file",
        "--batch-check=%(objectname) %(objecttype)",
        stdin="\n".join(pr["headRefOid"] for pr in merged),
    )
    local_heads = {line.split()[0] for line in check.splitlines() if line.endswith(" commit")}
    for pr in merged:
        if pr["headRefOid"] in local_heads:
            for commit in out("rev-list", pr["headRefOid"], "--not", MAIN).split():
                index.commits.setdefault(commit, f"#{pr['number']}")
    if index.commits:
        stdin = "\n".join(index.commits)
        for commit, pid in patch_ids("--no-walk=unsorted", "--stdin", stdin=stdin).items():
            index.patches.setdefault(pid, index.commits[commit])
        for commit, title in titles("--no-walk=unsorted", "--stdin", stdin=stdin).items():
            index.titles.setdefault(title, index.commits[commit])
    for pid in patch_ids(MAIN).values():
        index.patches.setdefault(pid, "main")
    for title in titles(MAIN).values():
        squash = SQUASH_SUFFIX.search(title)
        if squash:
            index.titles.setdefault(title[: squash.start()], f"#{squash.group(1)}")
        index.titles.setdefault(title, "main")
    return index


def pull_requests() -> list[dict[str, Any]]:
    """Every PR of the repo, or none (with a warning) when gh is unavailable."""
    result = subprocess.run(
        "gh pr list --state all --limit 5000 --json number,headRefName,headRefOid,state".split(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"warning: no PR data ({result.stderr.strip()})", file=sys.stderr)
        return []
    prs: list[dict[str, Any]] = json.loads(result.stdout)
    return prs


def branch_on_main(tip: str, index: Landed, main_tree: str) -> tuple[bool, str]:
    """Whether everything `tip` adds is on main, and a short note."""
    if ok("merge-base", "--is-ancestor", tip, MAIN):
        return True, ""
    own = out("rev-list", "--no-merges", f"{MAIN}..{tip}").split()
    stdin = "\n".join(own)
    pids = patch_ids("--no-walk=unsorted", "--stdin", stdin=stdin) if own else {}
    subjects = titles("--no-walk=unsorted", "--stdin", stdin=stdin) if own else {}
    missing, by_title = [], set()
    for commit in own:
        if commit in index.commits or pids.get(commit) in index.patches:
            continue
        if subjects.get(commit) in index.titles:
            by_title.add(index.titles[subjects[commit]])
        else:
            missing.append(commit)
    if not missing:
        return True, f"by title: {', '.join(sorted(by_title))}" if by_title else ""
    merge = git("merge-tree", "--write-tree", MAIN, tip)
    if merge.returncode == 0 and merge.stdout.split()[0] == main_tree:
        return True, "content already on main"
    return False, f"{len(missing)} of {len(own)} commit(s) not on main or in a merged PR"


def pr_status(prs: list[dict[str, Any]]) -> str:
    """Summarize the PRs opened from one branch name."""
    for state, label in (("OPEN", "open"), ("MERGED", "merged earlier"), ("CLOSED", "closed")):
        numbers = [f"#{pr['number']}" for pr in prs if pr["state"] == state]
        if numbers:
            return f"PR {', '.join(numbers)} {label}"
    return "no PR"


def snapshot(path: str, head: str, paths: list[str]) -> str | None:
    """A commit (parent HEAD) holding the worktree's current files, or None on failure.

    It is built in a throwaway index, so the worktree's own index and files stay untouched.
    """
    with tempfile.TemporaryDirectory() as scratch:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        steps = [
            ("read-tree", head),
            ("add", "--all", "--pathspec-from-file=-", "--pathspec-file-nul"),
            ("write-tree",),
        ]
        result = None
        for step in steps:
            stdin = "\0".join(paths) if step[0] == "add" else None
            result = git(*step, cwd=path, stdin=stdin, env=env)
            if result.returncode != 0:
                return None
    assert result is not None
    commit = git("commit-tree", result.stdout.strip(), "-p", head, "-m", "worktree snapshot")
    return commit.stdout.strip() if commit.returncode == 0 else None


def uncommitted(path: str, head: str, index: Landed, main_tree: str) -> tuple[bool, str]:
    """Whether the worktree has uncommitted edits that main lacks, and a short note.

    Sessions often open PRs straight from another worktree's uncommitted files. So the
    edits (HEAD to the files on disk, untracked files included) are merged onto main with
    HEAD as the base: when that changes nothing, main already has them.
    """
    if not Path(path).is_dir():
        return False, "worktree dir missing"
    # --no-optional-locks: never take the index lock of a worktree another session uses
    status = git(
        "--no-optional-locks", "status", "--porcelain", "-z", "--untracked-files=all", cwd=path
    )
    if status.returncode != 0:
        return True, "git status failed"
    entries, paths = iter(status.stdout.split("\0")), []
    for entry in entries:
        if entry:
            paths.append(entry[3:])
            if "R" in entry[:2] or "C" in entry[:2]:
                paths.append(next(entries, ""))  # a rename or copy is followed by its source
    paths = [p for p in paths if p]
    if not paths:
        return False, ""
    commit = snapshot(path, head, paths)
    if commit is None:
        return True, f"uncommitted: {len(paths)} file(s) (could not compare with main)"
    merge = git("merge-tree", "--write-tree", f"--merge-base={head}", MAIN, commit)
    merged_tree = merge.stdout.split()[0] if merge.stdout else ""
    if merge.returncode == 0 and merged_tree == main_tree:
        return False, f"{len(paths)} uncommitted file(s), already on main"
    pid = patch_ids("--no-walk", commit).get(commit)
    if pid in index.patches:
        return False, f"{len(paths)} uncommitted file(s), already in {index.patches[pid]}"
    changes = len(out("diff", "--name-only", main_tree, merged_tree).splitlines())
    conflicts = "" if merge.returncode == 0 else ", conflicts with main"
    return True, f"uncommitted: {len(paths)} file(s), {changes} would change main{conflicts}"


@dataclass
class Row:
    """One output line: a worktree or branch, and whether its work is on main."""

    name: str
    merged: bool
    note: str


def row(
    name: str,
    tip: str,
    prs: list[dict[str, Any]],
    index: Landed,
    main_tree: str,
    path: str | None,
) -> Row:
    merged, note = branch_on_main(tip, index, main_tree)
    notes = [note] if note else []
    if not merged:
        notes.append(pr_status(prs))
    dirty, dirty_note = uncommitted(path, tip, index, main_tree) if path else (False, "")
    if dirty_note:
        notes.append(dirty_note)
    if path and (dirty or not merged) and Path(path).name not in name:
        notes.append(f"[{Path(path).name}]")
    return Row(name, merged and not dirty, "; ".join(notes))


def show(title: str, rows: list[Row]) -> None:
    rows.sort(key=lambda r: (r.merged, r.name))
    width = max(len(r.name) for r in rows)
    print(f"\n{title}: {sum(not r.merged for r in rows)} of {len(rows)} not merged\n")
    print(f"{'BRANCH':<{width}}  MERGED  NOTE")
    for r in rows:
        print(f"{r.name:<{width}}  {'yes' if r.merged else 'no':<6}  {r.note}".rstrip())


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "--branches",
        action="store_true",
        help="also list local branches that no worktree has checked out",
    )
    args = parser.parse_args()

    if git("fetch", "--quiet", "origin", "main").returncode != 0:
        print(f"warning: fetch failed, using the local {MAIN}", file=sys.stderr)
    main_tree = out("rev-parse", f"{MAIN}^{{tree}}")
    prs = pull_requests()
    index = landed_index(prs)
    by_branch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pr in prs:
        by_branch[pr["headRefName"]].append(pr)

    rows, checked_out = [], set()
    for block in out("worktree", "list", "--porcelain").split("\n\n"):
        wt = dict(line.partition(" ")[::2] for line in block.splitlines())
        if "worktree" not in wt or "bare" in wt:
            continue
        branch = wt.get("branch", "").removeprefix("refs/heads/")
        checked_out.add(branch)
        name = branch or f"(detached) {Path(wt['worktree']).name}"
        branch_prs = by_branch[branch] if branch else []
        rows.append(row(name, wt["HEAD"], branch_prs, index, main_tree, wt["worktree"]))
    show("Worktrees", rows)

    if args.branches:
        others = []
        refs = out("for-each-ref", "refs/heads", "--format=%(refname:short) %(objectname)")
        for line in refs.splitlines():
            branch, tip = line.split()
            if branch not in checked_out:
                others.append(row(branch, tip, by_branch[branch], index, main_tree, None))
        if others:
            show("Local branches not checked out anywhere", others)


if __name__ == "__main__":
    main()
