import re

# a quote after one of these opens; anywhere else it closes (or is an apostrophe)
OPENS_AFTER = r"\s(\[{“‘—–"


def typographic(text: str) -> str:
    """Curly quotes and apostrophes, as Typst markup would set them: Typst prints a string's own as they are."""
    # double quotes first, so a single quote nested just inside one ("'Hosanna) sees it open
    text = re.sub(rf'(^|[{OPENS_AFTER}])"', "\\1“", text).replace('"', "”")
    return re.sub(rf"(^|[{OPENS_AFTER}])'", "\\1‘", text).replace("'", "’")


def tidy(text: str) -> str:
    """One space between words: Typst prints a string's double spaces and line breaks as they are."""
    return " ".join(text.split())


def printed(text: str) -> str:
    return typographic(tidy(text))
