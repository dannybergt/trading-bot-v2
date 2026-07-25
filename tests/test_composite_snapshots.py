"""Composite forward-collection tests (roadmap 2d-3).

Covers snapshot writing (dedup per symbol/day, completeness preference,
labeled-row protection), forward-return labeling, and the readiness summary.
"""
import os
import unittest
from datetime import date, datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import composite_snapshots
from app.database import Base
from app.models import CompositeSnapshot, User  # noqa: F401 — register models


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return Session()


def _composite(score=0.3, verdict="BUY", **axes):
    return {
        "score": score,
        "verdict": verdict,
        "breakdown": [
            {"axis": axis, "value": axes.get(axis), "available": axes.get(axis) is not None}
            for axis in ("technical", "analyst", "fundamentals", "news")
        ],
    }


class _FakeService:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_yfinance_history_df(self, symbol, *, period="3mo", interval="1d"):
        return self._df


class WriteSnapshotTests(unittest.TestCase):
    def test_inserts_one_row_and_captures_axes(self):
        db = _make_session()
        ok = composite_snapshots.write_snapshot(
            db, "aapl", 100.0, _composite(technical=0.4, analyst=0.2, fundamentals=0.1, news=-0.3)
        )
        self.assertTrue(ok)
        row = db.query(CompositeSnapshot).one()
        self.assertEqual(row.symbol, "AAPL")
        self.assertEqual(row.close, 100.0)
        self.assertEqual(row.axis_technical, 0.4)
        self.assertEqual(row.axis_news, -0.3)
        self.assertEqual(row.horizon_days, composite_snapshots.HORIZON_DAYS)
        self.assertIsNone(row.realized_up)

    def test_dedup_per_symbol_day(self):
        db = _make_session()
        composite_snapshots.write_snapshot(db, "AAPL", 100.0, _composite(technical=0.2))
        composite_snapshots.write_snapshot(db, "AAPL", 101.0, _composite(technical=0.2))
        self.assertEqual(db.query(CompositeSnapshot).count(), 1)

    def test_fuller_axes_overwrite_but_poorer_does_not(self):
        db = _make_session()
        # First a technical-only (background-style) snapshot.
        composite_snapshots.write_snapshot(db, "AAPL", 100.0, _composite(technical=0.2))
        # A full-axis (user-style) visit same day should overwrite.
        composite_snapshots.write_snapshot(
            db, "AAPL", 105.0, _composite(technical=0.3, analyst=0.1, fundamentals=0.2, news=0.0)
        )
        row = db.query(CompositeSnapshot).one()
        self.assertEqual(row.close, 105.0)
        self.assertEqual(row.axis_analyst, 0.1)
        # A later technical-only refresh must NOT clobber the fuller row.
        composite_snapshots.write_snapshot(db, "AAPL", 99.0, _composite(technical=0.9))
        row = db.query(CompositeSnapshot).one()
        self.assertEqual(row.close, 105.0)
        self.assertEqual(row.axis_analyst, 0.1)

    def test_does_not_overwrite_labeled_row(self):
        db = _make_session()
        composite_snapshots.write_snapshot(db, "AAPL", 100.0, _composite(technical=0.2))
        row = db.query(CompositeSnapshot).one()
        row.realized_up = True
        db.commit()
        changed = composite_snapshots.write_snapshot(
            db, "AAPL", 200.0, _composite(technical=0.3, analyst=0.3, fundamentals=0.3, news=0.3)
        )
        self.assertFalse(changed)
        self.assertEqual(db.query(CompositeSnapshot).one().close, 100.0)

    def test_rejects_bad_input(self):
        db = _make_session()
        self.assertFalse(composite_snapshots.write_snapshot(db, "AAPL", 100.0, None))
        self.assertFalse(composite_snapshots.write_snapshot(db, "AAPL", "x", _composite(technical=0.2)))
        self.assertFalse(composite_snapshots.write_snapshot(db, "AAPL", 0.0, _composite(technical=0.2)))
        self.assertFalse(
            composite_snapshots.write_snapshot(db, "AAPL", 100.0, {"verdict": "BUY", "breakdown": []})
        )
        self.assertEqual(db.query(CompositeSnapshot).count(), 0)


