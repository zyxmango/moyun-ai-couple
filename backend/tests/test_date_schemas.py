from datetime import date

from app.schemas import AnniversaryUpdate, SummaryRequest


def test_summary_request_accepts_iso_date():
    request = SummaryRequest.model_validate({"period": "daily", "date": "2026-11-04"})

    assert request.date == date(2026, 11, 4)


def test_anniversary_update_accepts_iso_date():
    request = AnniversaryUpdate.model_validate({"date": "2027-01-02"})

    assert request.date == date(2027, 1, 2)
