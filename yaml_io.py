from pathlib import Path

import yaml


def read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_yaml(data: dict, path: Path) -> None:
    # write then rename, so a crash mid-write never leaves a truncated file
    partial = path.with_name(path.name + ".partial")
    partial.write_text(yaml.safe_dump(data) + "\n", encoding="utf-8")
    partial.replace(path)