class LabelDueSnapshotsTests(unittest.TestCase):
    def _seed(self, db, *, days_ago, close, symbol="AAPL"):
        row = CompositeSnapshot(
            symbol=symbol,
            snapshot_date=date.today() - timedelta(days=days_ago),
            close=close,
            score=0.2,
            verdict="BUY",
            horizon_days=7,
            axis_technical=0.2,
        )
        db.add(row)
        db.commit()
        return row

    def test_labels_matured_snapshot_up(self):
        db = _make_session()
        self._seed(db, days_ago=10, close=100.0)
        target = date.today() - timedelta(days=3)
        df = pd.DataFrame(
            {"Close": [110.0, 111.0]},
            index=pd.to_datetime([target, target + timedelta(days=1)]),
        )
        n = composite_snapshots.label_due_snapshots(db, _FakeService(df))
        self.assertEqual(n, 1)
        row = db.query(CompositeSnapshot).one()
        self.assertTrue(row.realized_up)
        self.assertAlmostEqual(row.forward_close, 110.0, places=6)
        self.assertAlmostEqual(row.forward_return_pct, 10.0, places=4)
        self.assertIsNotNone(row.labeled_at)

    def test_labels_matured_snapshot_down(self):
        db = _make_session()
        self._seed(db, days_ago=10, close=100.0)
        target = date.today() - timedelta(days=3)
        df = pd.DataFrame({"Close": [90.0]}, index=pd.to_datetime([target]))
        composite_snapshots.label_due_snapshots(db, _FakeService(df))
        row = db.query(CompositeSnapshot).one()
        self.assertFalse(row.realized_up)
        self.assertAlmostEqual(row.forward_return_pct, -10.0, places=4)

    def test_skips_immature_snapshot(self):
        db = _make_session()
        self._seed(db, days_ago=2, close=100.0)  # horizon 7 not elapsed
        df = pd.DataFrame({"Close": [110.0]}, index=pd.to_datetime([date.today()]))
        n = composite_snapshots.label_due_snapshots(db, _FakeService(df))
        self.assertEqual(n, 0)
        self.assertIsNone(db.query(CompositeSnapshot).one().realized_up)

    def test_skips_when_no_forward_bar(self):
        db = _make_session()
        self._seed(db, days_ago=10, close=100.0)
        n = composite_snapshots.label_due_snapshots(db, _FakeService(pd.DataFrame()))
        self.assertEqual(n, 0)


class ReadinessTests(unittest.TestCase):
    def test_counts_and_ready_flag(self):
        db = _make_session()
        # One fully-labeled full-axis row.
        db.add(
            CompositeSnapshot(
                symbol="AAPL", snapshot_date=date.today() - timedelta(days=10), close=100.0,
                score=0.2, verdict="BUY", horizon_days=7, axis_technical=0.2, axis_analyst=0.1,
                axis_fundamentals=0.1, axis_news=0.0, forward_close=110.0, forward_return_pct=10.0,
                realized_up=True, labeled_at=datetime.now(timezone.utc),
            )
        )
        # One labeled but technical-only (not full-axis).
        db.add(
            CompositeSnapshot(
                symbol="MSFT", snapshot_date=date.today() - timedelta(days=9), close=50.0,
                score=0.1, verdict="HOLD", horizon_days=7, axis_technical=0.1,
                forward_close=49.0, realized_up=False, labeled_at=datetime.now(timezone.utc),
            )
        )
        # One unlabeled.
        db.add(
            CompositeSnapshot(
                symbol="TSLA", snapshot_date=date.today(), close=200.0, score=0.0,
                verdict="HOLD", horizon_days=7, axis_technical=0.0,
            )
        )
        db.commit()
        out = composite_snapshots.readiness(db)
        self.assertEqual(out["total"], 3)
        self.assertEqual(out["labeled"], 2)
        self.assertEqual(out["fullAxisLabeled"], 1)
        self.assertFalse(out["ready"])
        self.assertEqual(out["threshold"], composite_snapshots.READY_THRESHOLD)
        self.assertEqual(out["horizonDays"], 7)


if __name__ == "__main__":
    unittest.main()
