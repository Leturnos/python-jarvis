from core.infra.update_preferences import UpdatePreferenceManager


def test_can_check_on_boot_initial(tmp_path):
    mgr = UpdatePreferenceManager(state_file=tmp_path / "updates_state.json")
    assert mgr.can_check_on_boot() is True


def test_can_check_on_boot_rate_limited(tmp_path):
    mgr = UpdatePreferenceManager(
        state_file=tmp_path / "updates_state.json",
        check_interval_hours=24.0,
    )
    now = 1000000.0
    mgr.record_check(timestamp=now)

    # 1 hour later -> should be rate limited
    assert mgr.can_check_on_boot(now=now + 3600.0) is False
    # 25 hours later -> should allow check
    assert mgr.can_check_on_boot(now=now + 25 * 3600.0) is True


def test_should_notify_version_default(tmp_path):
    mgr = UpdatePreferenceManager(state_file=tmp_path / "updates_state.json")
    assert mgr.should_notify_version("v1.2.0") is True


def test_should_notify_version_snoozed(tmp_path):
    mgr = UpdatePreferenceManager(state_file=tmp_path / "updates_state.json")
    now = 1000000.0
    mgr.snooze(hours=24.0, now=now)

    # 2 hours later, still snoozed
    assert mgr.should_notify_version("v1.2.0", now=now + 7200.0) is False

    # 25 hours later, snooze expired
    assert mgr.should_notify_version("v1.2.0", now=now + 25 * 3600.0) is True


def test_should_notify_version_dismissed(tmp_path):
    mgr = UpdatePreferenceManager(state_file=tmp_path / "updates_state.json")
    mgr.dismiss_version("v1.2.0")

    # Dismissed version is suppressed
    assert mgr.should_notify_version("v1.2.0") is False

    # But a newer or different version is NOT suppressed
    assert mgr.should_notify_version("v1.3.0") is True


def test_persistence_across_instances(tmp_path):
    state_file = tmp_path / "updates_state.json"
    mgr1 = UpdatePreferenceManager(state_file=state_file)
    mgr1.record_check(timestamp=123456.0)
    mgr1.dismiss_version("v0.9.0")
    mgr1.snooze(hours=12.0, now=100000.0)

    # Instantiate second manager with same file
    mgr2 = UpdatePreferenceManager(state_file=state_file)
    assert mgr2.last_check_timestamp == 123456.0
    assert mgr2.dismissed_version == "v0.9.0"
    assert mgr2.dismissed_until == 100000.0 + 12.0 * 3600.0


def test_corrupt_json_recovery(tmp_path):
    state_file = tmp_path / "updates_state.json"
    state_file.write_text("{invalid json content!@#", encoding="utf-8")

    mgr = UpdatePreferenceManager(state_file=state_file)
    # Should safely load defaults without raising an exception
    assert mgr.last_check_timestamp == 0.0
    assert mgr.dismissed_version is None
    assert mgr.can_check_on_boot() is True
