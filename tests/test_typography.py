import pytest

from typography import printed, tidy, typographic


@pytest.mark.parametrize(
    "text, expected",
    [
        ('The Lord said, "No one has ascended."', "The Lord said, “No one has ascended.”"),
        ("at Jesus' knees", "at Jesus’ knees"),
        ("he called out, 'Father Abraham,", "he called out, ‘Father Abraham,"),
        ("rise from the dead.'\"", "rise from the dead.’”"),
        ('"Legion"; for many', "“Legion”; for many"),
        ("\"'Hosanna!' they cried\"", "“‘Hosanna!’ they cried”"),
        ('saying—"Come"', "saying—“Come”"),
        ("(“Come and see”)", "(“Come and see”)"),
    ],
)
def test_quotes(text, expected):
    assert typographic(text) == expected


def test_spaces():
    assert tidy("  sure.  I desire\nthese things ") == "sure. I desire these things"
    assert printed(' "Teacher,  what" ') == "“Teacher, what”"
