import os
from pathlib import Path
from datetime import date, timedelta
from utils import write_yaml

async def run(run_date: date, out_dir: Path) -> None:
    out_path = out_dir / "manual.yaml"

    if os.path.exists(out_path):
        return None

    next_service_date = run_date + timedelta(days=6)
    data = {
        "dismissal_hymns": [
            {
                "title": "Example",
                "page": "p. 0",
                "mode": 9
            }
        ],
        "upcoming_services": [
            {
                "date": "Today",
                "priest": "Fr. X"
            },
            {
                "date": next_service_date.strftime("%m/%d/%Y"),
                "priest": "Fr. X"
            },
        ]
    }
    await write_yaml(data, out_path)

    print(f"edit manual entry data at: {out_path}")
