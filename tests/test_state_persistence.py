from concurrent.futures import ThreadPoolExecutor

from app import analysis_sessions, cohorts, user_settings, user_state


def test_concurrent_analysis_session_saves_do_not_lose_records(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis_sessions, "USER_STATE_ROOT", tmp_path / "users")

    def save(index):
        return analysis_sessions.save_analysis_session({"id": f"session-{index}", "title": f"Session {index}"})

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(save, range(12)))

    assert {item["id"] for item in analysis_sessions.list_analysis_sessions()} == {
        f"session-{index}" for index in range(12)
    }


def test_concurrent_saved_cohort_writes_preserve_records_and_unique_names(tmp_path, monkeypatch):
    monkeypatch.setattr(cohorts, "USER_STATE_ROOT", tmp_path / "users")

    def save(index):
        return cohorts.save_cohort(
            name="Concurrent cohort",
            data_dir="/unavailable/test-dataset",
            members=[dict(dataset_id='test', patient_id=f'P{index}')],
            id_type="patient",
            source_kind="test",
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        created = list(executor.map(save, range(12)))

    stored = cohorts.list_saved_cohorts()
    assert len(stored) == 12
    assert len({item["id"] for item in stored}) == 12
    assert len({item["name"] for item in created}) == 12


def test_concurrent_user_setting_patches_preserve_independent_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(user_state, "STATE_ROOT_DIR", tmp_path / "state")
    patches = [
        {"landing_tab": "analysis"},
        {"query_default_mode": "planner_only"},
        {"dashboard_assays_open": True},
        {"dataset_compact_view": True},
    ]

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda patch: user_settings.update_user_settings(patch, "alice"), patches))

    stored = user_settings.load_user_settings("alice")
    assert stored["landing_tab"] == "analysis"
    assert stored["query_default_mode"] == "planner_only"
    assert stored["dashboard_assays_open"] is True
    assert stored["dataset_compact_view"] is True
