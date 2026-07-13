"""Before/after report comparison."""

from nectar_conformance.results.compare import compare_reports


def _report(statuses):
    return {
        "results": [{"rule_id": rid, "status": st} for rid, st in statuses]
    }


def test_compare_classifies_changes():
    old = _report(
        [
            ("glance.api.image_tag", "fail"),
            ("mariadb.version", "pass"),
            ("networking.uses_networkd", "pass"),
            ("os.mq.ubuntu", "fail"),
        ]
    )
    new = _report(
        [
            ("glance.api.image_tag", "pass"),  # fixed
            ("mariadb.version", "pass"),  # unchanged pass
            ("networking.uses_networkd", "fail"),  # regressed
            ("os.mq.ubuntu", "fail"),  # still failing
        ]
    )
    diff = compare_reports(old, new)
    assert [r["rule_id"] for r in diff["fixed"]] == ["glance.api.image_tag"]
    assert [r["rule_id"] for r in diff["regressed"]] == [
        "networking.uses_networkd"
    ]
    assert [r["rule_id"] for r in diff["still_failing"]] == ["os.mq.ubuntu"]


def test_compare_added_and_removed():
    old = _report([("a.b", "pass")])
    new = _report([("c.d", "fail")])
    diff = compare_reports(old, new)
    assert [r["rule_id"] for r in diff["removed"]] == ["a.b"]
    assert [r["rule_id"] for r in diff["added"]] == ["c.d"]
