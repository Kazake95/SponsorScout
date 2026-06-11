
from __future__ import annotations

import logging
from contextlib import contextmanager
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def _new_session() -> Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD", "POST"}),
        raise_on_status=False,
    )
    session = Session()
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "SponsorScout/1.0"})
    return session


def build_session() -> Session:
    """Return a fresh Session. Caller is responsible for .close().

    B12 fix: prior to this change every connector called build_session() and
    dropped the reference, leaking connection pools. Use http_session() as a
    context manager for the safe path.
    """
    return _new_session()


@contextmanager
def http_session():
    """Context manager that closes the session (and its connection pool) on exit.

    Usage:
        with http_session() as s:
            s.get(...)
    """
    s = _new_session()
    try:
        yield s
    finally:
        try:
            s.close()
        except Exception as exc:
            logger.exception("Failed to close HTTP session")
