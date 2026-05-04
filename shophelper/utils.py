"""
Утилиты для разбора кодов маркировки (GS1 Data Matrix / «Честный ЗНАК»).

Строка со сканера может содержать разделитель GS (ASCII 29, \\x1d) между полями
или склеенные AI подряд. Извлекаются типовые AI: 01 (GTIN), 17 (годен до),
10 (партия), 21 (серийный номер).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# Групповой разделитель GS1 между элементами в одной строке кода.
GS1_SEPARATOR = "\x1d"


def parse_data_matrix(code: str) -> dict[str, Any]:
    """
    Разбор строки GS1 Data Matrix.

    Возвращает словарь с ключами:
      - gtin: str | None  (14 цифр по AI 01)
      - expiry_raw: str | None  (6 символов YYMMDD по AI 17)
      - expiry_date: date | None  (datetime.strptime(..., \"%y%m%d\"))
      - batch: str | None  (AI 10)
      - serial: str | None  (AI 21, не короче 7 символов при наличии)

    Логика вместимости по осям не применяется — только извлечение полей по GS1.
    """
    raw = (code or "").strip().replace("\r", "").replace("\n", "")
    result: dict[str, Any] = {
        "gtin": None,
        "expiry_raw": None,
        "expiry_date": None,
        "batch": None,
        "serial": None,
    }

    if not raw:
        return result

    if GS1_SEPARATOR in raw:
        _parse_gs_chunks(raw.split(GS1_SEPARATOR), result)
    else:
        _parse_concatenated(raw, result)

    er = result.get("expiry_raw")
    if er:
        try:
            result["expiry_date"] = datetime.strptime(er, "%y%m%d").date()
        except ValueError:
            result["expiry_date"] = None

    return result


def _parse_gs_chunks(chunks: list[str], result: dict[str, Any]) -> None:
    """Каждый фрагмент после GS имеет вид «AI + значение»."""
    for chunk in chunks:
        chunk = chunk.strip()
        if len(chunk) < 4:
            continue
        ai = chunk[:2]
        payload = chunk[2:]
        if ai == "01" and len(payload) >= 14 and payload[:14].isdigit():
            result["gtin"] = payload[:14]
        elif ai == "17" and len(payload) >= 6 and payload[:6].isdigit():
            result["expiry_raw"] = payload[:6]
        elif ai == "10" and payload:
            result["batch"] = payload.strip()
        elif ai == "21" and len(payload) >= 7:
            result["serial"] = payload.strip()


def _parse_concatenated(s: str, result: dict[str, Any]) -> None:
    """
    Линейный разбор без GS: фиксированные длины для 01 и 17, затем 10 до маркера 21,
    затем 21 до конца строки (или хвостовых AI вроде 93 для КМ).

    Перевод единиц не нужен — все поля уже в символах кода.
    """
    i = 0
    n = len(s)
    while i < n:
        if i + 16 <= n and s[i : i + 2] == "01" and s[i + 2 : i + 16].isdigit():
            result["gtin"] = s[i + 2 : i + 16]
            i += 16
            continue
        if i + 8 <= n and s[i : i + 2] == "17" and s[i + 2 : i + 8].isdigit():
            result["expiry_raw"] = s[i + 2 : i + 8]
            i += 8
            continue
        if i + 2 <= n and s[i : i + 2] == "10":
            start = i + 2
            j = start
            while j < n - 1:
                if s[j : j + 2] == "21":
                    result["batch"] = s[start:j].strip()
                    i = j
                    break
                j += 1
            else:
                result["batch"] = s[start:n].strip()
                return
            continue
        if i + 2 <= n and s[i : i + 2] == "21":
            tail = s[i + 2 : n]
            # Отрезаем служебные поля после серии (например 93…), если попали в строку.
            tail = re.split(r"(?=93\d)", tail, maxsplit=1)[0]
            if len(tail) >= 7:
                result["serial"] = tail.strip()
            return
        i += 1

    # Дополнительно — резервные regex, если линейный проход не заполнил GTIN/дату.
    if result["gtin"] is None:
        m = re.search(r"01(\d{14})", s)
        if m:
            result["gtin"] = m.group(1)
    if result["expiry_raw"] is None:
        m = re.search(r"17(\d{6})", s)
        if m:
            result["expiry_raw"] = m.group(1)
