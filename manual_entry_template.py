from datetime import date, timedelta
from pathlib import Path

from yaml_io import write_yaml


def run(run_date: date, out_dir: Path) -> None:
    out_path = out_dir / "manual.yaml"
    if out_path.exists():
        return

    next_service_date = run_date + timedelta(days=6)
    data = {
        "dismissal_hymns": [
            {"title": "Example", "page": "p. 0", "mode": 9},
        ],
        "upcoming_services": [
            {"date": "Today", "priest": "Fr. X"},
            {"date": f"{next_service_date:%m/%d/%Y}", "priest": "Fr. X"},
        ],
    }
    write_yaml(data, out_path)
