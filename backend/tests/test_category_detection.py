from app.agents.prompts import detect_decision_category


def test_template_id_overrides_text_classification_when_paths_still_match_template():
    category = detect_decision_category(
        "Say what I feel",
        "Keep it to myself",
        template_id="relationship",
    )

    assert category == "relationship"


def test_stale_template_id_is_ignored_when_paths_change():
    category = detect_decision_category(
        "Stay employed",
        "Launch the startup",
        template_id="relationship",
    )

    assert category == "startup"


def test_constraints_and_samples_help_custom_classification():
    category = detect_decision_category(
        "Keep working",
        "Make the leap",
        constraints="I would need loans and tuition would be brutal for a few years.",
        writing_samples="I keep thinking about going back to school, but I am scared of the debt.",
    )

    assert category == "education"


def test_startup_keywords_still_win_when_present():
    category = detect_decision_category(
        "Stay employed",
        "Launch the startup",
        constraints="I have six months of runway and one cofounder.",
        writing_samples="I do not know if I should go all in on the company.",
    )

    assert category == "startup"
