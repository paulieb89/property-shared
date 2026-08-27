"""Library-level configuration flags.

`property_core` is consumed directly by the REST API, two MCP servers and the
CLI, so a flag needed by all four is read from the environment here rather than
depending on any one consumer's settings object.
"""

from __future__ import annotations

import os

#: Values accepted as true. Anything else -- including an empty string, which is
#: what `KEY=` in a .env file produces -- is false. A snapshot flag must fail
#: closed: an unparseable value means "off", never "on".
_TRUE = frozenset({"1", "true", "yes", "on"})

PPD_SNAPSHOT_ENABLED_ENV = "PPD_SNAPSHOT_ENABLED"


def parse_bool_flag(value: object) -> bool:
    """Parse a feature-flag value. Fails CLOSED on anything unrecognised.

    This is the single parser for PPD_SNAPSHOT_ENABLED across every consumer.
    pydantic-settings would otherwise raise on "" or "nonsense" while the library
    returned False, so an operator typo would leave the CLI running happily and
    the API refusing to start. One parser, one behaviour: unrecognised means off.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in _TRUE


def ppd_snapshot_enabled() -> bool:
    """Whether the PPD snapshot source is enabled. Defaults to False.

    Read at call time, not at import time, so tests and processes can change it
    without reimporting the package.
    """
    return parse_bool_flag(os.getenv(PPD_SNAPSHOT_ENABLED_ENV))
