"""AI chat launcher.

Opens a web-based AI chat (ChatGPT, Gemini, Claude.ai, ...) in the user's
DEFAULT SYSTEM BROWSER. The user copies a prompt from SponsorScout, pastes
it into the chat, gets a reply, and copies the reply back into SponsorScout
("semi-automated" workflow).

BUGFIX (2x): an earlier version tried to embed the chat in a pywebview
window.
  1. In a PyInstaller build, running pywebview in a multiprocessing.Process
     re-launches the frozen executable -- the window never appeared.
  2. Running it in a background thread instead hit pywebview's hard
     requirement that its GUI loop run on the MAIN thread (GTK/Cocoa
     backends) -- "pywebview must be run on a main thread", which would
     conflict with Tkinter's own main loop.

Using the system browser avoids all of this: zero extra dependencies (no
pywebview, no WebView2/webkit2gtk runtime needed), works identically on
Windows/Linux/macOS, and reuses the user's EXISTING browser login session for
ChatGPT/Gemini/Claude/etc. -- which is more reliable than a fresh embedded
profile anyway.
"""
from __future__ import annotations

import logging
import webbrowser

logger = logging.getLogger(__name__)

# -- Known web AI chat destinations ------------------------------------------
# Display name -> URL. Order matters: this is the order shown to the user.
AI_SITES: dict[str, str] = {
    "ChatGPT":   "https://chatgpt.com/",
    "Gemini":    "https://gemini.google.com/app",
    "Claude":    "https://claude.ai/new",
    "Mistral":   "https://chat.mistral.ai/chat",
    "Perplexity": "https://www.perplexity.ai/",
}

DEFAULT_SITE = "ChatGPT"


class AIWebviewLauncher:
    """Opens an AI chat site in the user's default system browser."""

    def open(self, site_name: str = DEFAULT_SITE) -> None:
        """Open *site_name* in a new browser tab/window.

        Raises RuntimeError if the system reports no way to open a browser
        (e.g. headless Linux with no BROWSER env var / xdg-open), so the
        caller can show a useful message instead of doing nothing.
        """
        url = AI_SITES.get(site_name, AI_SITES[DEFAULT_SITE])
        try:
            opened = webbrowser.open(url, new=2)
        except webbrowser.Error as exc:
            raise RuntimeError(
                f"No browser available to open {url}: {exc}"
            ) from exc
        if not opened:
            raise RuntimeError(
                f"Could not open a browser for {url}. "
                "If you're on Linux, make sure a default browser is "
                "configured (e.g. via xdg-settings)."
            )

    def close(self) -> None:
        # Nothing to clean up -- the browser is a separate application.
        pass
