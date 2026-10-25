"""The numeric grounding check: what counts as backed by the data, and what does not."""

from datetime import date

from dienstpilot_agents.copilot.grounding import Pool, extract, values_in


def pool() -> Pool:
    p = Pool("Wie viele Nachtdienste hat P3 am 12.11.2026 im November 2026?", "2026-10-25")
    p.add_result(
        {
            "totals": {"nacht": 5, "shifts": 14},
            "days": ["2026-11-03", "2026-11-12"],
            "id": "b5800c6f-7618-564e-a11c-22ee00bb5c03",
            "ratio": 17.5,
        }
    )
    return p


def test_numbers_from_the_question_the_data_and_today_are_grounded() -> None:
    p = pool()
    assert p.ungrounded("P3 hat 5 Nachtdienste von 14 Diensten im November 2026 (17,5).") == []
    assert p.ungrounded("Heute ist der 25.10.2026.") == []
    assert p.ungrounded("Am 12. November und am 3. November.") == []


def test_an_invented_number_or_date_is_found() -> None:
    p = pool()
    assert p.ungrounded("P3 hat 7 Nachtdienste.") == [7.0]
    assert p.ungrounded("Am 13.11.2026 hat P3 Dienst.") == [date(2026, 11, 13)]
    assert p.ungrounded("Am 20. November.") == [("md", 11, 20)]


def test_a_day_in_a_list_is_grounded_by_a_date_in_the_data_but_a_stray_one_is_not() -> None:
    p = pool()
    assert p.ungrounded("Nachtdienste am 3., 12. November") == []
    assert p.ungrounded("Nachtdienste am 3., 4. und 12. November") == [4.0]


def test_ids_aliases_and_month_names_are_not_numbers() -> None:
    assert extract("P12 und b5800c6f-7618-564e-a11c-22ee00bb5c03 im März") == []
    assert values_in({"id": "b5800c6f-7618-564e-a11c-22ee00bb5c03", "x": True}) == []


def test_date_formats_agree() -> None:
    for text in (
        "12.11.2026",
        "2026-11-12",
        "12 November 2026",
        "November 12, 2026",
        "12. November 2026",
    ):
        assert extract(text) == [date(2026, 11, 12)], text


def test_a_day_and_month_with_dots_is_a_date_not_a_decimal() -> None:
    p = pool()
    assert p.ungrounded("Am 12.11. und am 3.11.") == []
    assert p.ungrounded("Am 13.11. ist es so.") == [("md", 11, 13)]


def test_the_sign_of_a_number_does_not_matter() -> None:
    p = Pool("Frage", None)
    p.add_result({"params": {"hours": -0.5, "required": 11.0}})
    assert p.ungrounded("Ruhezeit -0,5 statt 11,0 Stunden, also 0,5 Stunden zu wenig.") == []
