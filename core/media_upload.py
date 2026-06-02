from __future__ import annotations

import uuid
from pathlib import Path

from django.core.files.storage import default_storage


def save_task_photo(uploaded_file, prefix: str = "task_reports") -> str:
    """Сохраняет фото в default storage и возвращает публичный URL."""
    ext = Path(uploaded_file.name).suffix.lower() or ".jpg"
    name = f"{prefix}/{uuid.uuid4().hex}{ext}"
    path = default_storage.save(name, uploaded_file)
    return default_storage.url(path)
