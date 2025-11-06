from watchdog_service import WatchdogService


def test_watchdog_restart_on_failure():
    service = WatchdogService(interval=1.0)
    state = {"fail": True, "restarted": 0}

    def check():
        if state["fail"]:
            state["fail"] = False
            return False, "unreachable"
        return True, None

    def restart():
        state["restarted"] += 1

    service.register_check("relay", check, restart=restart)
    service.probe_once()
    assert state["restarted"] == 1
    service.probe_once()
    snapshot = service.snapshot()
    assert snapshot["healthy"] is True
    assert snapshot["checks"][0]["failures"] == 0
