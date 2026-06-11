"""
B15 fix: BaseConnector is now an abstract base class so a future connector
that forgets to implement fetch_jobs() fails loudly at instantiation time
instead of returning silently empty results at scan time.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    ats_name: str = "base"

    @abstractmethod
    def fetch_jobs(self, company: dict) -> list[dict]:
        """Return a list of normalized job dicts for the given company."""
        raise NotImplementedError
