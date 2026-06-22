"""Источник данных OpenStreetMap через Overpass API.

Overpass — бесплатный read-only API запросов к данным OSM. Лимитов на
коммерческое использование нет, но публичные инстансы просят соблюдать
вежливый rate limit и присылать User-Agent.

Документация Overpass QL: https://wiki.openstreetmap.org/wiki/Overpass_API
"""

from __future__ import annotations

import time
from typing import Iterable

import requests

from ..categories import Category
from ..models import POI
from .base import Circle, DataSource

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "pars-openstreetmap/0.1 (infrastructure POI parser)"


class OverpassError(RuntimeError):
    pass


class OverpassSource(DataSource):
    name = "osm"

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: int = 180,
        pause: float = 1.0,
        max_retries: int = 3,
    ):
        self.endpoint = endpoint
        self.timeout = timeout
        self.pause = pause          # пауза между запросами (вежливость к серверу)
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    # ---- построение запроса -------------------------------------------------

    def _selectors_body(self, categories: list[Category], area_filter: str) -> str:
        lines: list[str] = []
        for cat in categories:
            for key, value in cat.selectors:
                sel = f'["{key}"="{value}"]'
                for kind in ("node", "way", "relation"):
                    lines.append(f"  {kind}{sel}{area_filter};")
        return "\n".join(lines)

    def build_query(self, categories: list[Category], circle: Circle) -> str:
        # around:радиус_в_метрах,широта,долгота — поиск в круговой области.
        area_filter = f"(around:{circle.radius_m:.0f},{circle.lat},{circle.lon})"
        body = self._selectors_body(categories, area_filter)
        # out center — координаты центра для way/relation; tags — все теги.
        return (
            f"[out:json][timeout:{self.timeout}];\n"
            f"(\n{body}\n);\n"
            f"out center tags;"
        )

    def build_polygon_query(self, categories: list[Category], poly: str) -> str:
        # poly:"lat1 lon1 lat2 lon2 ..." — поиск внутри произвольного полигона.
        body = self._selectors_body(categories, f'(poly:"{poly}")')
        return (
            f"[out:json][timeout:{self.timeout}];\n"
            f"(\n{body}\n);\n"
            f"out center tags;"
        )

    def build_area_query(self, categories: list[Category], area_id: int) -> str:
        # Поиск внутри административной границы (area). Сначала задаём область,
        # затем фильтруем объекты по принадлежности к ней.
        body = self._selectors_body(categories, "(area.searchArea)")
        return (
            f"[out:json][timeout:{self.timeout}];\n"
            f"area({area_id})->.searchArea;\n"
            f"(\n{body}\n);\n"
            f"out center tags;"
        )

    # ---- выполнение запроса -------------------------------------------------

    def _post(self, query: str) -> dict:
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._session.post(
                    self.endpoint, data={"data": query}, timeout=self.timeout
                )
                if resp.status_code == 429 or resp.status_code == 504:
                    # Слишком много запросов / таймаут шлюза — ждём и повторяем.
                    wait = self.pause * attempt * 5
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_err = exc
                time.sleep(self.pause * attempt)
        raise OverpassError(
            f"Overpass-запрос не выполнен после {self.max_retries} попыток: {last_err}"
        )

    # ---- разбор ответа ------------------------------------------------------

    @staticmethod
    def _coords(element: dict) -> tuple[float, float] | None:
        if element["type"] == "node":
            return element.get("lat"), element.get("lon")
        center = element.get("center")
        if center:
            return center.get("lat"), center.get("lon")
        return None

    @staticmethod
    def _address(tags: dict[str, str]) -> str | None:
        parts = [
            tags.get("addr:city"),
            tags.get("addr:street"),
            tags.get("addr:housenumber"),
        ]
        joined = ", ".join(p for p in parts if p)
        return joined or None

    def _to_poi(self, element: dict) -> POI | None:
        from ..categories import classify

        tags = element.get("tags", {})
        coords = self._coords(element)
        if not coords or coords[0] is None:
            return None
        cat = classify(tags)
        if cat is None:
            return None
        return POI(
            source=self.name,
            source_id=f"{element['type']}/{element['id']}",
            category=cat.key,
            group=cat.group,
            name=tags.get("name"),
            lat=float(coords[0]),
            lon=float(coords[1]),
            address=self._address(tags),
            phone=tags.get("phone") or tags.get("contact:phone"),
            website=tags.get("website") or tags.get("contact:website"),
            opening_hours=tags.get("opening_hours"),
            tags=tags,
        )

    # ---- публичный интерфейс ------------------------------------------------

    def _parse(self, data: dict) -> Iterable[POI]:
        seen: set[str] = set()
        for element in data.get("elements", []):
            poi = self._to_poi(element)
            if poi is None or poi.source_id in seen:
                continue
            seen.add(poi.source_id)
            yield poi

    def fetch(self, categories: list[Category], circle: Circle) -> Iterable[POI]:
        data = self._post(self.build_query(categories, circle))
        yield from self._parse(data)
        time.sleep(self.pause)

    def fetch_area(
        self, categories: list[Category], osm_type: str, osm_id: int
    ) -> Iterable[POI]:
        """Получить объекты внутри административной границы (по OSM relation/way)."""
        # Overpass area id: relation → 3600000000+id, way → 2400000000+id.
        if osm_type == "relation":
            area_id = 3_600_000_000 + osm_id
        elif osm_type == "way":
            area_id = 2_400_000_000 + osm_id
        else:
            raise OverpassError(
                f"У объекта типа {osm_type!r} нет площадной границы для поиска по area"
            )
        data = self._post(self.build_area_query(categories, area_id))
        yield from self._parse(data)
        time.sleep(self.pause)

    def fetch_polygon(
        self, categories: list[Category], ring: list[tuple[float, float]]
    ) -> Iterable[POI]:
        """Получить объекты внутри произвольного полигона (список точек lat, lon)."""
        if len(ring) < 3:
            raise OverpassError("Полигон должен содержать минимум 3 точки")
        poly = " ".join(f"{lat} {lon}" for lat, lon in ring)
        data = self._post(self.build_polygon_query(categories, poly))
        yield from self._parse(data)
        time.sleep(self.pause)
