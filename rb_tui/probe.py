"""Тестирование моделей: probe, speed-тест, fingerprint."""

import json
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

PROBE_PROMPT = "Count from 1 to 20, separated by single spaces. Output only the numbers."


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
    """Тест доступности модели + замер TTFT, TTS, total_time, tokens.

    Повторяем только транзиентные 5xx/таймауты. На защиту API не повторяем,
    а сразу сообщаем наверх — иначе ретраи только усугубляют блокировку.
    """
    retry_words = ("502", "503", "504", "timeout", "timed out", "overload", "busy")
    for attempt in range(retries + 1):
        status, ttft, tts, tot, tokens, fp, msg = _probe_once(base, key, model)
        if status in ("OK", "THROTTLE"):
            return status, ttft, tts, tot, tokens, fp, msg
        low = msg.lower()
        retryable = status == "ERR" and any(w in low for w in retry_words)
        if retryable and attempt < retries:
            time.sleep(2.0 * (attempt + 1))
            continue
        return status, ttft, tts, tot, tokens, fp, msg


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
        status, ttft, tts, tot, tokens, fp, msg = probe_with_metrics(base, key, m)
        if status == "THROTTLE":
            if progress:
                _sys.stderr.write("\r" + " " * 40 + "\r")
                _sys.stderr.flush()
            raise ProbeThrottled(msg, results)
        results.append((m, status, ttft, tts, tot, tokens, fp, msg))
        if progress:
            _sys.stderr.write(f"\r  проверено {i + 1}/{total}...")
            _sys.stderr.flush()
        if i < total - 1:
            time.sleep(guard.jitter(delay))
    if progress:
        _sys.stderr.write("\r" + " " * 40 + "\r")
        _sys.stderr.flush()
    return results


def _probe_once(base, key, model, stream=True):
    """Один запрос к модели. Возвращает кортеж (status, ttft, tts, total,
    tokens, fp, msg) — совместимый формат для CLI и тестов."""
    prompt = PROBE_PROMPT
    r = stream_request(base, key, model, prompt, max_tokens=48, stream=stream)
    return (r["status"], r["ttft"], r["tts"], r["total"], r["tokens"],
            r["fp"], r["msg"])


