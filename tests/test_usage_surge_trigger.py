"""Skeleton tests for the usage_surge trigger service.

All tests are skipped until A2 implements app/services/usage_surge_trigger.py.
After A2 lands, remove the @pytest.mark.skip decorator from each test, fill in
the fixture setup, and replace `pass` with real assertions.

TODO (main session): flip skip → enabled once usage_surge_trigger.py exists.
"""
from __future__ import annotations

import pytest


@pytest.mark.skip(reason="等 A2 实现 app/services/usage_surge_trigger.py")
def test_no_rules_returns_zero():
    """When there are no alert rules in the DB the trigger returns 0 alerts created.

    Setup:
        - Empty alert_rule table (no usage-surge rules configured).
    Expected:
        - trigger.run() returns 0 (or an object with triggered_count == 0).
    TODO: import trigger, create in-memory DB session, call trigger.run(db),
          assert result == 0.
    """
    pass


@pytest.mark.skip(reason="等 A2 实现 app/services/usage_surge_trigger.py")
def test_threshold_not_exceeded():
    """When a rule exists but the month-over-month usage change is below the threshold,
    no alert is created.

    Setup:
        - One alert_rule with threshold=50% (50 percent MoM surge).
        - cc_usage data for the rule's customer+service: current month only +20% vs prior.
    Expected:
        - trigger.run(db) returns 0 alerts created.
        - cc_alert table remains empty.
    TODO: seed alert_rule + cc_usage rows, run trigger, query cc_alert count == 0.
    """
    pass


@pytest.mark.skip(reason="等 A2 实现 app/services/usage_surge_trigger.py")
def test_threshold_exceeded_creates_alert():
    """When MoM usage exceeds the configured threshold an alert row is inserted into cc_alert.

    Setup:
        - One alert_rule with threshold=30% for customer X, service Y.
        - cc_usage: prior month $100, current month $150 (+50%, exceeds threshold).
    Expected:
        - trigger.run(db) returns 1.
        - cc_alert has exactly one new row with the correct customer_id / service / amount fields.
    TODO: seed data, run trigger, assert cc_alert count == 1 and check row fields.
    """
    pass


@pytest.mark.skip(reason="等 A2 实现 app/services/usage_surge_trigger.py")
def test_dedup_within_same_month():
    """When the same customer+service combination has already triggered an alert this month,
    the trigger does not insert a duplicate row.

    Setup:
        - One alert_rule for customer X, service Y, threshold=10%.
        - cc_usage: clear surge (e.g. +80% MoM).
        - cc_alert already contains one row for customer X, service Y, current month.
    Expected:
        - trigger.run(db) returns 0 (dedup: alert already fired this month).
        - cc_alert still has exactly one row (no duplicate inserted).
    TODO: pre-seed existing cc_alert row, run trigger, assert count stays at 1.
    """
    pass
