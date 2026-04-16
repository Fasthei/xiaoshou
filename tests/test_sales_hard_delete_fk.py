"""Regression test for hard-delete + lead_assignment_log FK violation.

Reproduces the production 500 (ForeignKeyViolation on
`lead_assignment_log_from_user_id_fkey`) that happened when DELETE
/api/sales/users/{id}/hard was called on a manually-created sales user
who already had historical assignment-log rows referencing them.

SQLite doesn't enforce FK constraints by default — which is why the
earlier `test_hard_delete_manual_user_recycles_customers_and_cleans_rules`
didn't catch the bug. We turn FK enforcement ON explicitly here via
`PRAGMA foreign_keys=ON` so the test mirrors Postgres behaviour.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.customer import Customer
from app.models.sales import LeadAssignmentLog, SalesUser
from main import app


@pytest.fixture()
def fk_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Force SQLite to enforce FKs like Postgres does — this is how we
    # reproduce the prod FK violation locally.
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()

    def _override():
        try:
            yield s
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    try:
        yield s
    finally:
        s.close()
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(fk_session):
    return TestClient(app)


def test_hard_delete_nullifies_historical_log_fks(client, fk_session):
    """Reproduces the prod bug: hard-deleting a sales user that has an
    existing lead_assignment_log row pointing at them (from/to_user_id)
    must succeed (200) and leave the log row intact with those FKs NULL.

    Without the fix this raises IntegrityError / returns 500.
    """
    # Setup: two users, one customer, one historical log row where both
    # from_user_id and to_user_id reference the user we're about to delete.
    u_old = SalesUser(name="要被硬删的张三", is_active=False)
    u_new = SalesUser(name="新销售", is_active=True)
    fk_session.add_all([u_old, u_new])
    fk_session.commit()
    fk_session.refresh(u_old)
    fk_session.refresh(u_new)

    cust = Customer(
        customer_code="C-HIST", customer_name="历史客户",
        customer_status="prospect", is_deleted=False,
        sales_user_id=None,  # already unassigned (soft-deleted scenario)
    )
    fk_session.add(cust); fk_session.commit(); fk_session.refresh(cust)

    # Historical log: customer was once assigned to u_old, then moved to u_new.
    log_hist = LeadAssignmentLog(
        customer_id=cust.id,
        from_user_id=None, to_user_id=u_old.id,
        reason="最初分配", trigger="manual",
    )
    log_move = LeadAssignmentLog(
        customer_id=cust.id,
        from_user_id=u_old.id, to_user_id=u_new.id,
        reason="转交", trigger="manual",
    )
    fk_session.add_all([log_hist, log_move])
    fk_session.commit()

    # Act: hard-delete u_old. Without the fix this returns 500 because
    # log_hist.to_user_id and log_move.from_user_id still reference u_old.
    r = client.delete(f"/api/sales/users/{u_old.id}/hard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["deleted_user_id"] == u_old.id
    # No live customers assigned → no recycle logs created
    assert body["customers_recycled"] == 0
    # Two historical log references nullified: log_hist.to + log_move.from
    assert body["logs_nullified"] == 2

    # sales_user row is gone
    fk_session.expire_all()
    assert fk_session.query(SalesUser).get(u_old.id) is None

    # Historical log rows preserved, FKs NULL'd
    rows = fk_session.query(LeadAssignmentLog).order_by(LeadAssignmentLog.id).all()
    assert len(rows) == 2
    # log_hist: to_user_id was u_old → NULL. from was already NULL.
    assert rows[0].from_user_id is None
    assert rows[0].to_user_id is None
    # log_move: from_user_id was u_old → NULL. to_user_id (u_new) untouched.
    assert rows[1].from_user_id is None
    assert rows[1].to_user_id == u_new.id


def test_hard_delete_with_active_customer_and_history_together(client, fk_session):
    """Mixed case: user has live customers to recycle AND historical logs.
    Both paths must work together without tripping the FK.
    """
    u = SalesUser(name="李四", is_active=True)
    fk_session.add(u); fk_session.commit(); fk_session.refresh(u)

    # Active customer currently assigned to u
    live_c = Customer(
        customer_code="C-LIVE", customer_name="活跃客户",
        customer_status="active", is_deleted=False, sales_user_id=u.id,
    )
    fk_session.add(live_c); fk_session.commit(); fk_session.refresh(live_c)

    # Old history: customer was assigned to u long ago
    old_c = Customer(
        customer_code="C-OLD", customer_name="老客户",
        customer_status="lost", is_deleted=False, sales_user_id=None,
    )
    fk_session.add(old_c); fk_session.commit(); fk_session.refresh(old_c)

    old_log = LeadAssignmentLog(
        customer_id=old_c.id, from_user_id=None, to_user_id=u.id,
        reason="老分配", trigger="manual",
    )
    fk_session.add(old_log); fk_session.commit()

    r = client.delete(f"/api/sales/users/{u.id}/hard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["customers_recycled"] == 1          # live_c recycled
    # Nullified rows: the historical row's to_user_id, PLUS the recycle-log
    # row we just wrote (from_user_id=u.id). So ≥ 2.
    assert body["logs_nullified"] >= 2

    fk_session.expire_all()
    # sales_user deletion succeeded
    assert fk_session.query(SalesUser).get(u.id) is None
    # Live customer back in the pool
    assert fk_session.query(Customer).get(live_c.id).sales_user_id is None
    # No row still references the deleted user
    remaining = fk_session.query(LeadAssignmentLog).filter(
        (LeadAssignmentLog.from_user_id == u.id)
        | (LeadAssignmentLog.to_user_id == u.id)
    ).count()
    assert remaining == 0
