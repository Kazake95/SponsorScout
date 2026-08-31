"""Tests for scan-row -> job-record mapping and the sponsorship scoreboard."""
from sponsorscout.scanning import pipeline


def _career_row(**overrides):
    row = {
        "Company Name": "Pleo", "Seed Name": "Pleo", "Source Type": "direct_employer",
        "Hiring Company": "Pleo", "Target Country": "Global", "Scope Policy": "global",
        "Industry Type": "Fintech", "Sponsorship History Score": "80",
        "English Friendly Score": "90", "Remote Score": "75",
        "Job Title": "Senior Backend Engineer", "Raw Job Title": "Senior Backend Engineer",
        "Job Location": "Berlin, Germany", "Raw Location": "Berlin, Germany",
        "Job Type": "Full-time / On-site", "Job URL": "https://jobs.ashbyhq.com/pleo/abc",
        "Canonical Job ID": "pleo-abc", "Provider": "ashby",
        "Extraction Method": "api", "EU Blue Card": "Y", "Blue Card Evidence": "blau karte",
        "Relocation/Visa Support": "Yes", "Location Source": "card",
        "URL Type": "real", "Visa Sponsorship": "Yes", "Relocation Support": "Unknown",
        "Relocation Required": "No", "Support Confidence": "0.9",
        "Support Evidence": "We offer visa sponsorship",
        "Support Evidence URL": "https://jobs.ashbyhq.com/pleo/abc",
        "Support Evidence Type": "description", "Record Status": "accepted",
        "Quarantine Reason": "", "Run ID": "R1", "Scanned At": "now",
    }
    row.update(overrides)
    return row


def test_row_to_job_maps_verdicts():
    job = pipeline._row_to_job(_career_row(), source_subtype="direct", run_id="R1")
    assert job["company"] == "Pleo"
    assert job["country"] == "Germany"  # parsed from location, not seed
    assert job["location"] == "Berlin, Germany"
    assert job["visa_sponsorship"] == "Y"
    assert job["relocation_support"] == "Unknown"  # honest three-state
    assert job["relocation_required"] == "N"
    assert job["eu_blue_card_verdict"] == "Y"
    assert job["eu_blue_card"] == 1
    assert job["has_relocation"] == 0
    assert job["canonical_job_id"] == "pleo-abc"
    assert job["run_id"] == "R1"
    assert job["source_subtype"] == "direct"


def test_row_to_job_normalises_verdict_words():
    job = pipeline._row_to_job(
        _career_row(**{"Relocation Support": "Yes", "Visa Sponsorship": "No"}),
        source_subtype="direct", run_id="R1")
    assert job["relocation_support"] == "Y"
    assert job["visa_sponsorship"] == "N"


def test_row_to_job_rejects_blank_rows():
    assert pipeline._row_to_job(
        _career_row(**{"Job URL": "", "Job Title": "x"}),
        source_subtype="direct", run_id="R1") is None
    assert pipeline._row_to_job(
        _career_row(**{"Job URL": "https://x/y", "Job Title": "Unknown"}),
        source_subtype="direct", run_id="R1") is None


def test_row_to_job_unknown_confidence_zero():
    job = pipeline._row_to_job(_career_row(**{"Support Confidence": ""}), run_id="R1")
    assert job["support_confidence"] == 0.0


def test_sponsorship_score_components():
    # Y + high confidence + strong seed history must score high.
    job = pipeline._row_to_job(_career_row(), run_id="R1")
    assert job["sponsorship_score"] == 96  # 70 + 18 (conf) + 8 (history)
    # Unknown verdict scores neutrally (35), never as a hard No.
    job_unknown = pipeline._row_to_job(
        _career_row(**{"Visa Sponsorship": "Unknown", "Support Confidence": "0"}),
        run_id="R1")
    assert job_unknown["sponsorship_score"] == 35
    # Explicit No scores 0 regardless of history.
    job_no = pipeline._row_to_job(
        _career_row(**{"Visa Sponsorship": "No", "Support Confidence": "0"}),
        run_id="R1")
    assert job_no["sponsorship_score"] == 0


def test_recruiter_rows_map_source_subtype():
    job = pipeline._row_to_job(
        _career_row(**{"Source Type": "recruiter", "Hiring Company": "Unknown"}),
        source_subtype="recruiter", run_id="R1")
    assert job["source_subtype"] == "recruiter"
    assert job["company"] == "Pleo"  # falls back to seed name, not 'Unknown'
