"""Таксономия инфраструктурных объектов и её привязка к тегам OpenStreetMap.

Каждая категория описывается набором OSM-селекторов вида (ключ, значение).
Объект попадает в категорию, если у него присутствует хотя бы один из селекторов.

Чтобы добавить новый тип объекта — допиши категорию в CATEGORIES.
Справочник тегов: https://wiki.openstreetmap.org/wiki/Map_features
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Category:
    key: str                       # машинное имя, напр. "school"
    group: str                     # группа, напр. "education"
    title: str                     # человекочитаемое название
    selectors: tuple[tuple[str, str], ...]  # OSM-теги (key, value)
    aliases: tuple[str, ...] = field(default=())  # доп. имена для CLI


# Порядок важен только для вывода. Селекторы подобраны под реалии РФ/СНГ.
CATEGORIES: tuple[Category, ...] = (
    # --- Образование ---
    Category("school", "education", "Школы",
             (("amenity", "school"),)),
    Category("kindergarten", "education", "Детские сады",
             (("amenity", "kindergarten"),), aliases=("детсад", "садик")),
    Category("university", "education", "Вузы",
             (("amenity", "university"),)),
    Category("college", "education", "Колледжи/техникумы",
             (("amenity", "college"),)),

    # --- Питание (коммерция) ---
    Category("cafe", "food", "Кофейни/кафе",
             (("amenity", "cafe"), ("shop", "coffee")), aliases=("coffee", "кофейня")),
    Category("restaurant", "food", "Рестораны",
             (("amenity", "restaurant"),)),
    Category("fast_food", "food", "Фастфуд",
             (("amenity", "fast_food"),)),
    Category("bar", "food", "Бары/пабы",
             (("amenity", "bar"), ("amenity", "pub"))),

    # --- Спорт (коммерция) ---
    Category("fitness", "sport", "Фитнес/спортзалы",
             (("leisure", "fitness_centre"), ("leisure", "sport_centre")),
             aliases=("gym", "спортзал", "фитнес")),
    Category("swimming", "sport", "Бассейны",
             (("leisure", "swimming_pool"), ("sport", "swimming"))),

    # --- Здоровье (коммерция/инфраструктура) ---
    Category("pharmacy", "health", "Аптеки",
             (("amenity", "pharmacy"),)),
    Category("clinic", "health", "Клиники/поликлиники",
             (("amenity", "clinic"), ("amenity", "doctors"))),
    Category("dentist", "health", "Стоматологии",
             (("amenity", "dentist"),)),
    Category("hospital", "health", "Больницы",
             (("amenity", "hospital"),)),

    # --- Торговля (коммерция) ---
    Category("supermarket", "retail", "Супермаркеты",
             (("shop", "supermarket"),)),
    Category("convenience", "retail", "Магазины у дома",
             (("shop", "convenience"),)),
    Category("mall", "retail", "Торговые центры",
             (("shop", "mall"),)),
    Category("beauty", "retail", "Салоны красоты/парикмахерские",
             (("shop", "hairdresser"), ("shop", "beauty"))),

    # --- Транспорт (общественные объекты) ---
    # metro идёт раньше railway_station: станции метро часто имеют railway=station,
    # и classify() должен относить их к «метро», а не к ж/д станциям.
    Category("metro", "transport", "Станции метро",
             (("station", "subway"),), aliases=("метро", "subway")),
    Category("railway_station", "transport", "Ж/д станции/вокзалы",
             (("railway", "station"),)),
    Category("bus_station", "transport", "Автовокзалы",
             (("amenity", "bus_station"),)),

    # --- Отдых и общественные пространства ---
    Category("park", "recreation", "Парки",
             (("leisure", "park"),), aliases=("парк",)),
    Category("playground", "recreation", "Детские площадки",
             (("leisure", "playground"),)),
    Category("stadium", "recreation", "Стадионы",
             (("leisure", "stadium"),)),

    # --- Природа ---
    Category("river", "nature", "Реки",
             (("waterway", "river"), ("waterway", "canal")), aliases=("река",)),
    Category("water", "nature", "Водоёмы (озёра/пруды)",
             (("natural", "water"),)),
    Category("forest", "nature", "Леса/лесопарки",
             (("natural", "wood"), ("landuse", "forest"))),

    # --- Промышленность ---
    Category("factory", "industry", "Заводы/промзоны",
             (("man_made", "works"), ("landuse", "industrial")),
             aliases=("завод", "промзона")),
)

# Быстрый доступ по ключу/алиасу
_BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
_BY_ANY: dict[str, Category] = {}
for _c in CATEGORIES:
    _BY_ANY[_c.key] = _c
    for _a in _c.aliases:
        _BY_ANY[_a.lower()] = _c


def all_categories() -> tuple[Category, ...]:
    return CATEGORIES


def all_groups() -> list[str]:
    seen: list[str] = []
    for c in CATEGORIES:
        if c.group not in seen:
            seen.append(c.group)
    return seen


def get(name: str) -> Category | None:
    """Найти категорию по ключу или алиасу (регистронезависимо)."""
    return _BY_ANY.get(name.lower())


def resolve(names: list[str] | None) -> list[Category]:
    """Преобразовать имена категорий/групп в список Category.

    Поддерживает: ключи категорий, алиасы, имена групп и спец-значение "all".
    Неизвестные имена вызывают ValueError со списком допустимых вариантов.
    """
    if not names or names == ["all"]:
        return list(CATEGORIES)

    result: list[Category] = []
    groups = set(all_groups())
    for name in names:
        low = name.lower()
        if low in groups:
            result.extend(c for c in CATEGORIES if c.group == low)
        elif (cat := get(low)) is not None:
            result.append(cat)
        else:
            valid = ", ".join(c.key for c in CATEGORIES)
            raise ValueError(
                f"Неизвестная категория/группа: {name!r}. "
                f"Доступно: {valid}; группы: {', '.join(groups)}; либо 'all'."
            )

    # dedup с сохранением порядка
    out: list[Category] = []
    for c in result:
        if c not in out:
            out.append(c)
    return out


def classify(tags: dict[str, str]) -> Category | None:
    """Определить категорию объекта по его OSM-тегам (первое совпадение)."""
    for cat in CATEGORIES:
        for k, v in cat.selectors:
            if tags.get(k) == v:
                return cat
    return None
