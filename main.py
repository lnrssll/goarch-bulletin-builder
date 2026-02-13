from pathlib import Path
import asyncio
from datetime import date

from cli import build_parser

# import goarch_calendar  # blocked by cloudflare bot protection
import digital_chant_stand
import goarch_xml_feed
import manual_entry_template

BUILD_DIR = Path("build")


async def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        run_date = date(args.year, args.month, args.day)
    except ValueError as e:
        parser.error(str(e))

    if run_date.weekday() != 6:  # Sunday
        raise ValueError(f"Date input {run_date.isoformat()} is not a Sunday")

    out_dir = BUILD_DIR / run_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    # await goarch_calendar.run(run_date, out_path)
    await digital_chant_stand.run(run_date, out_dir)
    await goarch_xml_feed.run(run_date, out_dir)
    await manual_entry_template.run(run_date, out_dir)

    # subprocess.run(
    #     [
    #         "typst",
    #         "compile",
    #         "--input",
    #         f"date={run_date.isoformat()}",
    #         "bulletin.typ",
    #         output,
    #     ]
    # )

    # print("bulletin ready at", output)

    return 0


if __name__ == "__main__":
    asyncio.run(main())
