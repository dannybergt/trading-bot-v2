"""Auto-execution risk-model tests.

Drives `evaluate_proposal`, `update_limits`, `halt_all_for_user` against
an in-memory SQLite so the real SQLAlchemy round-trip is exercised.
External-data inputs (FRED, FMP SEC-Filings, sector context) are passed
in by the test rather than fetched, which is exactly the seam the live
endpoint relies on too.
"""
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "12345678901234567890123456789012")
os.environ.setdefault("APP_ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwx12345678")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import auto_execution
from app.database import Base
from app.models import (
    AutoExecutionEvent,
    AutoExecutionLimits,
    PaperOrder,
    PaperTransaction,
    User,
)


class AutoExecutionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db = Session()
        self.user = User(
            email="alice@example.com",
            hashed_password="x",
            is_active=True,
            min_target_yield=1,
            trade_fee_absolute=0,
            trade_fee_percent=0,
            capital_gains_tax_bps=0,
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _enable_with_defaults(self, **overrides):
        payload = {
            "enabled": True,
            "maxPositionSizeUsd": 1000.0,
            "maxDailyLossUsd": 200.0,
            "maxOpenPositions": 5,
            "maxPortfolioBeta": 2.0,
            "allowedAssetClasses": ["stock", "etf"],
            **overrides,
        }
        return auto_execution.update_limits(self.db, self.user, payload)

    def test_default_limits_are_disabled(self):
        row = auto_execution.get_limits(self.db, self.user)
        self.assertFalse(row.enabled)
        self.assertEqual(row.allowed_asset_classes, "")
        self.assertEqual(500.0, float(row.max_position_size_usd))

    def test_disabled_master_switch_blocks_proposal(self):
        proposal = {"symbol": "AAPL", "side": "buy", "qty": 1, "limitPrice": 150, "assetClass": "stock"}
        decision = auto_execution.evaluate_proposal(self.db, self.user, proposal)
        self.assertFalse(decision.allowed)
        self.assertIn("auto_execution_disabled", decision.reasons)

    def test_allowed_proposal_passes_every_gate(self):
        self._enable_with_defaults()
        proposal = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 1,
            "limitPrice": 150,
            "assetClass": "stock",
            "proposalId": "p-1",
        }
        decision = auto_execution.evaluate_proposal(self.db, self.user, proposal)
        self.assertTrue(decision.allowed, decision.reasons)
        self.assertEqual([], decision.reasons)
        # Audit row was written
        events = self.db.query(AutoExecutionEvent).all()
        self.assertEqual(1, len(events))
        self.assertEqual("accepted", events[0].status)

    def test_position_size_cap_rejects_oversized_order(self):
        self._enable_with_defaults(maxPositionSizeUsd=500.0)
        proposal = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10,
            "limitPrice": 200,  # 2000 > 500 cap
            "assetClass": "stock",
        }
        decision = auto_execution.evaluate_proposal(self.db, self.user, proposal)
        self.assertFalse(decision.allowed)
        self.assertIn("position_size_exceeds_limit", decision.reasons)

    def test_asset_class_allowlist(self):
        self._enable_with_defaults(allowedAssetClasses=["stock"])
        proposal = {"symbol": "BTC", "side": "buy", "qty": 1, "limitPrice": 50000, "assetClass": "crypto"}
        decision = auto_execution.evaluate_proposal(self.db, self.user, proposal)
        self.assertIn("asset_class_not_allowed", decision.reasons)

    def test_open_position_cap(self):
        self._enable_with_defaults(maxOpenPositions=2)
        # Seed two open paper orders so the next proposal hits the cap
        for _ in range(2):
            self.db.add(
                PaperOrder(
                    user_id=self.user.id,
                    symbol="AAPL",
                    side="buy",
                    qty=1,
                    status="pending",
                    source="manual",
                )
            )
        self.db.commit()
        proposal = {"symbol": "MSFT", "side": "buy", "qty": 1, "limitPrice": 100, "assetClass": "stock"}
        decision = auto_execution.evaluate_proposal(self.db, self.user, proposal)
        self.assertIn("open_position_cap_reached", decision.reasons)

    def test_daily_loss_budget_exhausted(self):
        self._enable_with_defaults(maxDailyLossUsd=100.0)
        # Seed a paper order + transaction with realized_pnl that crosses the cap
        order = PaperOrder(user_id=self.user.id, symbol="AAPL", side="sell", qty=1, status="filled", source="manual")
        self.db.add(order)
        self.db.commit()
        self.db.add(
            PaperTransaction(
                user_id=self.user.id,
                order_id=order.id,
                symbol="AAPL",
                side="sell",
                qty=1,
                price=100,
                realized_pnl=-150.0,
            )
        )
        self.db.commit()
        proposal = {"symbol": "MSFT", "side": "buy", "qty": 1, "limitPrice": 50, "assetClass": "stock"}
        decision = auto_execution.evaluate_proposal(self.db, self.user, proposal)
        self.assertIn("daily_loss_budget_exhausted", decision.reasons)

    def test_halt_recent_8k_filing(self):
        self._enable_with_defaults()
        sec_filings = {"lastMaterial": {"daysAgo": 2, "type": "8-K"}}
        proposal = {"symbol": "AAPL", "side": "buy", "qty": 1, "limitPrice": 100, "assetClass": "stock"}
        decision = auto_execution.evaluate_proposal(
            self.db, self.user, proposal, sec_filings=sec_filings
        )
        self.assertIn("halt_recent_8k_material_event", decision.reasons)
        self.assertIn("halt_recent_8k_material_event", decision.halt_triggers)

    def test_halt_yield_curve_inverted_only_for_stocks_etfs(self):
        self._enable_with_defaults(allowedAssetClasses=["stock", "etf", "crypto"])
        fred_calendar = {"treasury": {"spreadInverted": True}, "upcomingReleases": []}
        # Stock: inversion fires
        decision_stock = auto_execution.evaluate_proposal(
            self.db,
            self.user,
            {"symbol": "AAPL", "side": "buy", "qty": 1, "limitPrice": 100, "assetClass": "stock"},
            fred_calendar=fred_calendar,
        )
        self.assertIn("halt_yield_curve_inverted", decision_stock.reasons)
        # Crypto: inversion does NOT fire
        decision_crypto = auto_execution.evaluate_proposal(
            self.db,
            self.user,
            {"symbol": "BTC", "side": "buy", "qty": 0.01, "limitPrice": 50000, "assetClass": "crypto"},
            fred_calendar=fred_calendar,
        )
        self.assertNotIn("halt_yield_curve_inverted", decision_crypto.reasons)

    def test_halt_fomc_within_24h(self):
        self._enable_with_defaults()
        fred_calendar = {
            "treasury": {"spreadInverted": False},
            "upcomingReleases": [
                {"category": "policy", "name": "FOMC", "daysUntil": 0, "date": "2026-05-08"},
            ],
        }
        decision = auto_execution.evaluate_proposal(
            self.db,
            self.user,
            {"symbol": "AAPL", "side": "buy", "qty": 1, "limitPrice": 100, "assetClass": "stock"},
            fred_calendar=fred_calendar,
        )
        self.assertIn("halt_fomc_within_24h", decision.reasons)

    def test_halt_symbol_beta_exceeds_limit(self):
        self._enable_with_defaults(maxPortfolioBeta=1.5)
        sector_context = {"correlation": {"beta": 2.7}}
        decision = auto_execution.evaluate_proposal(
            self.db,
            self.user,
            {"symbol": "TSLA", "side": "buy", "qty": 1, "limitPrice": 100, "assetClass": "stock"},
            sector_context=sector_context,
        )
        self.assertIn("halt_symbol_beta_exceeds_limit", decision.reasons)

    def test_net_yield_gate_block_propagates(self):
        self._enable_with_defaults()
        decision = auto_execution.evaluate_proposal(
            self.db,
            self.user,
            {"symbol": "AAPL", "side": "buy", "qty": 1, "limitPrice": 100, "assetClass": "stock"},
            net_yield_breakdown={"meetsMinimum": False, "netTargetPct": 0.4, "minTargetYieldPct": 1.0},
        )
        self.assertIn("net_yield_gate_blocked", decision.reasons)

    def test_update_limits_rejects_unknown_asset_classes(self):
        row = auto_execution.update_limits(
            self.db,
            self.user,
            {"enabled": True, "allowedAssetClasses": ["stock", "futures", "crypto"]},
        )
        # "futures" is dropped silently — keeps the policy auditable
        self.assertEqual(row.allowed_asset_classes, "stock,crypto")

    def test_halt_all_flips_master_switch_and_audits(self):
        self._enable_with_defaults()
        self.assertTrue(auto_execution.get_limits(self.db, self.user).enabled)
        canceled = auto_execution.halt_all_for_user(self.db, self.user, reason="test_halt")
        self.assertEqual(0, canceled)
        self.assertFalse(auto_execution.get_limits(self.db, self.user).enabled)
        events = self.db.query(AutoExecutionEvent).filter(AutoExecutionEvent.status == "halted").all()
        self.assertEqual(1, len(events))
        self.assertEqual("test_halt", events[0].reason)

    def test_default_mode_is_paper(self):
        row = auto_execution.get_limits(self.db, self.user)
        self.assertEqual("paper", row.mode)

    def test_live_mode_is_hard_locked_by_default(self):
        # The shipped default has LIVE_MODE_LOCKED=True so live-mode must
        # be silently rejected at the service layer no matter what payload
        # the frontend sent.
        self.assertTrue(auto_execution.LIVE_MODE_LOCKED)
        self.assertFalse(auto_execution.is_live_mode_available())
        row = auto_execution.update_limits(self.db, self.user, {"mode": "live"})
        self.assertEqual("paper", row.mode)
        # Unknown values still fall back to paper.
        row = auto_execution.update_limits(self.db, self.user, {"mode": "fantasy"})
        self.assertEqual("paper", row.mode)

    def test_live_mode_persists_when_lock_is_off(self):
        # Temporarily disable the code-lock for this test, then restore it.
        # This is the only sanctioned way to reach live-mode at the service
        # layer; production code must never flip the constant at runtime.
        original = auto_execution.LIVE_MODE_LOCKED
        auto_execution.LIVE_MODE_LOCKED = False
        try:
            row = auto_execution.update_limits(self.db, self.user, {"mode": "live"})
            self.assertEqual("live", row.mode)
        finally:
            auto_execution.LIVE_MODE_LOCKED = original

    def test_serialize_limits_surfaces_live_mode_availability(self):
        row = auto_execution.get_limits(self.db, self.user)
        payload = auto_execution.serialize_limits(row)
        self.assertIn("liveModeAvailable", payload)
        self.assertEqual(payload["liveModeAvailable"], not auto_execution.LIVE_MODE_LOCKED)

    def test_evaluate_proposal_from_prediction_actionable_passes(self):
        self._enable_with_defaults()
        prediction = {
            "direction": "UP",
            "confidence": 0.75,
            "zones": {"entry": 100.0, "target": 110.0},
        }
        decision, proposal = auto_execution.evaluate_proposal_from_prediction(
            self.db,
            self.user,
            symbol="AAPL",
            asset_class="stock",
            sector="Technology",
            prediction=prediction,
            latest_close=100.0,
        )
        self.assertTrue(decision.allowed, decision.reasons)
        self.assertIsNotNone(proposal)
        self.assertEqual("AAPL", proposal["symbol"])
        self.assertEqual("buy", proposal["side"])
        # qty = floor(maxPositionSize=$1000 / $100) = 10
        self.assertEqual(10.0, proposal["qty"])
        self.assertEqual(100.0, proposal["limitPrice"])
        self.assertEqual(110.0, proposal["targetPrice"])

    def test_evaluate_proposal_from_prediction_blocks_on_low_confidence(self):
        self._enable_with_defaults()
        prediction = {"direction": "UP", "confidence": 0.4, "zones": {"entry": 100.0}}
        decision, proposal = auto_execution.evaluate_proposal_from_prediction(
            self.db,
            self.user,
            symbol="AAPL",
            asset_class="stock",
            sector=None,
            prediction=prediction,
            latest_close=100.0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("prediction_confidence_below_threshold", decision.reasons)
        self.assertIsNone(proposal)

    def test_evaluate_proposal_from_prediction_blocks_on_hold(self):
        self._enable_with_defaults()
        prediction = {"direction": "HOLD", "confidence": 0.95}
        decision, proposal = auto_execution.evaluate_proposal_from_prediction(
            self.db,
            self.user,
            symbol="AAPL",
            asset_class="stock",
            sector=None,
            prediction=prediction,
            latest_close=100.0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("prediction_not_actionable", decision.reasons)
        self.assertIsNone(proposal)

    def test_list_events_returns_newest_first(self):
        self._enable_with_defaults()
        proposal_a = {"symbol": "AAPL", "side": "buy", "qty": 1, "limitPrice": 100, "assetClass": "stock", "proposalId": "p-a"}
        proposal_b = {"symbol": "MSFT", "side": "buy", "qty": 1, "limitPrice": 200, "assetClass": "stock", "proposalId": "p-b"}
        auto_execution.evaluate_proposal(self.db, self.user, proposal_a)
        auto_execution.evaluate_proposal(self.db, self.user, proposal_b)
        rows = auto_execution.list_events(self.db, self.user, limit=10)
        self.assertEqual(2, len(rows))
        self.assertEqual("p-b", rows[0]["proposalId"])
        self.assertEqual("p-a", rows[1]["proposalId"])


if __name__ == "__main__":
    unittest.main()
