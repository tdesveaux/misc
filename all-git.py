#!/usr/bin/python3

import datetime
import sys
import click
from pathlib import Path
import subprocess

@click.group()
def cli():
    pass

def enumerate_git():
    cwd = Path()
    for p in cwd.rglob(".git"):
        if p.is_dir():
            if p.parent == cwd:
                yield p.parent.absolute()
            else:
                yield p.parent.relative_to(cwd)

@cli.command()
def fetch():
    for repo in enumerate_git():
        display_name = f" {repo} "
        display_len = max(len(display_name) + 4, 60)
        print(f"\r{display_name:=^{display_len}}", end='', flush=True)
        fetch_cmd = ["git", "fetch", "--all", "--prune", "--tags"]
        process = subprocess.run(
            fetch_cmd,
            cwd=repo, text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # retry once
        if process.returncode:
            process = subprocess.run(
                fetch_cmd,
                cwd=repo, text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        if process.returncode:
            print(
                f"command {fetch_cmd} in {repo} failed with code {process.returncode}.\n"
                f"stdout: {process.stdout}\n"
                f"stderr: {process.stderr}\n"
                )
        if any(
            e.split()[0] != "Fetching"
            for e
            in process.stderr.splitlines(keepends=False)
        ):
            print()
            print(process.stderr)
            print(end='', flush=True)

    print('\r' + ' ' * 60, flush=True, end='\r')


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
