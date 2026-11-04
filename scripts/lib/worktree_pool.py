#!/usr/bin/env python3
"""
Git Worktree Physical Isolation Pool (worktree_pool.py)
-------------------------------------------------------
Implements SPEC-AGY-002 & AD-194:
1. Module-level asyncio.Lock (_GIT_WORKTREE_LOCK) to prevent concurrent .git/config.lock contention.
2. Dirty working tree target mirroring so uncommitted local changes are accurately tested in detached worktrees.
3. Windows EBUSY / PermissionError exponential backoff (0.5s, 1.0s, 2.0s) and .pending_prune orphan recovery.
"""

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Iterable, Optional

from .safe_subprocess import run_streaming_process

_GIT_WORKTREE_LOCK = asyncio.Lock()


class GitWorktreePool:
    """Manages isolated temporary Git worktrees under .worktrees/ with zero workspace residue."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.pool_dir = (self.repo_root / ".worktrees").resolve()
        self.pending_prune_file = self.pool_dir / ".pending_prune"

    def _is_safe_worktree_path(self, candidate: Path) -> bool:
        resolved = candidate.resolve()
        return resolved != self.pool_dir and resolved.is_relative_to(self.pool_dir)

    async def prune_orphans(self) -> int:
        """Sweep any orphaned worktrees recorded in .pending_prune from prior locked runs."""
        pruned_count = 0
        async with _GIT_WORKTREE_LOCK:
            if not self.pending_prune_file.exists():
                return 0
            try:
                lines = [
                    line.strip()
                    for line in self.pending_prune_file.read_text(encoding="utf-8", errors="replace").splitlines()
                    if line.strip()
                ]
            except Exception:
                return 0

            remaining = []
            for raw_path in lines:
                wt_path = Path(raw_path).resolve()
                if not self._is_safe_worktree_path(wt_path):
                    continue
                if not wt_path.exists():
                    pruned_count += 1
                    continue
                res = await run_streaming_process(
                    ["git", "worktree", "remove", "--force", str(wt_path)],
                    cwd=self.repo_root,
                    timeout_seconds=15.0,
                )
                if res.returncode != 0 and wt_path.exists():
                    shutil.rmtree(wt_path, ignore_errors=True)
                if not wt_path.exists():
                    pruned_count += 1
                else:
                    remaining.append(str(wt_path))

            await run_streaming_process(["git", "worktree", "prune"], cwd=self.repo_root, timeout_seconds=10.0)

            if remaining:
                self.pending_prune_file.write_text("\n".join(remaining) + "\n", encoding="utf-8")
            else:
                self.pending_prune_file.unlink(missing_ok=True)

        return pruned_count

    async def acquire(
        self,
        commit_ish: str = "HEAD",
        mirror_files: Optional[Iterable[str]] = None,
    ) -> Path:
        """Create an isolated detached worktree and mirror specified dirty files from main workspace."""
        if not commit_ish or commit_ish.strip().startswith("-"):
            raise ValueError(f"Invalid commit_ish: {commit_ish!r}")
        await self.prune_orphans()
        self.pool_dir.mkdir(parents=True, exist_ok=True)
        wt_path = self.pool_dir / f"sentinel-{uuid.uuid4().hex[:8]}"

        async with _GIT_WORKTREE_LOCK:
            res = await run_streaming_process(
                ["git", "worktree", "add", "--detach", str(wt_path), commit_ish],
                cwd=self.repo_root,
                timeout_seconds=30.0,
            )
            if res.returncode != 0:
                raise RuntimeError(f"git worktree add failed: {res.stderr.strip()}")

        # Mirror uncommitted local modifications of target files (plus core scripts/lib) into the detached worktree
        try:
            wt_resolved = wt_path.resolve()
            core_lib_files = [
                "scripts/lib/__init__.py",
                "scripts/lib/safe_subprocess.py",
                "scripts/lib/worktree_pool.py",
                "scripts/lib/adversarial_team.py",
            ]
            combined_mirrors = list(dict.fromkeys([*core_lib_files, *(mirror_files or [])]))
            for rel_path in combined_mirrors:
                if not rel_path or Path(rel_path).is_absolute() or ".git" in Path(rel_path).parts:
                    continue
                src = (self.repo_root / rel_path).resolve()
                dst = (wt_resolved / rel_path).resolve()
                # CWE-22 Path containment guard: enforce is_relative_to() on both source and destination
                if (
                    src.is_relative_to(self.repo_root)
                    and dst.is_relative_to(wt_resolved)
                    and src.is_file()
                ):
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
        except Exception:
            await self.release(wt_path)
            raise

        return wt_path

    async def release(self, wt_path: Path) -> bool:
        """Remove worktree with exponential backoff for Windows file handle locks (EBUSY)."""
        wt_resolved = wt_path.resolve()
        if not self._is_safe_worktree_path(wt_resolved):
            raise ValueError(f"Refusing to release path outside worktree pool: {wt_resolved}")
        for delay in (0.0, 0.5, 1.0, 2.0):
            if delay > 0:
                await asyncio.sleep(delay)
            async with _GIT_WORKTREE_LOCK:
                res = await run_streaming_process(
                    ["git", "worktree", "remove", "--force", str(wt_resolved)],
                    cwd=self.repo_root,
                    timeout_seconds=15.0,
                )
                if res.returncode == 0 or not wt_resolved.exists():
                    return True
                shutil.rmtree(wt_resolved, ignore_errors=True)
                await run_streaming_process(["git", "worktree", "prune"], cwd=self.repo_root, timeout_seconds=10.0)
                if not wt_resolved.exists():
                    return True

        # Fallback: record in .pending_prune under _GIT_WORKTREE_LOCK for next run's orphan sweep
        async with _GIT_WORKTREE_LOCK:
            self.pool_dir.mkdir(parents=True, exist_ok=True)
            with open(self.pending_prune_file, "a", encoding="utf-8") as f:
                f.write(f"{wt_resolved}\n")
        return False

