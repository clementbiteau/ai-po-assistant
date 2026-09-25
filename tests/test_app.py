"""End-to-end UI tests with Streamlit's AppTest (local auth mode, no network)."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from config import get_settings

PASSWORD = "test-only-password"


@pytest.fixture(autouse=True)
def local_mode(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("LOCAL_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("LOCAL_DEV_PASSWORD", PASSWORD)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def login(email: str, password: str = PASSWORD) -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=60)
    # AppTest cannot render st.dialog trees: skip the onboarding modal here
    # (its effect is covered by test_onboarding_launch_runs_the_demo).
    app.session_state["onboarded"] = True
    app.run()
    app.text_input[0].input(email)
    app.text_input[1].input(password)
    app.button[0].click().run()
    return app


def tab_labels(app: AppTest) -> list[str]:
    return [t.label for t in app.tabs]


def test_anonymous_visitor_only_sees_the_login_form() -> None:
    app = AppTest.from_file("../app.py", default_timeout=60)
    app.run()
    assert not app.exception
    assert [t.label for t in app.text_input] == ["Email", "Mot de passe"]
    assert not app.tabs


def test_wrong_password_is_rejected() -> None:
    app = login("demo@local.dev", "wrong")
    assert "incorrect" in app.error[0].value
    assert not app.tabs


def test_member_has_no_admin_console() -> None:
    app = login("demo@local.dev")
    assert not app.exception
    assert "Inbox" in tab_labels(app) and "Admin" not in tab_labels(app)


def test_admin_console_and_demo_run() -> None:
    app = login("admin@local.dev")
    assert not app.exception
    assert "Admin" in tab_labels(app)
    next(b for b in app.button if b.label == "Générer 60 jours").click().run()
    assert not app.exception
    assert any(m.label == "Dépense du mois" for m in app.metric)
    next(b for b in app.button if b.label == "Lancer l'analyse").click().run()  # offline demo replay
    assert not app.exception
    assert app.session_state["result"] is not None


def test_onboarding_launch_runs_the_demo() -> None:
    app = login("demo@local.dev")
    # What the dialog's "Démarrer" button records before triggering a rerun:
    app.session_state["pending_sample"] = "notifications"
    app.session_state["pending_run"] = "demo"
    app.run()
    assert not app.exception
    assert app.session_state["result"] is not None and app.session_state["result"].is_demo
