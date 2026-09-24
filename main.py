import asyncio
import sys
from datetime import timedelta

import sunday
from cli import parse_run_options
from utils import ARCHIVE_DIR


async def main() -> int:
    options = parse_run_options()
    run_date = options.run_date
    out_dir = sunday.build_dir(run_date)

    fetched = await sunday.download_readings(run_date, options.refresh)
    for source, error in fetched.failures.items():
        print(f"{source.name} failed, nothing written for it: {error}", file=sys.stderr)
    if fetched.failures:
        return 1

    print(f"last build at: {sunday.build_dir(run_date - timedelta(days=7))}")
    print(f"new build at: {out_dir}")
    print(f"sources archived at: {ARCHIVE_DIR / run_date.isoformat()}")
    print("To compile bulletin from build data, run:")
    print(f'"{run_date.isoformat()}" | typst watch --input date=($in) booklet.typ out/($in).pdf')
    print(f"PDF output at out/{run_date.isoformat()}.pdf")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
