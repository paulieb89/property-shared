"""Values shared by the rehearsal guards. **No optional dependency.**

`test_shadow_rehearsal.py` needs DuckDB and zstandard to run the tool, so it
`importorskip`s both at module level. The guards over the *summary document*
need neither -- they read a markdown file -- and must not inherit that skip: a
documentation guard that disappears when a native wheel is absent is a guard
that stops working exactly when nobody notices.

So the forbidden values live here, imported by both, and the summary guards live
in their own dependency-free module.
"""

from __future__ import annotations

#: Values from the rehearsal fixture rows that must NEVER appear in a report or
#: in any document describing one. Ids, prices and addresses are the three
#: categories the authorisation forbids, and both are files someone will paste
#: into a review.
FORBIDDEN_IN_REPORT = ["T-B57-A", "T-B50-A", "T-M37-A",
                       "210000", "400000", "250000", "HIGH STREET"]
