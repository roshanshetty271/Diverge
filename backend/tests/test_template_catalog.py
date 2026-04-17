from fastapi.testclient import TestClient

from app.data.template_catalog import get_template_catalog
from app.main import create_app


def test_template_catalog_has_all_frontend_templates():
    templates = get_template_catalog()
    assert len(templates) == 9
    assert [template.id for template in templates] == [
        "career",
        "city",
        "startup",
        "education",
        "relationship",
        "lifestyle",
        "volunteer",
        "trade",
        "family",
    ]


def test_templates_route_uses_shared_catalog():
    client = TestClient(create_app())

    response = client.get("/api/templates")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 9
    assert payload[0]["id"] == "career"
    assert payload[-1]["id"] == "family"
    assert {item["category"] for item in payload} == {
        "career",
        "financial",
        "startup",
        "education",
        "relationship",
        "health",
        "general",
    }
