"""Тестирование моделей: probe, speed-тест, fingerprint."""

import json
import time
import urllib.error
import urllib.request
import hashlib


def probe_with_metrics(base, key, model):
    """Тест доступности модели + замер TTFT, total_time, tokens."""
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

        # fingerprint модели (если есть)
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
        return "ERR", None, total, 0, "", str(msg)[:60]
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
