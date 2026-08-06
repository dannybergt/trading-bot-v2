"""Keine Hintergrundschleife darf ihren Zyklus auf dem Event-Loop fahren.

Der Befund vom 2026-08-06: alle sieben periodischen Schleifen waren
`async def`, fuehrten ihren Zyklus aber vollstaendig blockierend aus —
Provider-HTTP, Datenbank, XGBoost-Training. Ein angehaltener Event-Loop
nimmt keine Anfrage mehr an; gemessen brauchte `/api/health` dabei bis zu
21,7 Sekunden.

Der Nachweis am laufenden System fuehrt `tests/run-event-loop-latency-probe.sh`
(der stellt die Bedingung her und misst). Dieser Test hier ist die statische
Ergaenzung: er verhindert, dass die **naechste** Schleife den Defekt neu
baut. Beides zusammen, weil keines von beidem allein reicht — die Messung
laeuft nicht in jeder Kette, und ein bestandener Strukturtest ist noch keine
gemessene Latenz.
"""
import ast
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
if not (BACKEND_ROOT / "app").exists():
    BACKEND_ROOT = REPO_ROOT
sys.path.insert(0, str(BACKEND_ROOT))

WATCHED_MODULES = ("main.py", "backup_service.py")

# Aufrufe, die blockieren. Steht einer davon direkt im Rumpf einer
# `async def *_task`, laeuft er auf dem Event-Loop.
BLOCKING_NAMES = {
    "SessionLocal",
    "get_stock_data",
    "get_latest_close",
    "get_avg_daily_volume",
    "dispatch_pending_orders",
    "evaluate_alert_rules_for_all_users",
    "dispatch_configured_watchlist_alerts",
    "create_backup",
    "normalized_macro_calendar",
    "send_notification_to_user",
}


def _module_tree(filename: str) -> ast.Module:
    path = BACKEND_ROOT / "app" / filename
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _background_tasks(tree: ast.Module):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name.endswith("_task")
    ]


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


class BackgroundLoopsTests(unittest.TestCase):
    def test_the_watched_modules_actually_contain_loops(self):
        # Ein Guard, der nichts findet, ist gruen und wertlos.
        total = sum(len(_background_tasks(_module_tree(name))) for name in WATCHED_MODULES)
        self.assertGreaterEqual(total, 7, f"nur {total} Hintergrundschleifen gefunden")

    def test_no_loop_calls_blocking_work_directly(self):
        offenders = []
        for filename in WATCHED_MODULES:
            for task in _background_tasks(_module_tree(filename)):
                blocking = sorted(_called_names(task) & BLOCKING_NAMES)
                if blocking:
                    offenders.append(f"{filename}:{task.name} -> {', '.join(blocking)}")
        self.assertEqual(
            [],
            offenders,
            "Hintergrundschleife ruft blockierende Arbeit direkt auf dem Event-Loop auf. "
            "Den Zyklus in eine synchrone Funktion auslagern und ueber "
            f"`await run_cycle(...)` fahren: {offenders}",
        )

    def test_every_loop_goes_through_run_cycle(self):
        without = []
        for filename in WATCHED_MODULES:
            for task in _background_tasks(_module_tree(filename)):
                if "run_cycle" not in _called_names(task):
                    without.append(f"{filename}:{task.name}")
        self.assertEqual(
            [],
            without,
            f"Hintergrundschleife ohne `run_cycle`: {without}",
        )

    def test_the_executor_is_separate_from_the_request_pool(self):
        # `asyncio.to_thread`/`run_in_executor(None, ...)` wuerde den
        # Default-Executor benutzen. Der Sinn des eigenen Pools ist, dass
        # Hintergrundarbeit die Anfragen nicht verdraengen kann.
        source = (BACKEND_ROOT / "app" / "background.py").read_text(encoding="utf-8")
        self.assertIn("ThreadPoolExecutor(", source)
        self.assertIn("run_in_executor(get_executor()", source)
        self.assertNotIn("run_in_executor(None", source)


if __name__ == "__main__":
    unittest.main()