def stream_request(base, key, model, prompt, max_tokens=200, stream=True, timeout=60):
    """Один запрос к модели. Возвращает словарь с метриками и текстом ответа.

    TTFT — время до первого контент-чанка, TTS — до второго.
    Для нестримингового ответа TTS/TPS не вычисляются: замерять там нечего.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    if stream:
        payload["stream"] = True
    body = json.dumps(payload).encode()
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    url = base.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, data=body, headers=headers)

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "text/event-stream" in ctype:
                ttft, tts, total, tokens, chars, content, fp = _read_stream(resp, start)
                if ttft is None:
                    return _result("NO", total=total, msg="пустой стрим")
                return _result(
                    "OK", ttft=ttft, tts=tts, total=total, tokens=tokens,
                    chars=chars, content=content, fp=fp,
                )

            raw = resp.read()
            total = round(time.monotonic() - start, 3)
            j = json.loads(raw)
        if "choices" not in j:
            return _result("NO", total=total, msg="ответ без choices")
        message = (j.get("choices") or [{}])[0].get("message") or {}
        content = message.get("content") or ""
        tokens = 0
        if "usage" in j:
            usage = j["usage"] or {}
            tokens = usage.get("completion_tokens") or usage.get("total_tokens", 0)
        fp = j.get("system_fingerprint", "")
        # без стрима TTFT измерить нельзя — показываем полное время
        return _result(
            "OK", ttft=total, total=total, tokens=tokens, chars=len(content),
            content=content, fp=fp,
        )
    except urllib.error.HTTPError as e:
        total = round(time.monotonic() - start, 3)
        try:
            j = json.loads(e.read())
            err = j.get("error", {})
            msg = err.get("code") or err.get("type") or err.get("message") or f"HTTP {e.code}"
        except Exception:
            msg = f"HTTP {e.code}"
        msg = str(msg)[:80]
        if stream and e.code in (400, 404, 422) and "stream" in msg.lower():
            # провайдер не умеет стриминг — повторяем обычным запросом
            return stream_request(
                base, key, model, prompt, max_tokens=max_tokens,
                stream=False, timeout=timeout,
            )
        if e.code == 429 or is_throttle_error(msg):
            return _result("THROTTLE", total=total, msg=msg)
        return _result("ERR", total=total, msg=msg)
    except Exception as e:
        total = round(time.monotonic() - start, 3)
        return _result("NO", total=total, msg=type(e).__name__)


def _result(status, ttft=None, tts=None, total=None, tokens=0, chars=0,
            content="", fp="", msg=""):
    return {
        "status": status,
        "ttft": ttft,
        "tts": tts,
        "total": total,
        "tokens": tokens,
        "chars": chars,
        "content": content,
        "fp": fp,
        "msg": msg,
    }


def effective_tps(r):
    """Единая формула TPS: токены за всё время ответа (только для стрима)."""
    if r.get("tts") is None or not r.get("tokens") or not r.get("total"):
        return None
    return round(r["tokens"] / r["total"], 1)


def _read_stream(resp, start):
    """Разобрать SSE-поток. Возвращает (ttft, tts, total, tokens, chars, text, fp).

    tokens — число контент-чанков: оценка именно сгенерированных токенов,
    без токенов промпта (usage в стриме обычно отсутствует).
    """
    first = None
    second = None
    chunks = 0
    usage_tokens = 0
    parts = []
    fp = ""

    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            event = json.loads(data)
        except ValueError:
            continue

        if not fp:
            fp = event.get("system_fingerprint") or ""

        usage = event.get("usage")
        if usage:
            usage_tokens = (
                usage.get("completion_tokens")
                or usage.get("total_tokens")
                or usage_tokens
            )

        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            text = delta.get("content")
            if not text:
                continue
            chunks += 1
            parts.append(text)
            if chunks == 1:
                first = round(time.monotonic() - start, 3)
            elif chunks == 2:
                second = round(time.monotonic() - start, 3)

    total = round(time.monotonic() - start, 3)
    content = "".join(parts)
    return first, second, total, chunks or usage_tokens, len(content), content, fp


def _call_or_throttle(base, key, model, prompt, max_tokens, timeout=60):
    r = stream_request(base, key, model, prompt, max_tokens=max_tokens, timeout=timeout)
    if r["status"] == "THROTTLE":
        raise ProbeThrottled(r["msg"])
    return r


def bench_model(base, key, model, prompts=None, delay=None):
    """Бенчмарк на нескольких промптах через тот же стриминговый замер."""
    prompts = prompts or [
        "Write a Python function to merge two sorted lists.",
        "Explain the difference between TCP and UDP in simple terms.",
        "Write a short poem about artificial intelligence.",
    ]
    delay = guard.DEFAULT_DELAY if delay is None else delay
    rows = []
    for i, prompt in enumerate(prompts, 1):
        r = _call_or_throttle(base, key, model, prompt, max_tokens=200)
        rows.append({
            "prompt": i,
            "status": r["status"],
            "ttft": r["ttft"],
            "tts": r["tts"],
            "tps": effective_tps(r),
            "total": r["total"],
            "tokens": r["tokens"],
            "len": r["chars"],
            "content": r["content"],
            "msg": r["msg"],
        })
        if i < len(prompts):
            time.sleep(guard.jitter(delay))
    return rows


def speed_test(base, key, model, prompt_len=200):
    """Тест скорости генерации: возвращает (tokens/s, ошибка)."""
    prompt = " ".join(["deep learning"] * prompt_len)
    r = _call_or_throttle(
        base, key, model, f"Summarize: {prompt}", max_tokens=100, timeout=60,
    )
    if r["status"] != "OK":
        return None, r["msg"] or r["status"]
    tps = effective_tps(r)
    if tps is None:
        return None, "нет стриминговых данных"
    return tps, ""


def compare_models(base, key, model_a, model_b, delay=None):
    """A/B сравнение двух моделей на одинаковых промптах."""
    prompts = [
        "Write a Python function to sort a list of dictionaries by a key.",
        "Explain quantum computing in simple terms.",
        "Write a haiku about programming.",
    ]
    delay = guard.DEFAULT_DELAY if delay is None else delay
    results = []
    calls = 0
    for i, prompt in enumerate(prompts, 1):
        row = {"prompt": i}
        for label, model in [("A", model_a), ("B", model_b)]:
            r = _call_or_throttle(base, key, model, prompt, max_tokens=200)
            calls += 1
            row[f"status_{label}"] = r["status"]
            row[f"ttft_{label}"] = r["ttft"]
            row[f"tts_{label}"] = r["tts"]
            row[f"tps_{label}"] = effective_tps(r)
            row[f"tokens_{label}"] = r["tokens"]
            row[f"len_{label}"] = r["chars"]
            row[f"msg_{label}"] = r["msg"]
            if calls < len(prompts) * 2:
                time.sleep(guard.jitter(delay))
        results.append(row)
    return results