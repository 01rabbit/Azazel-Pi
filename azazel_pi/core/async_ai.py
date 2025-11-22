#!/usr/bin/env python3
"""
Asynchronous Deep AI evaluation worker.

This module provides a simple background queue to run costly Ollama
evaluations asynchronously. Call `enqueue(alert_data, context)` to
schedule a deep analysis. Results are logged and optionally sent via
Mattermost notifications when configured.
"""
from __future__ import annotations

import logging
import threading
import random
import time
from queue import Queue
from typing import Any, Dict, Optional
from pathlib import Path

# lazy resolver for AI evaluator to avoid importing heavy deps at module import time
get_ai_evaluator = None
from . import notify_config

logger = logging.getLogger(__name__)

_queue: "Queue[Dict[str, Any]]" = Queue()
_started = False

# Sampling/rate defaults
_DEFAULT_SAMPLE_RATE = float(notify_config.get("ai", {}).get("deep_sample_rate", 1.0))
_DEFAULT_MAX_PER_MIN = int(notify_config.get("ai", {}).get("deep_max_per_min", 60) or 60)

# Simple rate limiter state (use time.time())
_tokens = _DEFAULT_MAX_PER_MIN
_last_refill = time.time()
_rate_lock = threading.Lock()


def _allow_enqueue() -> bool:
    """Decide whether to allow enqueue based on sampling and a simple token bucket.

    Thread-safe and uses wall-clock minute-based refill. Returns True when
    the item is allowed to be enqueued.
    """
    # Probabilistic sampling
    try:
        if random.random() > _DEFAULT_SAMPLE_RATE:
            return False
    except Exception:
        # if random fails for some reason, default to allow
        pass

    global _tokens, _last_refill
    with _rate_lock:
        try:
            current = int(time.time())
            # refill once per minute
            if current - int(_last_refill) >= 60:
                _tokens = _DEFAULT_MAX_PER_MIN
                _last_refill = current
            if _tokens <= 0:
                return False
            _tokens -= 1
            return True
        except Exception:
            return True


def _worker() -> None:
    logger.info("Async AI worker started")
    while True:
        item = _queue.get()
        if item is None:
            break
        alert = item.get("alert") or {}
        context = item.get("context") or {}
        try:
            # resolve evaluator lazily; tests may monkeypatch `get_ai_evaluator` in this module
            evaluator = None
            try:
                if callable(get_ai_evaluator):
                    evaluator = get_ai_evaluator()
                else:
                    # lazy import (avoid importing requests during test collection)
                    from .ai_evaluator import get_ai_evaluator as _g
                    globals()['get_ai_evaluator'] = _g
                    evaluator = _g()
            except Exception:
                logger.warning("No AI evaluator available for deep analysis")
                continue

            sig_safe = str(alert.get('signature') or '')
            src_safe = str(alert.get('src_ip') or '')
            logger.info(f"Running deep AI analysis for {src_safe} {sig_safe}")
            # evaluator may be flaky; retry a small number of times with backoff
            max_eval_retries = int(notify_config.get("ai", {}).get("deep_eval_retries", 2) or 2)
            eval_attempt = 0
            result = None
            while eval_attempt <= max_eval_retries:
                try:
                    result = evaluator.evaluate_threat(alert)
                    break
                except Exception:
                    eval_attempt += 1
                    wait = 0.5 * (2 ** (eval_attempt - 1))
                    logger.exception(f"Deep eval attempt {eval_attempt} failed, retrying in {wait}s")
                    time.sleep(wait)
            if result is None:
                logger.error("Deep AI evaluation failed after retries")
                continue
            logger.info(f"Deep AI result: {result}")

            # Persist deep result to decisions.log if provided in context
            decisions_path = context.get("decisions_log")
            if decisions_path:
                p = Path(decisions_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                entry = {
                    "event": alert.get("signature", "deep_ai"),
                    "score": result.get("score") or ((result.get("risk", 1) - 1) * 25),
                    "classification": result.get("category"),
                    "timestamp": alert.get("timestamp"),
                    "deep_ai": result,
                    "note": "deep_followup",
                }
                import json

                # write with retries to tolerate transient FS/permission issues
                max_persist_retries = int(notify_config.get("ai", {}).get("deep_persist_retries", 3) or 3)
                attempt = 0
                while attempt <= max_persist_retries:
                    try:
                        with p.open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False))
                            fh.write("\n")
                            fh.flush()
                        break
                    except Exception:
                        attempt += 1
                        wait = 0.25 * (2 ** (attempt - 1))
                        logger.exception(f"Failed to persist deep AI result (attempt {attempt}), retrying in {wait}s")
                        time.sleep(wait)
                else:
                    logger.error("Giving up persisting deep AI result after retries")

        except Exception:
            logger.exception("Async AI worker encountered an error during evaluation")
        finally:
            try:
                _queue.task_done()
            except Exception:
                pass


def start() -> None:
    global _started
    if _started:
        return
    t = threading.Thread(target=_worker, daemon=True, name="azazel-async-ai")
    t.start()
    _started = True


def enqueue(alert: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> None:
    """Schedule a deep AI evaluation for the given alert.

    This returns immediately; evaluation runs in background.
    """
    start()
    ctx = context or {}
    src_ip = str(alert.get("src_ip") or "")
    # IPv6フィルタ: src_ipが":"を含む場合は無視
    if ":" in src_ip:
        logger.info(f"Skipping IPv6 event for src_ip={src_ip}")
        return
    # sampling / rate limiting
    try:
        allow = _allow_enqueue()
    except Exception:
        allow = True
    if not allow:
        logger.info("Async AI enqueue skipped by sampling/rate limit")
        return
    _queue.put({"alert": alert, "context": ctx})


def shutdown() -> None:
    """Gracefully stop the worker (for tests).

    Note: This will block until the worker thread sees the sentinel.
    """
    _queue.put(None)
