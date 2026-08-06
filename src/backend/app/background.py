"""Hintergrundarbeit gehoert nicht auf den Event-Loop.

Die periodischen Schleifen (Scanner, Alarm-Auswertung, Alarm-Zustellung,
Paper-Fills, ML-Nachtraining, Auto-Execution, Backup) sind Koroutinen, ihr
Zyklus ist aber vollstaendig blockierend: Provider-HTTP, Datenbank,
XGBoost-Training. Wer das direkt in einer `async def` ausfuehrt, haelt den
Event-Loop fuer die gesamte Dauer an — und ein angehaltener Loop nimmt
**keine einzige Anfrage** mehr an.

Gemessen am 2026-08-06, bevor es diese Datei gab: waehrend einer 85,6 s
dauernden Anfrage brauchte `/api/health` — ein Endpunkt ohne jede
Provider-Arbeit — bis zu **21,7 Sekunden**. Nicht der Threadpool war voll,
der Loop stand.

`run_cycle` legt genau diese Arbeit in einen **eigenen** Threadpool. Das
entkoppelt zweierlei: der Loop bleibt frei, und die Hintergrundarbeit kann
den Threadpool der Request-Bearbeitung (AnyIO) nicht auffressen, weil sie
ihn nicht benutzt. Die Groesse des Pools ist zugleich die Obergrenze fuer
gleichzeitige Hintergrundzyklen.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Gleichzeitig laufende Hintergrundzyklen. Sieben Schleifen, die meiste Zeit
#: schlafend — vier Threads reichen, und die Grenze ist erwuenscht: sie
#: verhindert, dass sich alle Schleifen gleichzeitig auf die Anbieter werfen.
BACKGROUND_WORKER_THREADS = max(1, int(os.getenv("BACKGROUND_WORKER_THREADS", "4")))

_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=BACKGROUND_WORKER_THREADS,
            thread_name_prefix="bg-cycle",
        )
        logger.info(
            "background_executor_started",
            extra={"workers": BACKGROUND_WORKER_THREADS},
        )
    return _executor


async def run_cycle(name: str, fn: Callable[[], T]) -> T | None:
    """Einen blockierenden Hintergrundzyklus ausserhalb des Event-Loops fahren.

    Faengt jede Ausnahme: eine gescheiterte Runde darf die Schleife nicht
    beenden, sonst faellt die Funktion still fuer die restliche Laufzeit des
    Prozesses aus. Der Rueckgabewert ist `None`, wenn der Zyklus scheiterte.
    """
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(get_executor(), fn)
    except Exception:
        logger.exception("background_cycle_failed", extra={"cycle": name})
        return None


def shutdown(wait: bool = False) -> None:
    """Pool beim Herunterfahren schliessen.

    `wait=False` als Default: ein haengender Provider-Aufruf darf das
    Beenden des Containers nicht aufhalten.
    """
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=wait, cancel_futures=True)
        _executor = None
