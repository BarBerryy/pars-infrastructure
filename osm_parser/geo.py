"""Геометрические утилиты: расстояния и преобразования координат."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками на сфере в метрах."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _ring_area_km2(ring: list, kx: float, ky: float) -> float:
    """Площадь одного кольца полигона (формула шнурков) в проекции км."""
    n = len(ring)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = ring[i][0] * kx, ring[i][1] * ky
        x2, y2 = ring[(i + 1) % n][0] * kx, ring[(i + 1) % n][1] * ky
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def polygon_area_km2(geometry: dict) -> float:
    """Площадь GeoJSON-полигона (Polygon/MultiPolygon) в км².

    Используется равнопромежуточная проекция вокруг средней широты — для
    городов/районов погрешность мала. Внешние кольца суммируются, дыры вычитаются.
    """
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        polys = [coords]
    elif gtype == "MultiPolygon":
        polys = coords
    else:
        return 0.0

    lats = [pt[1] for poly in polys for ring in poly for pt in ring]
    if not lats:
        return 0.0
    lat0 = sum(lats) / len(lats)
    kx = 111.320 * math.cos(math.radians(lat0))
    ky = 110.574

    total = 0.0
    for poly in polys:
        for i, ring in enumerate(poly):
            area = _ring_area_km2(ring, kx, ky)
            total += area if i == 0 else -area  # первое кольцо — внешнее, остальные — дыры
    return abs(total)
