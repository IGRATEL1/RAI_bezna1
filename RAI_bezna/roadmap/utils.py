import base64
import os
import requests
from django.core.files.base import ContentFile
from django.conf import settings
from urllib.parse import urlparse
import uuid

def save_image_from_base64(base64_str, filename_hint=None):
    """
    Сохраняет base64 изображение в MEDIA_ROOT/achievements/..., возвращает относительный path (для ImageField).
    """
    if ',' in base64_str:
        base64_str = base64_str.split(',',1)[1]
    data = base64.b64decode(base64_str)
    ext = "png"
    if filename_hint and "." in filename_hint:
        ext = filename_hint.split(".")[-1]
    fname = f"ach_{uuid.uuid4().hex}.{ext}"
    path = os.path.join(settings.MEDIA_ROOT, "achievements")
    os.makedirs(path, exist_ok=True)
    fullpath = os.path.join(path, fname)
    with open(fullpath, "wb") as f:
        f.write(data)
    return f"achievements/{fname}"  # relative MEDIA path


def fetch_and_save_image(url):
    """
    Загружает image по URL (локальная сеть) и сохраняет в MEDIA_ROOT, возвращает relative path.
    """
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        content = r.content
    except Exception:
        return None
    # try get extension
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1].lstrip('.') or "png"
    fname = f"ach_{uuid.uuid4().hex}.{ext}"
    path = os.path.join(settings.MEDIA_ROOT, "achievements")
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, fname), "wb") as f:
        f.write(content)
    return f"achievements/{fname}"
