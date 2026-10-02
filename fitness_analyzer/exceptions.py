"""Exceptions raised while reading and checking the input files."""


class InvalidIdentifierError(ValueError):
    """A participant or session ID does not follow the expected pattern."""

    def __init__(self, field, value, expected):
        self.field = field
        self.value = value
        self.expected = expected
        super().__init__("{0!r} is not a valid ID, expected {1}".format(
            value, expected))


class InvalidRecordError(ValueError):
    """A CSV row cannot be accepted.

    Holds every problem found in the row as (field, reason) pairs, so a row
    with several bad values is reported once with all of them listed.
    """

    def __init__(self, problems):
        problems = list(problems)
        if not problems:
            raise ValueError("InvalidRecordError needs at least one problem")
        self.problems = problems
        super().__init__("; ".join(
            "{0}: {1}".format(field, reason) for field, reason in problems))

    @classmethod
    def single(cls, field, reason):
        return cls([(field, reason)])


class DataFileError(Exception):
    """A whole file cannot be used, for example because its header is wrong."""

    def __init__(self, path, reason):
        self.path = path
        self.reason = reason
        super().__init__("{0}: {1}".format(path, reason))
