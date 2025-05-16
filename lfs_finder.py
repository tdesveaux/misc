#!/usr/bin/python3

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

CACHE_DIR = Path(".lfs_finder_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

session = requests.session()


@dataclass
class LfsPointer:
    name: str
    oid_type: str
    oid: str
    size: int

    @property
    def grep_expr(self):
        return f"oid {self.oid_type}:{self.oid}"

    def __hash__(self) -> int:
        return self.oid.__hash__()


def _output_cached(cmd: list[str], cache_path: Path):
    if cache_path.exists():
        print(f"using cache at {cache_path}")
        return cache_path.read_text()
    output = subprocess.check_output(cmd, text=True)
    cache_path.write_text(output)
    return output


lfs_pointers: list[LfsPointer] = [
    LfsPointer(
        name=lfs_file["name"],
        oid_type=lfs_file["oid_type"],
        oid=lfs_file["oid"],
        size=lfs_file["size"],
    )
    for lfs_file in json.loads(
        _output_cached(
            [
                "git",
                "lfs",
                "ls-files",
                "--all",
                "--json",
            ],
            CACHE_DIR / "ls-files.json",
        )
    )["files"]
]


def _get_remote_info(remote: str):
    remote_url = subprocess.check_output(
        ["git", "remote", "get-url", remote], text=True
    ).strip()

    credential_output = subprocess.check_output(
        ["git", "credential", "fill"], text=True, input=f"url={remote_url}"
    ).splitlines()
    username = next(
        (
            line[len("username=") :]
            for line in credential_output
            if line.startswith("username=")
        ),
        None,
    )
    password = next(
        (
            line[len("password=") :]
            for line in credential_output
            if line.startswith("password=")
        ),
        None,
    )

    if not remote_url.endswith(".git"):
        remote_url = f"{remote_url}.git"

    if username is not None and password is not None:
        return (remote, remote_url, (username, password))

    return (remote, remote_url, None)


remotes = [
    _get_remote_info(remote)
    for remote in subprocess.check_output(["git", "remote"], text=True).splitlines()
]


_file_revs_cache = {}


def get_commits(ptr: LfsPointer):
    revs = _file_revs_cache.get(ptr.name)
    if revs is None:
        _file_revs_cache[ptr.name] = revs = subprocess.check_output(
            ["git", "rev-list", "--all", "--", ptr.name], text=True
        ).splitlines()

    return [
        line.split(":", 1)[0]
        for line in subprocess.check_output(
            [
                "git",
                "grep",
                "--text",
                "--fixed-strings",
                ptr.grep_expr,
                *revs,
                "--",
                ptr.name,
            ],
            text=True,
        ).splitlines()
    ]


ok_lfs_cache: dict[str, set[str]] = {}
ok_lfs_cachepath = CACHE_DIR / "ok_lfs.json"
if ok_lfs_cachepath.exists():
    with ok_lfs_cachepath.open() as fp:
        # json set is serialized as list
        for k, v in json.load(fp).items():
            ok_lfs_cache[k] = set(v)
    print("loaded cache")

missing_pointer: list[LfsPointer] = []
commits_missing_lfs: dict[str, dict[LfsPointer, list[str]]] = {}
try:
    lfs_pointers_count = len(lfs_pointers)
    step = 100
    for idx, ptr in enumerate(lfs_pointers):
        if idx % step == 0:
            print(
                f"[{datetime.now().time()}] "
                f"{idx}/{lfs_pointers_count} "
                f"({(idx * 100) / lfs_pointers_count:.2f}%)"
            )
        for remote, remote_url, auth in remotes:
            if ptr.oid in ok_lfs_cache.get(remote, set()):
                continue
            with session.post(
                f"{remote_url}/info/lfs/verify",
                timeout=5 * 60,
                auth=auth,
                headers={"Accept": "application/vnd.git-lfs+json"},
                json={"oid": ptr.oid, "size": ptr.size},
            ) as response:
                if response.status_code != 200:
                    print(
                        f"{remote_url}/info/lfs/objects/{ptr.oid} "
                        f"({response.status_code})"
                    )
                    for commit in get_commits(ptr):
                        commits_missing_lfs.setdefault(commit, {}).setdefault(
                            ptr, []
                        ).append(remote)
                elif response.status_code != 404:
                    ok_lfs_cache.setdefault(remote, set()).add(ptr.oid)
                else:
                    response.raise_for_status()

except KeyboardInterrupt:
    pass
finally:
    print("dumping cache")
    with ok_lfs_cachepath.open(mode="w+") as fp:
        json.dump({k: list(v) for k, v in ok_lfs_cache.items()}, fp)


all_remotes = set(r for r, _, _ in remotes)

for commit, ptrs in commits_missing_lfs.items():
    commits_log = subprocess.check_output(
        ["git", "log", "--format=%H %an %s", "-1", commit], text=True
    ).strip()
    print(f"commit: {commits_log}")
    print("Missing LFS pointers:")
    for ptr, remotes in ptrs.items():
        print(f"\t{ptr.name}: {ptr.oid}", end="")
        if all_remotes != set(remotes):
            print(f" ({' '.join(remotes)})", end="")
        print()

    print("object_ids:")
    print(" ".join(ptr.oid for ptr in ptrs.keys()))
