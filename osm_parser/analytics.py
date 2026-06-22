"""Аналитика по собранным объектам: статистика, плотность, кольца удалённости.

Поиск идёт по кругу вокруг заданной точки, поэтому естественная разбивка —
концентрические кольца (0–1 км, 1–2 км …): видно, как насыщенность
инфраструктурой меняется по мере удаления от центра.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .geo import haversine_m
from .models import POI
from .sources.base import Circle


@dataclass
class Summary:
    total: int
    by_group: dict[str, int]
    by_category: dict[str, int]
    area_km2: float
    density_per_km2: dict[str, float]

    def render(self) -> str:
        lines = [
            f"Всего объектов: {self.total}",
            f"Площадь круга: {self.area_km2:.1f} км²",
            "\nПо группам:",
        ]
        for g, n in sorted(self.by_group.items(), key=lambda x: -x[1]):
            lines.append(f"  {g:<12} {n:>6}")
        lines.append("\nПо категориям:")
        for c, n in sorted(self.by_category.items(), key=lambda x: -x[1]):
            lines.append(f"  {c:<14} {n:>6}   ({self.density_per_km2.get(c, 0):.2f} /км²)")
        return "\n".join(lines)


def summarize(pois: list[POI], area_km2: float) -> Summary:
    by_group = Counter(p.group for p in pois)
    by_category = Counter(p.category for p in pois)
    area = area_km2
    density = {c: n / area for c, n in by_category.items()} if area > 0 else {}
    return Summary(
        total=len(pois),
        by_group=dict(by_group),
        by_category=dict(by_category),
        area_km2=area,
        density_per_km2=density,
    )


@dataclass
class Ring:
    inner_km: float
    outer_km: float
    count: int
    area_km2: float

    @property
    def density(self) -> float:
        return self.count / self.area_km2 if self.area_km2 > 0 else 0.0


@dataclass
class RingAnalysis:
    rings: list[Ring]
    beyond: int  # объектов за пределами радиуса (обычно 0)

    def render(self) -> str:
        lines = ["Распределение по кольцам удалённости от центра:", ""]
        lines.append(f"  {'кольцо, км':<14}{'объектов':>10}{'плотн. /км²':>14}")
        lines.append(f"  {'-' * 36}")
        peak = max((r.count for r in self.rings), default=0)
        for r in self.rings:
            bar = "█" * round(20 * r.count / peak) if peak else ""
            label = f"{r.inner_km:g}–{r.outer_km:g}"
            lines.append(f"  {label:<14}{r.count:>10}{r.density:>14.2f}  {bar}")
        if self.beyond:
            lines.append(f"  (за радиусом: {self.beyond})")
        return "\n".join(lines)


def ring_analysis(pois: list[POI], circle: Circle, rings: int = 5) -> RingAnalysis:
    """Разбить круг на `rings` колец равной ширины и посчитать объекты в каждом.

    Площадь кольца — разность площадей кругов (кольцо/annulus), поэтому
    плотность корректна и сопоставима между кольцами.
    """
    import math

    width_km = circle.radius_km / rings
    ring_objs = [0] * rings
    beyond = 0
    for p in pois:
        dist_km = haversine_m(circle.lat, circle.lon, p.lat, p.lon) / 1000.0
        idx = int(dist_km / width_km)
        if idx >= rings:
            # На границе из-за погрешности возможен выход за радиус.
            if dist_km <= circle.radius_km * 1.001:
                ring_objs[rings - 1] += 1
            else:
                beyond += 1
        else:
            ring_objs[idx] += 1

    result: list[Ring] = []
    for i in range(rings):
        inner = i * width_km
        outer = (i + 1) * width_km
        area = math.pi * (outer ** 2 - inner ** 2)
        result.append(Ring(inner, outer, ring_objs[i], area))
    return RingAnalysis(result, beyond)
