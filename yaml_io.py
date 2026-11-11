from pathlib import Path

import yaml


def read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_yaml(data: dict, path: Path) -> None:
    write_atomic(path, (yaml.safe_dump(data, allow_unicode=True) + "\n").encode("utf-8"))


def write_atomic(path: Path, content: bytes) -> None:
    # write then rename, so a crash mid-write never leaves a truncated file
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(content)
    partial.replace(path)
