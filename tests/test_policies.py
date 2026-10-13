from app import policies


def test_booking_does_not_retrieve_unrelated_policies(tmp_path, monkeypatch):
    (tmp_path / "hours.md").write_text(
        "Visits run Monday to Saturday.", encoding="utf-8"
    )
    (tmp_path / "cancellation.md").write_text(
        "A cancellation fee applies.", encoding="utf-8"
    )
    (tmp_path / "service_area.md").write_text(
        "Call a provider outside the service area.", encoding="utf-8"
    )
    monkeypatch.setattr(policies, "DIR", tmp_path)

    assert policies.search(
        "Need a plumber Friday morning. Call 312-555-0100."
    ) == []
    assert policies.hours_evidence()[0]["source"] == "hours.md"


def test_cancellation_question_retrieves_cancellation(tmp_path, monkeypatch):
    (tmp_path / "cancellation.md").write_text(
        "Cancellations within 24 hours incur a fee.",
        encoding="utf-8",
    )
    (tmp_path / "service_area.md").write_text(
        "Requests outside the area must be declined.",
        encoding="utf-8",
    )
    monkeypatch.setattr(policies, "DIR", tmp_path)

    hits = policies.search("Can I cancel my appointment?")
    assert hits
    assert {hit["source"] for hit in hits} == {"cancellation.md"}


def test_area_question_retrieves_service_area(tmp_path, monkeypatch):
    (tmp_path / "service_area.md").write_text(
        "Requests outside the service area must be declined.",
        encoding="utf-8",
    )
    (tmp_path / "cancellation.md").write_text(
        "Cancellations incur a fee.", encoding="utf-8"
    )
    monkeypatch.setattr(policies, "DIR", tmp_path)

    hits = policies.search("Do you serve ZIP code 60616?")
    assert hits
    assert {hit["source"] for hit in hits} == {"service_area.md"}