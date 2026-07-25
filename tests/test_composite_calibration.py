"""Interim composite-weight calibration tests (roadmap 2d-2).

Covers the grid-search: insufficient-data guard, that a misleading axis gets
down-weighted to beat the current hit-rate, that apply=False never writes, and
that apply=True writes only on improvement.
"""
import os
import unittest
from datetime import date, timedelta

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import composite_calibration, composite_weights
from app.database import Base
from app.models import CompositeSnapshot, CompositeWeightConfiguration, User  # noqa: F401


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return Session()


def _seed_misleading_fundamentals(db, n_pairs=20):
    """Rows where `technical` predicts the outcome and `fundamentals` actively
    misleads. Under the default weights (tech 0.4, fund 0.2) the blend flips the
    verdict the wrong way; zeroing fundamentals recovers a perfect hit-rate."""
    for i in range(n_pairs):
        # Distinct snapshot_date per pair to satisfy the (symbol, date) unique
        # constraint; calibration filters purely on realized_up, not date.
        day = date.today() - timedelta(days=i)
        db.add(
            CompositeSnapshot(
                symbol="UP", snapshot_date=day, close=100.0, score=0.0,
                verdict="HOLD", horizon_days=7,
                axis_technical=0.2, axis_fundamentals=-1.0, realized_up=True,
            )
        )
        db.add(
            CompositeSnapshot(
                symbol="DN", snapshot_date=day, close=100.0, score=0.0,
                verdict="HOLD", horizon_days=7,
                axis_technical=-0.2, axis_fundamentals=1.0, realized_up=False,
            )
        )
    db.commit()


class CalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        composite_weights.invalidate()

    def test_insufficient_data_does_not_apply(self):
        db = _make_session()
        db.add(
            CompositeSnapshot(
                symbol="AAPL", snapshot_date=date.today(), close=100.0, score=0.1,
                verdict="BUY", horizon_days=7, axis_technical=0.3, realized_up=True,
            )
        )
        db.commit()
        report = composite_calibration.calibrate(db, apply=True)
        self.assertFalse(report["applied"])
        self.assertEqual(report["reason"], "insufficient_labeled_data")
        self.assertEqual(db.query(CompositeWeightConfiguration).count(), 0)

    def test_grid_downweights_misleading_axis_and_applies(self):
        db = _make_session()
        _seed_misleading_fundamentals(db, n_pairs=20)  # 40 labeled rows
        report = composite_calibration.calibrate(db, apply=True, updated_by_user_id=None)
        db.commit()  # calibrate writes via set_weights; the caller commits (as the endpoint does)

        self.assertEqual(report["labeled"], 40)
        self.assertIn("technical", report["calibratedAxes"])
        self.assertIn("fundamentals", report["calibratedAxes"])
        # Default weights mispredict every actionable row here.
        self.assertEqual(report["currentHitRate"], 0.0)
        # Grid recovers a strong hit-rate by leaning on technical.
        self.assertGreater(report["bestHitRate"], report["currentHitRate"])
        self.assertTrue(report["improved"])
        self.assertTrue(report["applied"])
        self.assertGreater(
            report["bestWeights"]["technical"], report["bestWeights"]["fundamentals"]
        )
        # It wrote the calibrated set into the Slice-A store.
        self.assertEqual(db.query(CompositeWeightConfiguration).count(), 1)
        stored = composite_weights.get_stored(db)
        self.assertIsNotNone(stored)
        self.assertGreater(stored["technical"], stored["fundamentals"])

    def test_dry_run_reports_but_does_not_write(self):
        db = _make_session()
        _seed_misleading_fundamentals(db, n_pairs=20)
        report = composite_calibration.calibrate(db, apply=False)
        self.assertTrue(report["improved"])
        self.assertFalse(report["applied"])
        self.assertEqual(db.query(CompositeWeightConfiguration).count(), 0)

    def test_score_and_verdict_helpers(self):
        # Only technical present -> score is technical, renormalised.
        self.assertAlmostEqual(
            composite_calibration._score({"technical": 0.5, "analyst": None,
                                          "fundamentals": None, "news": None},
                                         {"technical": 0.4}), 0.5, places=9
        )
        self.assertEqual(composite_calibration._verdict(0.5), "BUY")
        self.assertEqual(composite_calibration._verdict(-0.5), "SELL")
        self.assertEqual(composite_calibration._verdict(0.0), "HOLD")


if __name__ == "__main__":
    unittest.main()
