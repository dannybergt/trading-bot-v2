"""Unit tests for the paper-trading order lifecycle.

Drives the service against an in-memory SQLite database with a stub price
provider so the fill simulator and Net-Yield-Gate can be exercised without
touching MarketDataService.
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import PaperOrder, PaperTransaction, User
from app import paper_trading


def _make_user(
    *,
    fee_absolute: int = 0,
    fee_percent: int = 0,
    min_target_yield: int = 0,
    capital_gains_tax_bps: int = 0,
    income_tax_bps: int = 0,
):
    return User(
        email="trader@example.com",
        hashed_password="x",
        is_active=True,
        is_admin=False,
        trade_fee_absolute=fee_absolute,
        trade_fee_percent=fee_percent,
        min_target_yield=min_target_yield,
        capital_gains_tax_bps=capital_gains_tax_bps,
        income_tax_bps=income_tax_bps,
    )


class PaperTradingServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = Session()
        user = _make_user()
        self.db.add(user)
        self.db.commit()
        self.user = self.db.query(User).first()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _provider(self, price: float | None):
        return lambda symbol: price

    def test_market_buy_fills_immediately_with_adverse_slippage(self):
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="aapl",
            side="buy",
            qty=10,
            limit_price=None,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
        )
        self.assertEqual(order.status, "filled")
        self.assertEqual(order.symbol, "AAPL")
        tx = self.db.query(PaperTransaction).filter_by(order_id=order.id).one()
        # Adverse slippage of 0.1% against the buyer
        self.assertAlmostEqual(tx.price, 100.0 * 1.001, places=6)
        self.assertEqual(tx.qty, 10)
        self.assertEqual(tx.side, "buy")
        self.assertAlmostEqual(tx.realized_pnl, 0.0)

    def test_limit_buy_above_market_stays_pending(self):
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="MSFT",
            side="buy",
            qty=5,
            limit_price=90.0,  # market is at 100, we won't pay 100 with a 90 limit
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
        )
        self.assertEqual(order.status, "pending")
        self.assertEqual(self.db.query(PaperTransaction).count(), 0)

    def test_limit_buy_below_market_fills_at_limit(self):
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="MSFT",
            side="buy",
            qty=5,
            limit_price=120.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
        )
        self.assertEqual(order.status, "filled")
        tx = self.db.query(PaperTransaction).filter_by(order_id=order.id).one()
        self.assertEqual(tx.price, 120.0)

    def test_realized_pnl_subtracts_fees_and_capital_gains_tax(self):
        # Configure fees + 25% capital-gains tax on realized profit
        self.user.trade_fee_absolute = 1
        self.user.trade_fee_percent = 0
        self.user.capital_gains_tax_bps = 2500  # 25.00%
        self.db.commit()

        paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="NVDA",
            side="buy",
            qty=10,
            limit_price=100.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
        )
        sell = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="NVDA",
            side="sell",
            qty=10,
            limit_price=110.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(110.0),
        )
        sell_tx = (
            self.db.query(PaperTransaction)
            .filter_by(order_id=sell.id)
            .one()
        )
        # gross = (110 - 100) * 10 = 100
        # tax = 100 * 0.25 = 25 ; fee_absolute on the sell leg = 1
        # realized_pnl = 100 - 1 (fee) - 25 (tax) = 74
        self.assertAlmostEqual(sell_tx.tax_amount, 25.0, places=4)
        self.assertAlmostEqual(sell_tx.fee_absolute, 1.0, places=4)
        self.assertAlmostEqual(sell_tx.realized_pnl, 74.0, places=4)

    def test_net_yield_gate_rejects_target_below_minimum(self):
        # Net yield must clear 5% AFTER 1% per-leg fee and 25% tax on gross gains
        self.user.min_target_yield = 5
        self.user.trade_fee_percent = 1
        self.user.capital_gains_tax_bps = 2500
        self.db.commit()

        with self.assertRaises(paper_trading.NetYieldGateRejection) as ctx:
            paper_trading.place_order(
                db=self.db,
                user=self.user,
                symbol="AMZN",
                side="buy",
                qty=1,
                limit_price=100.0,
                target_price=104.0,  # gross 4% — below minimum even before fees
                source="auto-recommendation",
                latest_close_provider=self._provider(100.0),
            )
        self.assertEqual(ctx.exception.reason, "net_target_below_minimum")
        self.assertFalse(ctx.exception.breakdown["meetsMinimum"])
        # Nothing was persisted
        self.assertEqual(self.db.query(PaperOrder).count(), 0)

    def test_net_yield_gate_accepts_when_target_clears_minimum(self):
        self.user.min_target_yield = 1
        self.db.commit()
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="AMZN",
            side="buy",
            qty=1,
            limit_price=100.0,
            target_price=110.0,  # 10% gross — well above minimum
            source="auto-recommendation",
            latest_close_provider=self._provider(100.0),
        )
        self.assertEqual(order.status, "filled")

    def test_journal_lists_transactions_chronologically_with_pnl_pct(self):
        # Buy 10 @ 100, sell 5 @ 120
        paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="GOOG",
            side="buy",
            qty=10,
            limit_price=100.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
        )
        paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="GOOG",
            side="sell",
            qty=5,
            limit_price=120.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(120.0),
        )
        journal = paper_trading.list_transactions(self.db, self.user)
        self.assertEqual(len(journal), 2)
        self.assertEqual(journal[0]["side"], "buy")
        self.assertEqual(journal[1]["side"], "sell")
        # cost basis for the sell leg = 5 * 100 = 500
        # realized = (120 - 100) * 5 = 100, no fees, no tax → 100
        # pnl% = 100 / 500 * 100 = 20.0
        self.assertAlmostEqual(journal[1]["realizedPnlPct"], 20.0, places=4)

    def test_compute_positions_aggregates_open_qty_and_unrealized(self):
        paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="TSLA",
            side="buy",
            qty=4,
            limit_price=200.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(200.0),
        )
        positions = paper_trading.compute_positions(
            self.db, self.user, self._provider(220.0)
        )
        self.assertEqual(len(positions), 1)
        pos = positions[0]
        self.assertEqual(pos["symbol"], "TSLA")
        self.assertEqual(pos["qty"], 4)
        self.assertAlmostEqual(pos["avgEntryPrice"], 200.0, places=4)
        self.assertAlmostEqual(pos["unrealizedPnl"], 80.0, places=4)
        self.assertAlmostEqual(pos["unrealizedPnlPct"], 10.0, places=4)

    def test_cancel_pending_order(self):
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="META",
            side="buy",
            qty=1,
            limit_price=10.0,  # well below market → stays pending
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
        )
        self.assertEqual(order.status, "pending")
        cancelled = paper_trading.cancel_order(
            db=self.db, user=self.user, order_id=order.id
        )
        self.assertEqual(cancelled.status, "cancelled")

    def test_dispatch_pending_orders_fills_when_market_crosses_limit(self):
        # Place a buy at 90 while market is 100 -> stays pending
        paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="DISPATCH",
            side="buy",
            qty=2,
            limit_price=90.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
        )
        # Now market drops to 85 -> dispatch should fill at the resting limit
        filled = paper_trading.dispatch_pending_orders(self.db, self._provider(85.0))
        self.assertEqual(filled, 1)
        order = self.db.query(PaperOrder).filter_by(symbol="DISPATCH").one()
        self.assertEqual(order.status, "filled")
        tx = self.db.query(PaperTransaction).filter_by(order_id=order.id).one()
        # Limit fills cannot be better than the resting limit price
        self.assertEqual(tx.price, 90.0)

    def test_market_buy_uses_crypto_slippage_when_asset_class_resolved(self):
        # Crypto carries a 0.3% adverse slippage instead of the 0.1% default
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="BTC/USD",
            side="buy",
            qty=1,
            limit_price=None,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(50_000.0),
            asset_class_resolver=lambda _s: "crypto",
        )
        tx = self.db.query(PaperTransaction).filter_by(order_id=order.id).one()
        # 50000 * (1 + 0.003) = 50150
        self.assertAlmostEqual(tx.price, 50_150.0, places=2)

    def test_dynamic_slippage_scales_with_position_size(self):
        # qty equal to 10% of avg daily volume → multiplier (1 + 0.1) = 1.1
        # base stock slippage 0.1% → effective 0.11%
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="VOL",
            side="buy",
            qty=100,
            limit_price=None,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(50.0),
            asset_class_resolver=lambda _s: "stock",
            avg_daily_volume_provider=lambda _s: 1000,
        )
        tx = self.db.query(PaperTransaction).filter_by(order_id=order.id).one()
        # 50 * (1 + 0.0011) = 50.055
        self.assertAlmostEqual(tx.price, 50.055, places=4)

    def test_dynamic_slippage_caps_at_max_for_oversized_orders(self):
        # qty 10x avg daily volume would push slippage way past the cap;
        # we want it to clamp at 1.0% so a single big paper order can't
        # destroy its own P&L.
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="HUGE",
            side="buy",
            qty=10_000,
            limit_price=None,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
            asset_class_resolver=lambda _s: "stock",
            avg_daily_volume_provider=lambda _s: 100,
        )
        tx = self.db.query(PaperTransaction).filter_by(order_id=order.id).one()
        # capped at MAX_SLIPPAGE_PCT (1.0%) → 100 * 1.01 = 101
        self.assertAlmostEqual(tx.price, 101.0, places=4)

    def test_crypto_fee_multiplier_scales_user_fees(self):
        # User pays 1.0% fee per leg; crypto multiplier is 5x → 5%
        self.user.trade_fee_absolute = 0
        self.user.trade_fee_percent = 1
        self.db.commit()

        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="BTC/USD",
            side="buy",
            qty=1,
            limit_price=100.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
            asset_class_resolver=lambda _s: "crypto",
        )
        tx = self.db.query(PaperTransaction).filter_by(order_id=order.id).one()
        # 1 * 100 * 5% = 5
        self.assertAlmostEqual(tx.fee_percent_amount, 5.0, places=4)

    def test_stock_fee_multiplier_unchanged(self):
        self.user.trade_fee_absolute = 0
        self.user.trade_fee_percent = 1
        self.db.commit()

        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="AAPL",
            side="buy",
            qty=1,
            limit_price=100.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
            asset_class_resolver=lambda _s: "stock",
        )
        tx = self.db.query(PaperTransaction).filter_by(order_id=order.id).one()
        # Stock multiplier is 1.0 → 1 * 100 * 1% = 1
        self.assertAlmostEqual(tx.fee_percent_amount, 1.0, places=4)

    def test_market_buy_uses_etf_slippage_when_asset_class_resolved(self):
        # ETFs are tighter (0.05%) than the default
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="VOO",
            side="buy",
            qty=1,
            limit_price=None,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(400.0),
            asset_class_resolver=lambda _s: "etf",
        )
        tx = self.db.query(PaperTransaction).filter_by(order_id=order.id).one()
        # 400 * (1 + 0.0005) = 400.20
        self.assertAlmostEqual(tx.price, 400.20, places=2)

    def test_dispatch_pending_orders_skips_when_no_price(self):
        paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="NOPRICE",
            side="buy",
            qty=1,
            limit_price=50.0,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(None),
        )
        filled = paper_trading.dispatch_pending_orders(self.db, self._provider(None))
        self.assertEqual(filled, 0)
        order = self.db.query(PaperOrder).filter_by(symbol="NOPRICE").one()
        self.assertEqual(order.status, "pending")

    def test_cancel_filled_order_rejected(self):
        order = paper_trading.place_order(
            db=self.db,
            user=self.user,
            symbol="META",
            side="buy",
            qty=1,
            limit_price=None,
            target_price=None,
            source="manual",
            latest_close_provider=self._provider(100.0),
        )
        self.assertEqual(order.status, "filled")
        with self.assertRaises(ValueError):
            paper_trading.cancel_order(
                db=self.db, user=self.user, order_id=order.id
            )


if __name__ == "__main__":
    unittest.main()
