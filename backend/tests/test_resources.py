from app.data.resources import (
    detect_primary_bottleneck,
    get_rotating_fallback_resources,
    select_timeline_resources,
)


def test_detect_primary_bottleneck_for_family_pressure():
    bottleneck = detect_primary_bottleneck(
        "Stay home and help run the family restaurant",
        "Take the job in Chicago and send money home",
        constraints="My parents depend on me and my younger brother is not ready to step up yet.",
        writing_samples="I feel guilty even thinking about leaving.",
        decision_category="general",
    )

    assert bottleneck == "family_duty_pressure"


def test_generic_family_mention_does_not_force_family_duty_pressure():
    bottleneck = detect_primary_bottleneck(
        "Stay in my current role for better family time",
        "Take the promotion and travel more",
        constraints="I want to be around more on weekends, but no one depends on me for care.",
        writing_samples="I am mostly worried about making the wrong call.",
        decision_category="career",
    )

    assert bottleneck != "family_duty_pressure"


def test_resource_selection_returns_one_book_video_and_concept():
    resources = get_rotating_fallback_resources(
        "Stay employed",
        "Start my own thing",
        "I have six months of savings and a real fear of failure.",
        decision_category="startup",
    )

    assert [resource["type"] for resource in resources] == ["book", "video", "concept"]
    assert all(resource["why"] for resource in resources)


def test_distinct_category_and_bottleneck_inputs_do_not_collapse_to_same_trio():
    career_titles = tuple(
        resource["title"]
        for resource in get_rotating_fallback_resources(
            "Stay in my current role",
            "Change careers",
            "I am scared of failing and becoming a beginner again.",
            decision_category="career",
        )
    )
    relationship_titles = tuple(
        resource["title"]
        for resource in get_rotating_fallback_resources(
            "Tell my friend how I feel",
            "Keep it to myself",
            "I am terrified of rejection and embarrassment.",
            decision_category="relationship",
        )
    )

    assert career_titles != relationship_titles


def test_timeline_resources_return_structured_items_and_bottleneck():
    items, bottleneck = select_timeline_resources(
        "Keep working as a medical assistant",
        "Go back to school for nursing",
        "I help with rent at home and cannot be unpaid for long.",
        writing_samples="The tuition scares me more than the classes do.",
        decision_category="education",
    )

    assert bottleneck == "scarcity_panic"
    assert [item["type"] for item in items] == ["book", "video", "concept"]
    assert all(item["why_it_helps"] for item in items)
