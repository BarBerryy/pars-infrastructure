"""Абстрактный интерфейс источника данных и геометрия области поиска.

Любой новый сервис (2GIS, Yandex, Google Places) должен реализовать DataSource,
после чего станет доступен остальному приложению без изменений в storage/analytics.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable

from ..categories import Category
from ..models import POI

# Готовые («пресетные») радиусы поиска в километрах.
PRESET_RADII_KM: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0)

_M_PER_DEG_LAT = 111_320.0


def _m_per_deg_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


@dataclass(frozen=True)
class BBox:
    """Прямоугольная область (широта/долгота в градусах). Используется как
    описывающий прямоугольник круга — например, для экспорта или индексов."""

    south: float
    west: float
    north: float
    east: float


@dataclass(frozen=True)
class Circle:
    """Круговая область поиска: центр (lat, lon) и радиус в метрах."""

    lat: float
    lon: float
    radius_m: float

    def validate(self) -> None:
        if not (-90 <= self.lat <= 90):
            raise ValueError(f"Широта вне диапазона: {self.lat}")
        if not (-180 <= self.lon <= 180):
            raise ValueError(f"Долгота вне диапазона: {self.lon}")
        if self.radius_m <= 0:
            raise ValueError(f"Радиус должен быть положительным: {self.radius_m}")

    @property
    def radius_km(self) -> float:
        return self.radius_m / 1000.0

    def area_km2(self) -> float:
        return math.pi * self.radius_km ** 2

    def bounding_box(self) -> BBox:
        dlat = self.radius_m / _M_PER_DEG_LAT
        dlon = self.radius_m / _m_per_deg_lon(self.lat)
        return BBox(
            south=max(self.lat - dlat, -90),
            west=max(self.lon - dlon, -180),
            north=min(self.lat + dlat, 90),
            east=min(self.lon + dlon, 180),
        )

    @classmethod
    def from_coords(cls, coords: str, radius_km: float) -> "Circle":
        """Создать круг из строки 'lat,lon' и радиуса в километрах."""
        parts = [p.strip() for p in coords.split(",")]
        if len(parts) != 2:
            raise ValueError("Координаты должны быть в формате 'lat,lon'")
        circle = cls(float(parts[0]), float(parts[1]), radius_km * 1000.0)
        circle.validate()
        return circle


class DataSource(ABC):
    """Базовый класс источника инфраструктурных данных."""

    name: str = "abstract"

    @abstractmethod
    def fetch(self, categories: list[Category], circle: Circle) -> Iterable[POI]:
        """Получить объекты заданных категорий в круговой области."""
        raise NotImplementedError
