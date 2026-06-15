"""Per-tab UI builders for SponsorScout.

This package is a structural placeholder following
SponsorScout_Codebase_Analysis.md §3.10 / §7 (#8): the long-term goal is to
move each `_build_*_tab` method in ``ui/app.py`` here, sharing state through
a thin ``AppContext`` object so each tab can be reasoned about and tested
in isolation.

For now the explicit "we kept the monolith for now" reasoning is documented
here so an AI/maintainer picking this up later knows the package was
intentionally introduced even though the actual builders still live in
``ui/app.py``. See ``docs/backend_expansion.md`` for future-state sketches.
"""

# Re-export nothing yet - the actual methods live on SponsorScoutApp in
# ui/app.py. When a real split is done, this __init__ will expose one factory
# function per tab (e.g. ``from sponsorscout.ui.tabs import build_search_tab``).
__all__: list[str] = []
