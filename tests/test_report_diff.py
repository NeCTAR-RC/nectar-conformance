"""Before/after report comparison."""

from nectar_conformance.results.compare import compare_reports


def _report(statuses):
    return {
        "results": [
            {"rule_id": rid, "severity": sev, "status": st}
            for rid, sev, st in statuses
        ]
    }


def test_compare_classifies_changes():
    old = _report(
        [
            ("glance.api.image_tag", "error", "fail"),
            ("mariadb.version", "error", "pass"),
            ("networking.uses_networkd", "warning", "pass"),
            ("os.mq.ubuntu", "warning", "fail"),
        ]
    )
    new = _report(
        [
            ("glance.api.image_tag", "error", "pass"),  # fixed
            ("mariadb.version", "error", "pass"),  # unchanged pass
            ("networking.uses_networkd", "warning", "fail"),  # regressed
            ("os.mq.ubuntu", "warning", "fail"),  # still failing
        ]
    )
    diff = compare_reports(old, new)
    assert [r["rule_id"] for r in diff["fixed"]] == ["glance.api.image_tag"]
    assert [r["rule_id"] for r in diff["regressed"]] == [
        "networking.uses_networkd"
    ]
    assert [r["rule_id"] for r in diff["still_failing"]] == ["os.mq.ubuntu"]


def test_compare_added_and_removed():
    old = _report([("a.b", "error", "pass")])
    new = _report([("c.d", "error", "fail")])
    diff = compare_reports(old, new)
    assert [r["rule_id"] for r in diff["removed"]] == ["a.b"]
    assert [r["rule_id"] for r in diff["added"]] == ["c.d"]
