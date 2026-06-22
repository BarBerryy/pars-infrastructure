"""Единая модель инфраструктурного объекта (POI), не зависящая от источника."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class POI:
    """Точка интереса — нормализованное представление объекта с карты."""

    source: str                 # источник данных, напр. "osm"
    source_id: str              # идентификатор в источнике (тип+id для OSM)
    category: str               # ключ категории из categories.py
    group: str                  # группа категории
    name: str | None            # название (может отсутствовать)
    lat: float
    lon: float
    # Контактные/адресные данные — заполняются по мере доступности
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    opening_hours: str | None = None
    # Сырые теги источника для отладки/обогащения
    tags: dict[str, str] = field(default_factory=dict)

    def as_row(self) -> dict:
        """Плоское представление для записи в БД/CSV."""
        return {
            "source": self.source,
            "source_id": self.source_id,
            "category": self.category,
            "group": self.group,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "address": self.address,
            "phone": self.phone,
            "website": self.website,
            "opening_hours": self.opening_hours,
        }

    def as_geojson_feature(self) -> dict:
        """Представление в виде GeoJSON Feature (для карт/ГИС)."""
        props = self.as_row()
        props.pop("lat")
        props.pop("lon")
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [self.lon, self.lat]},
            "properties": props,
        }
