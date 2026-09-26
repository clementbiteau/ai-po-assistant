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
    assert not [t for t in app.toggle if "synthétiques" in t.label]  # real usage only
    assert any(m.label == "Dépense du mois" for m in app.metric)
    next(b for b in app.button if b.key == "load_notifications").click().run()
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


def test_inbox_starts_empty_with_a_prompt() -> None:
    app = login("demo@local.dev")
    assert app.session_state["feedback_text"] == ""
    assert not any(b.label == "Lancer l'analyse" for b in app.button)  # nothing to run yet
    assert sum(b.label == "Charger ce cas" for b in app.button) == 3
    next(b for b in app.button if b.key == "load_mobile").click().run()
    assert any(b.label == "Lancer l'analyse" for b in app.button)
    assert any("Tri instantané" in e.label for e in app.expander)


def test_admin_picks_models_and_sees_runs_with_their_configuration(tmp_path) -> None:
    import os
    from pathlib import Path

    from agents import PipelineResult, ranking_summary
    from config import PRESETS
    from store import RunDetails, RunRecord, SQLiteRepository

    demo = PipelineResult.model_validate_json(Path("tests/fixtures/reference_result.json").read_text(encoding="utf-8"))
    repo = SQLiteRepository(os.environ["LOCAL_DB_PATH"])
    admin = repo.ensure_user("admin@local.dev", PASSWORD, role="admin")
    for preset in ("reference", "writer_haiku"):
        details = RunDetails("Notifications & churn", PRESETS[preset].config, ranking_summary(demo))
        repo.record_run(RunRecord(user_id=admin, kind="pipeline", status="success", model="m", duration_s=100.0,
                                  cost_eur=0.15, details=details))  # fmt: skip

    app = login("admin@local.dev")
    assert not app.exception
    picker = app.selectbox(key="adm_preset")
    assert picker.value == "reference"
    picker.select("writer_haiku").run()
    assert not app.exception
    assert any("Coût estimé" in c.value for c in app.sidebar.caption)
    assert "Runs" in tab_labels(app)
    frames = [d.value for d in app.dataframe if "Top 3" in d.value.columns]
    assert frames and len(frames[0]) == 2
    assert frames[0]["Configuration (analyste · stratège · rédacteur)"].str.contains("Haiku 4.5").any()


def test_member_has_no_model_picker() -> None:
    app = login("demo@local.dev")
    assert not app.exception
    assert not [s for s in app.selectbox if s.key == "adm_preset"]
    assert any("Modèles : Sonnet 5" in c.value for c in app.sidebar.caption)


def test_connectors_tab_is_a_roadmap_with_no_live_connection() -> None:
    app = login("demo@local.dev")
    assert not app.exception
    assert "Connecteurs" in tab_labels(app)
    buttons = [b for b in app.button if (b.key or "").startswith("connect_")]
    assert len(buttons) >= 6 and all(b.disabled for b in buttons)
