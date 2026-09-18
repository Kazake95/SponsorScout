"""Custom-scan scope: per-phase whitelists and phase toggles in run_scan."""
import csv
import threading

import pytest

from sponsorscout.scanning import pipeline


def _write_seed(path, names):
    cols = ["name", "ats_type", "careers_url", "industry",
            "sponsorship_history", "english_friendly", "remote_score"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for n in names:
            w.writerow({
                "name": n, "ats_type": "greenhouse",
                "careers_url": f"https://boards.greenhouse.io/{n.lower()}",
                "industry": "X", "sponsorship_history": "50",
                "english_friendly": "50", "remote_score": "50",
            })


class _FakeAts:
    instances = []

    def __init__(self, **kw):
        self.kw = kw
        self.run_id = ""
        _FakeAts.instances.append(self)

    def run(self):
        pass


class _FakeCareer:
    instances = []

    def __init__(self, **kw):
        self.kw = kw
        _FakeCareer.instances.append(self)

    def execute_crawler(self):
        pass


@pytest.fixture()
def scoped_env(tmp_path, monkeypatch):
    from sponsorscout.application import seed_manager

    seeds = tmp_path / "seeds"
    seeds.mkdir()
    _write_seed(seeds / "ats.csv", ["AtsOne", "AtsTwo", "AtsThree"])
    _write_seed(seeds / "career.csv", ["CarOne", "CarTwo"])
    monkeypatch.setattr(seed_manager, "SEEDS_DIR", seeds)
    monkeypatch.setattr(seed_manager, "user_ats_path", lambda: seeds / "ats.csv")
    monkeypatch.setattr(seed_manager, "user_career_path",
                        lambda: seeds / "career.csv")
    monkeypatch.setattr(seed_manager, "merge_bundled_seeds",
                        lambda log_fn=print: {})
    monkeypatch.setattr(pipeline.ats_module, "ATSScanner", _FakeAts)
    monkeypatch.setattr(pipeline.career_module, "CareerPortalScanner",
                        _FakeCareer)
    monkeypatch.setattr(pipeline, "recommended_workers", lambda kind: 1)
    _FakeAts.instances = []
    _FakeCareer.instances = []
    db_path = str(tmp_path / "test.db")
    return db_path


def test_custom_ats_only(scoped_env):
    summary = pipeline.run_scan(
        method="full", db_path=scoped_env,
        cancel_event=threading.Event(),
        only_ats=["AtsOne", "AtsTwo"], run_career=False,
        progress=lambda m: None)
    assert summary["method"] == "custom"
    assert summary["status"] == "completed"
    assert len(_FakeAts.instances) == 1
    assert _FakeAts.instances[0].kw["only_companies"] == ["AtsOne", "AtsTwo"]
    assert _FakeCareer.instances == []  # career phase disabled


def test_custom_career_only(scoped_env):
    summary = pipeline.run_scan(
        method="full", db_path=scoped_env,
        cancel_event=threading.Event(),
        only_career=["CarOne"], run_ats=False,
        progress=lambda m: None)
    assert summary["method"] == "custom"
    assert _FakeAts.instances == []
    assert len(_FakeCareer.instances) == 1
    assert _FakeCareer.instances[0].kw["only_companies"] == ["CarOne"]


def test_custom_disjoint_lists(scoped_env):
    pipeline.run_scan(
        method="full", db_path=scoped_env,
        cancel_event=threading.Event(),
        only_ats=["AtsOne"], only_career=["CarTwo"],
        progress=lambda m: None)
    assert _FakeAts.instances[0].kw["only_companies"] == ["AtsOne"]
    assert _FakeCareer.instances[0].kw["only_companies"] == ["CarTwo"]


def test_full_scan_unchanged_when_no_scope(scoped_env):
    """No scope → both phases run unfiltered, method stays 'full'."""
    summary = pipeline.run_scan(
        method="full", db_path=scoped_env,
        cancel_event=threading.Event(),
        progress=lambda m: None)
    assert summary["method"] == "full"
    assert _FakeAts.instances[0].kw["only_companies"] is None
    assert _FakeCareer.instances[0].kw["only_companies"] is None
