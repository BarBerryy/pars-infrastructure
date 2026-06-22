"""Хранение результатов: SQLite + экспорт в GeoJSON и CSV.

SQLite выбран как бессерверная БД без внешних зависимостей. Если в будущем
понадобится геопоиск/индексы — структуру легко перенести на PostgreSQL+PostGIS.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import POI

SCHEMA = """
CREATE TABLE IF NOT EXISTS poi (
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    category      TEXT NOT NULL,
    "group"       TEXT NOT NULL,
    name          TEXT,
    lat           REAL NOT NULL,
    lon           REAL NOT NULL,
    address       TEXT,
    phone         TEXT,
    website       TEXT,
    opening_hours TEXT,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_poi_category ON poi(category);
CREATE INDEX IF NOT EXISTS idx_poi_group ON poi("group");

CREATE TABLE IF NOT EXISTS searches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT,
    created_at   TEXT NOT NULL,
    place        TEXT,            -- исходный запрос места (если был --place)
    center_lat   REAL NOT NULL,
    center_lon   REAL NOT NULL,
    radius_m     REAL NOT NULL,
    categories   TEXT NOT NULL,   -- ключи категорий через запятую
    result_count INTEGER NOT NULL,
    geometry     TEXT             -- GeoJSON нарисованной фигуры (если режим shape)
);
"""


class Storage:
    def __init__(self, db_path: str | Path = "osm_poi.db"):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Догоняющие миграции для БД, созданных ранними версиями схемы."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(searches)")}
        if "geometry" not in cols:
            self.conn.execute("ALTER TABLE searches ADD COLUMN geometry TEXT")

    def save(self, pois: Iterable[POI]) -> int:
        """Сохранить объекты (upsert по source+source_id). Вернуть кол-во записей."""
        rows = [p.as_row() for p in pois]
        if not rows:
            return 0
        cols = list(rows[0].keys())
        quoted = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        self.conn.executemany(
            f"INSERT OR REPLACE INTO poi ({quoted}) VALUES ({placeholders})", rows
        )
        self.conn.commit()
        return len(rows)

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM poi").fetchone()[0]

    # ---- история поиска -----------------------------------------------------

    def record_search(
        self,
        *,
        place: str | None,
        center_lat: float,
        center_lon: float,
        radius_m: float,
        categories: list[str],
        result_count: int,
        name: str | None = None,
        geometry: str | None = None,
    ) -> int:
        """Записать выполненный поиск в историю. Вернуть его id.

        Если имя не задано, формируется автоматически из места/координат, радиуса
        или типа фигуры.
        """
        created_at = datetime.now().isoformat(timespec="seconds")
        where = place or f"{center_lat:.5f}, {center_lon:.5f}"
        if name is None:
            if geometry is not None:  # нарисованная фигура
                name = f"Фигура @ {center_lat:.4f}, {center_lon:.4f}"
            elif radius_m == 0:  # поиск по границе города/района
                name = f"{where} (вся территория)"
            else:
                name = f"{where} · r={radius_m / 1000:g} км"
        cur = self.conn.execute(
            """INSERT INTO searches
               (name, created_at, place, center_lat, center_lon, radius_m,
                categories, result_count, geometry)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, created_at, place, center_lat, center_lon, radius_m,
             ",".join(categories), result_count, geometry),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_searches(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM searches ORDER BY id DESC"
        ).fetchall()

    def get_search(self, search_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM searches WHERE id = ?", (search_id,)
        ).fetchone()

    def rename_search(self, search_id: int, new_name: str) -> bool:
        """Переименовать запись истории. Вернуть True, если запись существовала."""
        cur = self.conn.execute(
            "UPDATE searches SET name = ? WHERE id = ?", (new_name, search_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_search(self, search_id: int) -> bool:
        """Удалить запись истории. Вернуть True, если запись существовала."""
        cur = self.conn.execute("DELETE FROM searches WHERE id = ?", (search_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def all_pois(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM poi").fetchall()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def export_geojson(pois: Iterable[POI], path: str | Path) -> int:
    features = [p.as_geojson_feature() for p in pois]
    fc = {"type": "FeatureCollection", "features": features}
    Path(path).write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(features)


def export_csv(pois: Iterable[POI], path: str | Path) -> int:
    rows = [p.as_row() for p in pois]
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return 0
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
