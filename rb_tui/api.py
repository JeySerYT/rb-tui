"""ReformBoss API: получение каталога, управление ключом."""

import json
import os
import re
import urllib.error
import urllib.request


def api_key(settings):
    key = settings.get("apiKey", "")
    m = re.match(r"\{file:(.+)\}", key or "")
    if m:
        path = os.path.expanduser(m.group(1))
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return key


def http_json(url, key, data=None, timeout=25):
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_catalog(base, key):
    """Получить список моделей из каталога API."""
    try:
        data = http_json(base.rstrip("/") + "/models", key, timeout=20)
        models = sorted(m["id"] for m in data.get("data", []))
        owned = {}
        for m in data.get("data", []):
            owned[m["id"]] = m.get("owned_by", "unknown")
        return models, owned, None
    except urllib.error.HTTPError as e:
        return None, None, f"HTTP {e.code}"
    except Exception as e:
        return None, None, type(e).__name__
