"""Тестирование моделей: probe, speed-тест, fingerprint."""

import json
import os
import time
import urllib.error
import urllib.request

from rb_tui import guard


# Ошибки, означающие «API заметил зондирование / лимит ключа», а не смерть модели.
THROTTLE_WORDS = (
    "catalog_probe_detected",
    "token_concurrency_limit",
    "concurrency_limit",
    "rate_limit",
    "rate limit",
    "too many requests",
    "429",
    "quota",
    "temporarily blocked",
    "probe detected",
)


class ProbeThrottled(Exception):
    """API включил защиту. Прогон надо остановить, модели не виноваты."""

    def __init__(self, msg, results=None):
        super().__init__(msg)
        self.msg = msg
        self.results = results or []


def is_throttle_error(msg):
    low = (msg or "").lower()
    return any(w in low for w in THROTTLE_WORDS)


def probe_with_metrics(base, key, model, retries=1):
    """Тест доступности модели + замер TTFT, total_time, tokens.

    Повторяем только транзиентные 5xx/таймауты. На защиту API не повторяем,
    а сразу сообщаем наверх — иначе ретраи только усугубляют блокировку.
    """
    retry_words = ("502", "503", "504", "timeout", "timed out", "overload", "busy")
    for attempt in range(retries + 1):
        status, ttft, total, tokens, fp, msg = _probe_once(base, key, model)
        if status in ("OK", "THROTTLE"):
            return status, ttft, total, tokens, fp, msg
        low = msg.lower()
        retryable = status == "ERR" and any(w in low for w in retry_words)
        if retryable and attempt < retries:
            time.sleep(2.0 * (attempt + 1))
            continue
        return status, ttft, total, tokens, fp, msg


def probe_all(base, key, models, delay=None, budget=None, progress=False):
    """Последовательный прогон маленькими порциями с паузой и джиттером.

    - delay по умолчанию из guard.DEFAULT_DELAY (3 сек).
    - budget ограничивает число запросов за прогон; список моделей лучше
      готовить через guard.pick_targets().
    - при первом детекте защиты выбрасывает ProbeThrottled с уже собранными
      результатами, чтобы вызывающий не записал их как «мёртвые».
    """
    import sys as _sys

    delay = guard.DEFAULT_DELAY if delay is None else delay
    if budget is not None:
        models = list(models)[:budget]

    results = []
    total = len(models)
    for i, m in enumerate(models):
        status, ttft, tot, tokens, fp, msg = probe_with_metrics(base, key, m)
        if status == "THROTTLE":
            if progress:
                _sys.stderr.write("\r" + " " * 40 + "\r")
                _sys.stderr.flush()
            raise ProbeThrottled(msg, results)
        results.append((m, status, ttft, tot, tokens, fp, msg))
        if progress:
            _sys.stderr.write(f"\r  проверено {i + 1}/{total}...")
            _sys.stderr.flush()
        if i < total - 1:
            time.sleep(guard.jitter(delay))
    if progress:
        _sys.stderr.write("\r" + " " * 40 + "\r")
        _sys.stderr.flush()
    return results


def _probe_once(base, key, model):
    """Один запрос к модели. Возвращает (status, ttft, total, tokens, fp, msg)."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Return exactly 'ok' and nothing else."}],
        "max_tokens": 5,
    }).encode()
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    url = base.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, data=body, headers=headers)

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ttft = round(time.monotonic() - start, 3)
            raw = resp.read()
            total = round(time.monotonic() - start, 3)
            j = json.loads(raw)
        if "choices" not in j:
            return "NO", ttft, total, 0, "", "ответ без choices"
        tokens = 0
        if "usage" in j:
            tokens = j["usage"].get("total_tokens", 0)
        fp = j.get("system_fingerprint", "")
        return "OK", ttft, total, tokens, fp, ""
    except urllib.error.HTTPError as e:
        total = round(time.monotonic() - start, 3)
        try:
            j = json.loads(e.read())
            err = j.get("error", {})
            msg = err.get("code") or err.get("type") or err.get("message") or f"HTTP {e.code}"
        except Exception:
            msg = f"HTTP {e.code}"
        msg = str(msg)[:80]
        if e.code == 429 or is_throttle_error(msg):
            return "THROTTLE", None, total, 0, "", msg
        return "ERR", None, total, 0, "", msg
    except Exception as e:
        total = round(time.monotonic() - start, 3)
        return "NO", None, total, 0, "", type(e).__name__


def speed_test(base, key, model, prompt_len=200):
    """Тест скорости генерации: возвращает tokens/s."""
    prompt = " ".join(["deep learning"] * prompt_len)
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": f"Summarize: {prompt}"}],
        "max_tokens": 100,
    }).encode()
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, headers=headers)

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
        total = time.monotonic() - start
        if not raw:
            return None, "пустой ответ"
        j = json.loads(raw)
        if "usage" not in j:
            return None, "нет usage"
        completion_tokens = j["usage"].get("completion_tokens", 0) or 1
        tps = round(completion_tokens / total, 2) if total > 0 else 0
        return tps, ""
    except Exception as e:
        return None, str(e)


def compare_models(base, key, model_a, model_b):
    """A/B сравнение двух моделей на одинаковых промптах."""
    prompts = [
        "Write a Python function to sort a list of dictionaries by a key.",
        "Explain quantum computing in simple terms.",
        "Write a haiku about programming.",
    ]
    results = []
    for i, prompt in enumerate(prompts):
        row = {"prompt": i + 1}
        for label, model in [("A", model_a), ("B", model_b)]:
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
            }).encode()
            headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
            req = urllib.request.Request(
                base.rstrip("/") + "/chat/completions", data=body, headers=headers
            )
            start = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                total = round(time.monotonic() - start, 3)
                j = json.loads(raw)
                content = j.get("choices", [{}])[0].get("message", {}).get("content", "")
                tokens = j.get("usage", {}).get("total_tokens", 0)
                row[f"ttft_{label}"] = total
                row[f"tokens_{label}"] = tokens
                row[f"len_{label}"] = len(content)
            except Exception:
                row[f"ttft_{label}"] = None
                row[f"tokens_{label}"] = 0
                row[f"len_{label}"] = 0
        results.append(row)
    return results
