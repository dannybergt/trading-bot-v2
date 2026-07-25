"""Composite-weights configuration tests.

Covers the operator-configurable axis weights:
  * validate_weights normalisation + rejection of bad input
  * set/get_stored round-trip against a DB session
  * invalid stored JSON degrades to None (caller falls back to default)
  * get_weights() degrades to DEFAULT_WEIGHTS when no override is readable
"""
import json
import os
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import composite_weights
from app.composite_score import AXES, DEFAULT_WEIGHTS
from app.database import Base
from app.models import CompositeWeightConfiguration, User  # noqa: F401 — register models


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return Session()


class CompositeWeightsValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        composite_weights.invalidate()

    def test_validate_normalises_to_sum_one(self):
        out = composite_weights.validate_weights(
            {"technical": 2, "analyst": 1, "fundamentals": 1, "news": 0}
        )
        self.assertAlmostEqual(sum(out.values()), 1.0, places=9)
        self.assertAlmostEqual(out["technical"], 0.5, places=9)
        self.assertAlmostEqual(out["news"], 0.0, places=9)
        self.assertEqual(set(out), set(AXES))

    def test_validate_rejects_missing_axis(self):
        with self.assertRaises(ValueError):
            composite_weights.validate_weights({"technical": 1, "analyst": 1, "fundamentals": 1})

    def test_validate_rejects_unknown_axis(self):
        with self.assertRaises(ValueError):
            composite_weights.validate_weights(
                {"technical": 1, "analyst": 1, "fundamentals": 1, "news": 1, "macro": 1}
            )

    def test_validate_rejects_negative_and_nonnumber(self):
        with self.assertRaises(ValueError):
            composite_weights.validate_weights(
                {"technical": -1, "analyst": 1, "fundamentals": 1, "news": 1}
            )
        with self.assertRaises(ValueError):
            composite_weights.validate_weights(
                {"technical": "x", "analyst": 1, "fundamentals": 1, "news": 1}
            )
        # bool must not slip through as int
        with self.assertRaises(ValueError):
            composite_weights.validate_weights(
                {"technical": True, "analyst": 1, "fundamentals": 1, "news": 1}
            )

    def test_validate_rejects_all_zero_and_nondict(self):
        with self.assertRaises(ValueError):
            composite_weights.validate_weights(
                {"technical": 0, "analyst": 0, "fundamentals": 0, "news": 0}
            )
        with self.assertRaises(ValueError):
            composite_weights.validate_weights([0.4, 0.25, 0.2, 0.15])


class CompositeWeightsPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        composite_weights.invalidate()

    def test_set_then_get_stored_roundtrip(self):
        db = _make_session()
        stored = composite_weights.set_weights(
            db,
            {"technical": 0.5, "analyst": 0.2, "fundamentals": 0.2, "news": 0.1},
            updated_by_user_id=None,
        )
        db.commit()
        self.assertAlmostEqual(stored["technical"], 0.5, places=9)
        got = composite_weights.get_stored(db)
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got["technical"], 0.5, places=9)
        self.assertAlmostEqual(sum(got.values()), 1.0, places=9)

    def test_set_updates_singleton_not_appends(self):
        db = _make_session()
        composite_weights.set_weights(
            db, {"technical": 1, "analyst": 1, "fundamentals": 1, "news": 1}, updated_by_user_id=None
        )
        db.commit()
        composite_weights.set_weights(
            db, {"technical": 4, "analyst": 1, "fundamentals": 1, "news": 0}, updated_by_user_id=None
        )
        db.commit()
        self.assertEqual(db.query(CompositeWeightConfiguration).count(), 1)
        got = composite_weights.get_stored(db)
        self.assertAlmostEqual(got["technical"], 4 / 6, places=9)

    def test_get_stored_none_when_unset(self):
        db = _make_session()
        self.assertIsNone(composite_weights.get_stored(db))

    def test_invalid_stored_json_degrades_to_none(self):
        db = _make_session()
        db.add(CompositeWeightConfiguration(id=1, weights_json="{not json"))
        db.commit()
        self.assertIsNone(composite_weights.get_stored(db))
        # A structurally-valid-but-incomplete payload is also rejected.
        db.query(CompositeWeightConfiguration).delete()
        db.add(
            CompositeWeightConfiguration(id=1, weights_json=json.dumps({"technical": 1.0}))
        )
        db.commit()
        self.assertIsNone(composite_weights.get_stored(db))

    def test_get_weights_falls_back_to_default(self):
        # No override readable in the unit-test environment → DEFAULT_WEIGHTS.
        composite_weights.invalidate()
        weights = composite_weights.get_weights()
        self.assertEqual(set(weights), set(AXES))
        self.assertEqual(weights, dict(DEFAULT_WEIGHTS))


if __name__ == "__main__":
    unittest.main()
