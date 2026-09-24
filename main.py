import asyncio
import sys
from datetime import timedelta
from pathlib import Path

import digital_chant_stand
import goarch_xml_feed
import manual_entry_template
import text_sizing
from cli import parse_run_options
from utils import ARCHIVE_DIR, SourceArchive, http_client

BUILD_DIR = Path("build")


async def main() -> int:
    options = parse_run_options()
    run_date = options.run_date

    out_dir = BUILD_DIR / run_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    async with http_client() as client:
        archive = SourceArchive(ARCHIVE_DIR / run_date.isoformat(), client, options.refresh)
        await asyncio.gather(
            digital_chant_stand.run(run_date, out_dir, archive),
            goarch_xml_feed.run(run_date, out_dir, archive),
        )
    archive.save()
    manual_entry_template.run(run_date, out_dir)
    text_sizing.run(out_dir)

    print(f"last build at: {BUILD_DIR / (run_date - timedelta(days=7)).isoformat()}")
    print(f"new build at: {out_dir}")
    print(f"sources archived at: {archive.root}")
    print("To compile bulletin from build data, run:")
    print(f'"{run_date.isoformat()}" | typst watch --input date=($in) booklet.typ out/($in).pdf')
    print(f"PDF output at out/{run_date.isoformat()}.pdf")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
