#!/usr/bin/env python3
"""
Универсальный парсер каталогов: сайт -> CSV / Excel.

Работает по пресету (JSON): адрес страницы, селектор карточки товара и
селекторы полей. Поддерживает пагинацию, задержку между запросами,
повторы при ошибках и удаление дублей.

Пример:
    python parser.py --preset presets/books.json --out books.csv
    python parser.py --preset presets/books.json --out books.xlsx --max-items 200
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


@dataclass
class Preset:
    """Описание того, как читать конкретный сайт."""

    name: str
    url: str
    item: str
    fields: dict[str, dict[str, Any]]
    next_page: str | None = None
    max_pages: int = 10
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Preset":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            name=data.get("name", Path(path).stem),
            url=data["url"],
            item=data["item"],
            fields=data["fields"],
            next_page=data.get("next_page"),
            max_pages=int(data.get("max_pages", 10)),
            headers=data.get("headers", {}),
        )


def clean(value: str) -> str:
    """Схлопываем пробелы и убираем неразрывные пробелы."""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def parse_number(value: str) -> float | None:
    """'1 299,90 руб.' -> 1299.90

    Понимает пробелы-разделители тысяч, запятую как десятичный знак и
    вариант '1.299.90', где точки разделяют тысячи.
    """
    raw = re.sub(r"[^\d,.\-]", "", value).strip(".,-")
    if not raw:
        return None
    if "," in raw and "." in raw:
        # тот разделитель, что стоит правее, — десятичный
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif raw.count(",") == 1:
        raw = raw.replace(",", ".")
    elif raw.count(",") > 1:
        raw = raw.replace(",", "")
    parts = raw.split(".")
    if len(parts) > 2:  # 1.299.90 -> 1299.90
        raw = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(raw)
    except ValueError:
        return None


def _extract(node, spec: dict[str, Any]) -> str:
    """Достаём одно поле из карточки по селектору и способу чтения."""
    selector = spec.get("selector")
    target = node
    if selector:
        target = node.select_one(selector)
        if target is None:
            return ""
    attr = spec.get("attr")
    if attr == "text":
        raw = target.get_text(" ", strip=True)
    elif attr:
        # class и rel возвращаются списком — склеиваем в строку
        raw = target.get(attr, "") or ""
        if isinstance(raw, (list, tuple)):
            raw = " ".join(str(part) for part in raw)
    else:
        raw = target.get_text(" ", strip=True)

    if spec.get("regex"):
        match = re.search(spec["regex"], raw)
        raw = match.group(1) if match else ""
    if spec.get("number"):
        number = parse_number(raw)
        return "" if number is None else str(number)
    return clean(raw)


def parse_html(html: str, preset: Preset) -> list[dict[str, Any]]:
    """Разбирает одну страницу и возвращает список карточек."""
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict[str, Any]] = []
    for card in soup.select(preset.item):
        row: dict[str, Any] = {}
        for name, spec in preset.fields.items():
            row[name] = _extract(card, spec)
        if any(row.values()):
            rows.append(row)
    return rows


def fetch(session: requests.Session, url: str, timeout: int = 20, retries: int = 3) -> str:
    """GET с повторами: 429/5xx и таймауты не валят весь парсинг."""
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status()
            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding
            return response.text
        except Exception as error:  # noqa: BLE001 - нужен общий перехват для ретраев
            last_error = error
            if attempt < retries:
                time.sleep(attempt * 1.5)
    raise RuntimeError(f"Не удалось получить {url}: {last_error}")


def crawl(preset: Preset, max_items: int = 0, delay: float = 1.0) -> list[dict[str, Any]]:
    """Обходит страницы по пагинации, пока не кончится лимит или страницы."""
    session = requests.Session()
    session.headers.update({**DEFAULT_HEADERS, **preset.headers})

    url: str | None = preset.url
    rows: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    for page in range(1, preset.max_pages + 1):
        if not url:
            break
        html = fetch(session, url)
        page_rows = parse_html(html, preset)
        for row in page_rows:
            key = tuple(row.values())
            if key not in seen:  # дубли между страницами
                seen.add(key)
                rows.append(row)
        print(f"страница {page}: {len(page_rows)} карточек, всего {len(rows)}", file=sys.stderr)

        if max_items and len(rows) >= max_items:
            rows = rows[:max_items]
            break
        if not preset.next_page:
            break
        soup = BeautifulSoup(html, "lxml")
        link = soup.select_one(preset.next_page)
        url = link.get("href") if link else None
        if url and url.startswith("/"):
            url = requests.compat.urljoin(preset.url, url)
        time.sleep(delay)

    return rows


def save_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError("Нет данных для сохранения")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def save_xlsx(rows: list[dict[str, Any]], path: Path) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError as error:  # pragma: no cover
        raise SystemExit("Для Excel нужен openpyxl: pip install openpyxl") from error
    if not rows:
        raise ValueError("Нет данных для сохранения")
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = "data"
    headers = list(rows[0].keys())
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([row.get(name, "") for name in headers])
    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(width + 2, 60)
    sheet.freeze_panes = "A2"
    book.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Парсер каталога в CSV/Excel")
    parser.add_argument("--preset", required=True, help="путь к JSON-пресету")
    parser.add_argument("--out", default="result.csv", help="result.csv или result.xlsx")
    parser.add_argument("--max-items", type=int, default=0, help="0 — без ограничения")
    parser.add_argument("--delay", type=float, default=1.0, help="пауза между запросами, сек")
    args = parser.parse_args()

    preset = Preset.load(args.preset)
    rows = crawl(preset, max_items=args.max_items, delay=args.delay)
    out = Path(args.out)
    if out.suffix.lower() == ".xlsx":
        save_xlsx(rows, out)
    else:
        save_csv(rows, out)
    print(f"Готово: {len(rows)} строк -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
