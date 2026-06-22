"""Геокодинг через Nominatim — поиск координат по названию места.

Nominatim — бесплатный сервис геокодинга на данных OSM. Публичный инстанс
требует обязательный User-Agent и ограничивает частоту запросов (не чаще
1 запроса в секунду). Документация: https://nominatim.org/release-docs/latest/api/Search/
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "pars-openstreetmap/0.1 (infrastructure POI parser)"


class GeocodeError(RuntimeError):
    pass


@dataclass
class Place:
    lat: float
    lon: float
    display_name: str


@dataclass
class AreaPlace:
    """Место с административной границей (для поиска «по всему городу»)."""

    lat: float
    lon: float
    display_name: str
    osm_type: str          # 'relation' | 'way' | 'node'
    osm_id: int
    geojson: dict | None   # геометрия границы (Polygon/MultiPolygon) или None


def _request(params: dict, query: str, timeout: int) -> list:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru"}
    try:
        resp = requests.get(NOMINATIM_ENDPOINT, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeocodeError(f"Ошибка геокодинга {query!r}: {exc}") from exc


def geocode(query: str, timeout: int = 30) -> Place:
    """Найти координаты места по текстовому запросу (берётся лучший результат)."""
    results = _request({"q": query, "format": "jsonv2", "limit": 1}, query, timeout)
    if not results:
        raise GeocodeError(f"Место не найдено: {query!r}")
    top = results[0]
    return Place(
        lat=float(top["lat"]),
        lon=float(top["lon"]),
        display_name=top.get("display_name", query),
    )


def geocode_area(query: str, timeout: int = 45) -> AreaPlace:
    """Найти место вместе с его границей (полигоном) для поиска по всей территории.

    Среди результатов выбирается первый, у которого есть полигональная граница
    (город/район), а не точка.
    """
    results = _request(
        {"q": query, "format": "jsonv2", "limit": 5, "polygon_geojson": 1},
        query, timeout,
    )
    if not results:
        raise GeocodeError(f"Место не найдено: {query!r}")

    # Предпочитаем результат с полигональной границей.
    chosen = None
    for r in results:
        geom = r.get("geojson") or {}
        if geom.get("type") in ("Polygon", "MultiPolygon"):
            chosen = r
            break
    if chosen is None:
        chosen = results[0]

    geom = chosen.get("geojson") or {}
    return AreaPlace(
        lat=float(chosen["lat"]),
        lon=float(chosen["lon"]),
        display_name=chosen.get("display_name", query),
        osm_type=chosen.get("osm_type", ""),
        osm_id=int(chosen.get("osm_id", 0)),
        geojson=geom if geom.get("type") in ("Polygon", "MultiPolygon") else None,
    )
