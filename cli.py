import argparse
from dataclasses import dataclass
from datetime import date, timedelta

SUNDAY = 6


def parse_day(value: str) -> int:
    day = int(value)
    if not 1 <= day <= 31:
        raise argparse.ArgumentTypeError("DAY must be in range 1-31")
    return day


def parse_month(value: str) -> int:
    month = int(value)
    if not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("MONTH must be in range 1-12")
    return month


def parse_year(value: str) -> int:
    year = int(value)
    if 0 <= year <= 99:
        year += 2000

    current_year = date.today().year
    if year < current_year:
        raise argparse.ArgumentTypeError(f"YEAR must be >= {current_year}")

    return year


def next_sunday(today: date) -> date:
    return today + timedelta(days=(SUNDAY - today.weekday()) or 7)


@dataclass
class RunOptions:
    run_date: date
    refresh: bool


def parse_run_options() -> RunOptions:
    parser = argparse.ArgumentParser(description="Run the scraper for a specific date")

    default = next_sunday(date.today())
    parser.add_argument("day",   type=parse_day,   nargs="?", metavar="DAY",   default=default.day)
    parser.add_argument("month", type=parse_month, nargs="?", metavar="MONTH", default=default.month)
    parser.add_argument("year",  type=parse_year,  nargs="?", metavar="YEAR",  default=default.year)
    parser.add_argument("--refresh", action="store_true", help="re-download sources already in archive/")
    args = parser.parse_args()

    try:
        run_date = date(args.year, args.month, args.day)
    except ValueError as e:
        parser.error(str(e))

    if run_date.weekday() != SUNDAY:
        parser.error(f"{run_date.isoformat()} is not a Sunday")

    return RunOptions(run_date, args.refresh)
