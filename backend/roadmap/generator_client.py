import requests
from django.conf import settings

GENERATOR_TIMEOUT = 25  # seconds — укажи по потребности

def call_generator(ai_request_id: str, user_id: str, goal: dict, prompt: str, params: dict = None):
    """
    Синхронно вызывает генератор по settings.GENERATOR_URL.
    Возвращает dict с ключами: status (succeeded|failed|queued),
    и payload (roadmap, achievements, raw_output) если есть.
    """
    url = settings.GENERATOR_URL
    payload = {
        "ai_request_id": ai_request_id,
        "user_id": user_id,
        "goal": goal,
        "prompt": prompt,
        "params": params or {}
    }
    headers = {
        "Content-Type": "application/json",
        # простой shared secret (LAN). Generator должен проверять этот header.
        "Authorization": f"Bearer {getattr(settings, 'GENERATOR_SECRET', '')}"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=GENERATOR_TIMEOUT)
    except requests.RequestException as e:
        return {"status": "failed", "error": str(e)}

    # Если генератор принял задачу и обработал (200)
    if resp.status_code == 200:
        # expected: {"status":"succeeded","roadmap": {...},"achievements":[...],"raw_output": {...}}
        try:
            data = resp.json()
        except ValueError:
            return {"status": "failed", "error": "invalid JSON from generator"}
        return data
    elif resp.status_code == 202:
        # generator accepted job and will process async
        try:
            data = resp.json()
        except ValueError:
            data = {}
        return {"status": "queued", **data}
    else:
        # 4xx/5xx
        try:
            err = resp.json()
        except ValueError:
            err = resp.text
        return {"status": "failed", "error": f"generator returned {resp.status_code}: {err}"}
