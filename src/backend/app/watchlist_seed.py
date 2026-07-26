"""Starter watchlists for freshly created accounts.

Lives in its own module so both the account-creation paths (`auth_routes`,
`auth.ensure_initial_admin`) and `main` can seed without an import cycle.

Seeding happens exactly once, at account creation. It deliberately does NOT run
from the read path: a user who deletes their starter lists must keep them
deleted instead of having them resurrected on the next page load.
"""

import uuid

from sqlalchemy.orm import Session

from .models import User, Watchlist as WatchlistRecord, WatchlistItem as WatchlistItemRecord

# (list name, ((symbol, display name), ...))
DEFAULT_WATCHLIST_SEED: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Tech Giants",
        (
            ("NVDA", "NVIDIA Corp"),
            ("AAPL", "Apple Inc"),
            ("MSFT", "Microsoft Corp"),
            ("GOOGL", "Alphabet Inc"),
        ),
    ),
    (
        "Crypto Proxies",
        (
            ("COIN", "Coinbase Global"),
            ("MSTR", "MicroStrategy"),
            ("MARA", "Marathon Digital"),
        ),
    ),
)


def seed_default_watchlists(db: Session, user: User) -> None:
    """Create the starter watchlists for a brand new account.

    No-op when the user already owns watchlists, so calling it twice for the
    same account (e.g. bootstrap admin promoted on a later start) is safe.
    """
    existing = db.query(WatchlistRecord).filter(WatchlistRecord.user_id == user.id).count()
    if existing:
        return

    for name, items in DEFAULT_WATCHLIST_SEED:
        record = WatchlistRecord(
            id=str(uuid.uuid4())[:8],
            user_id=user.id,
            name=name,
            is_default=True,
        )
        record.items = [
            WatchlistItemRecord(symbol=symbol, name=item_name)
            for symbol, item_name in items
        ]
        db.add(record)
    db.commit()
