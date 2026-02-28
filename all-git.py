#!/usr/bin/python3
from __future__ import annotations

import asyncio
import datetime
import shutil
import subprocess
import sys
from collections.abc import Callable, Coroutine, Iterator
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

import click

if TYPE_CHECKING:
    _T = TypeVar("_T")
    _P = ParamSpec("_P")


def sync(func: Callable[_P, Coroutine[Any, Any, _T]]) -> Callable[_P, _T]:
    """Decorator that wraps coroutine with asyncio.run."""

    @wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        return asyncio.run(func(*args, **kwargs))

    return wrapper


@click.group()
def cli() -> None:
    pass


def enumerate_git() -> Iterator[Path]:
    cwd = Path()
    for p in cwd.rglob(".git"):
        if p.is_dir():
            if p.parent == cwd:
                yield p.parent.absolute()
            else:
                yield p.parent.relative_to(cwd)


@cli.command()
@sync
async def fetch() -> None:
    git_exe = shutil.which("git")
    if git_exe is None:
        raise RuntimeError("Failed to find git")
    fetch_cmd = ["fetch", "--all", "--prune", "--tags"]

    async def _fetch(repo: Path) -> tuple[int | None, bytes, bytes]:
        process = await asyncio.subprocess.create_subprocess_exec(
            git_exe,
            *fetch_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo,
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout, stderr

    async def _task(repo: Path) -> tuple[int | None, bytes, bytes]:
        returncode, stdout, stderr = await _fetch(repo)
        if returncode != 0:
            returncode, stdout, stderr = await _fetch(repo)
        return returncode, stdout, stderr

    tasks = [
        (repo, asyncio.create_task(_task(repo), name=f"fetch {repo}"))
        for repo in enumerate_git()
    ]

    for idx, (repo, task) in enumerate(tasks):
        display_name = f" {repo} ({idx+1}/{len(tasks)}) "
        display_len = max(len(display_name) + 4, 60)
        print(f"\r{display_name:=^{display_len}}", end="", flush=True)

        returncode, stdout, stderr_b = await task
        stderr = stderr_b.decode()
        if returncode:
            print(
                f"command {git_exe} {fetch_cmd} in {repo} failed with code {returncode}.\n"
                f"stdout: {stdout.decode()}\n"
                f"stderr: {stderr}\n"
            )
        if any(e.split()[0] != "Fetching" for e in stderr.splitlines(keepends=False)):
            print()
            print(stderr)
            print(end="", flush=True)

    print("\r" + " " * 60, flush=True, end="\r")


def print_git_logs(
    author: str | None = None,
    after: datetime.datetime | None = None,
    before: datetime.datetime | None = None,
):
    log_cmd = "git log --color --oneline --remotes --first-parent --graph".split()
    if author:
        log_cmd.append(f"--author={author}")

    if after is not None:
        log_cmd.append(f"--after={after.ctime()}")
    if before is not None:
        log_cmd.append(f"--before={before.ctime()}")

    for repo in enumerate_git():
        process = subprocess.run(
            log_cmd, cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        process.check_returncode()
        if process.stdout.strip():
            print(f"===== {repo} =====")
            print(process.stdout.strip())
            print(end='', flush=True)

@cli.command()
@click.option("--author", default="Desveaux")
def yesterday(author: str | None):
    today = datetime.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - datetime.timedelta(days=1 if today.weekday() != 0 else 3)
    print_git_logs(author=author, after=yesterday, before=today)

@cli.command()
@click.option("--author", default="Desveaux")
def last_week(author: str | None):
    today = datetime.datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    last_week = today - datetime.timedelta(days=7)
    print_git_logs(author=author, after=last_week, before=today)

@cli.command()
@click.option("--author", default="Desveaux")
@click.argument("after", type=click.DateTime(formats=['%Y-%m-%d']))
@click.argument("before", type=click.DateTime(formats=['%Y-%m-%d']))
def range(
    author: str | None,
    after: datetime.datetime,
    before: datetime.datetime,
):
    print_git_logs(author=author, after=after, before=before)


@cli.command()
def gone():
    for repo in enumerate_git():
        branches = subprocess.check_output(
            ['git', 'branch', '-vvv'], cwd=repo,
            text=True,
        ).strip().splitlines()
        branches = [
            b for b in branches
            if ': gone] ' in b
        ]
        if branches:
            print(f"===== {repo} =====")
            for b in branches:
                print(f"\t- {b}")
            print(end='', flush=True)

@cli.command()
@click.argument('args', nargs=-1)
def exec(args: tuple[str]):
    for repo in enumerate_git():
        display_name = f" {repo} "
        display_len = max(len(display_name) + 4, 60)
        print(f"\r{display_name:=^{display_len}}", flush=True)
        cmd = ["git", *args]
        process = subprocess.run(
            cmd,
            cwd=repo, text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        process.check_returncode()
        if stdout := process.stdout.strip():
            print(stdout)
            print(end='', flush=True)

if __name__ == "__main__":
    sys.exit(cli())
