"""Starter-watchlist seeding tests.

The seeding used to run from the read path (`GET /api/watchlists`), which
resurrected starter lists a user had deliberately deleted. These tests pin the
contract that replaced it: seed once at account creation, never again.
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, Watchlist as WatchlistRecord
from app.watchlist_seed import DEFAULT_WATCHLIST_SEED, seed_default_watchlists


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return Session()


def _make_user(db, email="seed@example.com"):
    user = User(email=email, hashed_password="x", is_admin=False, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class WatchlistSeedTests(unittest.TestCase):
    def test_seeds_starter_lists_marked_default(self):
        db = _make_session()
        user = _make_user(db)

        seed_default_watchlists(db, user)

        records = db.query(WatchlistRecord).filter(WatchlistRecord.user_id == user.id).all()
        self.assertEqual(len(records), len(DEFAULT_WATCHLIST_SEED))
        self.assertTrue(all(record.is_default for record in records))
        names = {record.name for record in records}
        self.assertEqual(names, {name for name, _ in DEFAULT_WATCHLIST_SEED})
        tech = next(record for record in records if record.name == "Tech Giants")
        self.assertEqual(
            {item.symbol for item in tech.items},
            {"NVDA", "AAPL", "MSFT", "GOOGL"},
        )

    def test_second_call_is_a_noop(self):
        db = _make_session()
        user = _make_user(db)

        seed_default_watchlists(db, user)
        seed_default_watchlists(db, user)

        records = db.query(WatchlistRecord).filter(WatchlistRecord.user_id == user.id).all()
        self.assertEqual(len(records), len(DEFAULT_WATCHLIST_SEED))

    def test_deleted_starter_lists_are_not_resurrected(self):
        """The regression this whole change exists for."""
        db = _make_session()
        user = _make_user(db)
        seed_default_watchlists(db, user)

        for record in db.query(WatchlistRecord).filter(WatchlistRecord.user_id == user.id).all():
            db.delete(record)
        db.commit()

        # A later read must not re-seed. Nothing but account creation calls the
        # seeder, so an explicit re-seed is the only way back — and the user
        # never triggers it.
        remaining = db.query(WatchlistRecord).filter(WatchlistRecord.user_id == user.id).all()
        self.assertEqual(remaining, [])

    def test_seeds_per_user_not_globally(self):
        db = _make_session()
        first = _make_user(db, "first@example.com")
        second = _make_user(db, "second@example.com")

        seed_default_watchlists(db, first)
        seed_default_watchlists(db, second)

        for user in (first, second):
            records = db.query(WatchlistRecord).filter(WatchlistRecord.user_id == user.id).all()
            self.assertEqual(len(records), len(DEFAULT_WATCHLIST_SEED))


if __name__ == "__main__":
    unittest.main()
