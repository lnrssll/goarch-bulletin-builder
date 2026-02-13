import argparse
from datetime import date, timedelta

def parse_day(value: str) -> int:
    day = int(value)
    if not 1 <= day <= 31:
        raise argparse.ArgumentTypeError("DAY must be in range 1–31")
    return day


def parse_month(value: str) -> int:
    month = int(value)
    if not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("MONTH must be in range 1–12")
    return month


def parse_year(value: str) -> int:
    year = int(value)
    if 0 <= year <= 99:
        year += 2000

    current_year = date.today().year
    if year < current_year:
        raise argparse.ArgumentTypeError(
            f"YEAR must be >= {current_year}"
        )

    return year


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the scraper for a specific date"
    )

    today = date.today()
    sunday_weekday_index = 6
    next_sunday = today + timedelta(days=((sunday_weekday_index - today.weekday()) or 7))

    parser.add_argument("day",   type=parse_day,   nargs="?", metavar="DAY",   default=next_sunday.day)
    parser.add_argument("month", type=parse_month, nargs="?", metavar="MONTH", default=next_sunday.month)
    parser.add_argument("year",  type=parse_year,  nargs="?", metavar="YEAR",  default=next_sunday.year)

    return parser
