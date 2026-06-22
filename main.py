"""CLI парсера инфраструктурных объектов с OpenStreetMap.

Модель: задаётся центральная точка (координатами или названием места) и радиус,
после чего анализируется вся инфраструктура в этом круге.

Примеры:
    # Список доступных категорий
    python main.py --list-categories

    # Вся инфраструктура в радиусе 2 км от координаты
    python main.py --coords 55.751,37.618 --radius 2

    # Школы и детсады в радиусе 1 км от места (по названию)
    python main.py --place "Казань, Кремль" --radius 1 -c school kindergarten

    # Коммерция в радиусе 5 км + экспорт и анализ по кольцам
    python main.py --place "Москва, Арбат" --radius 5 -c food sport retail \\
        --geojson out.geojson --rings 5
"""

from __future__ import annotations

import argparse
import sys

# На Windows консоль часто использует cp1251 — принудительно переключаем
# ввод/вывод на UTF-8, чтобы кириллица не превращалась в «кракозябры».
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass

from osm_parser import analytics, categories
from osm_parser.geocode import GeocodeError, geocode
from osm_parser.sources import OverpassSource
from osm_parser.sources.base import PRESET_RADII_KM, Circle
from osm_parser.storage import Storage, export_csv, export_geojson
from osm_parser.webmap import export_map


def cmd_list_categories() -> None:
    print("Доступные категории (ключ — группа — название):\n")
    for c in categories.all_categories():
        alias = f"  [алиасы: {', '.join(c.aliases)}]" if c.aliases else ""
        print(f"  {c.key:<14} {c.group:<11} {c.title}{alias}")
    print(f"\nГруппы (можно указывать целиком): {', '.join(categories.all_groups())}")
    print("Спец-значение 'all' — все категории.")


def build_parser() -> argparse.ArgumentParser:
    presets = "/".join(f"{r:g}" for r in PRESET_RADII_KM)
    p = argparse.ArgumentParser(
        description="Парсер инфраструктурных объектов OpenStreetMap (центр + радиус)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--list-categories", action="store_true",
                   help="показать доступные категории и выйти")

    center = p.add_argument_group("центр поиска (задать одно из двух)")
    center.add_argument("--coords", metavar="LAT,LON",
                        help="координаты центра, напр. 55.751,37.618")
    center.add_argument("--place", metavar="НАЗВАНИЕ",
                        help="название места/адрес (геокодинг через Nominatim)")

    p.add_argument("--radius", "-r", type=float, default=2.0, metavar="КМ",
                   help=f"радиус поиска в км (пресеты: {presets}; по умолчанию 2)")
    p.add_argument("--categories", "-c", nargs="+", metavar="CAT",
                   help="категории/группы/'all' (по умолчанию: all)")

    out = p.add_argument_group("вывод")
    out.add_argument("--db", default="osm_poi.db", help="путь к SQLite БД (по умолчанию osm_poi.db)")
    out.add_argument("--no-db", action="store_true", help="не писать в БД")
    out.add_argument("--geojson", help="экспорт в GeoJSON-файл")
    out.add_argument("--csv", help="экспорт в CSV-файл")
    out.add_argument("--map", dest="map_html", metavar="FILE.html",
                     help="интерактивная веб-карта (Leaflet) с кругом и маркерами")
    out.add_argument("--rings", type=int, default=5, metavar="N",
                     help="число колец для анализа удалённости (по умолчанию 5)")

    hist = p.add_argument_group("история поиска")
    hist.add_argument("--history", action="store_true",
                      help="показать историю поисков и выйти")
    hist.add_argument("--rename", nargs=2, metavar=("ID", "ИМЯ"),
                      help="переименовать запись истории по её ID")
    hist.add_argument("--rerun", type=int, metavar="ID",
                      help="повторить поиск из истории по его ID")
    hist.add_argument("--delete", type=int, metavar="ID",
                      help="удалить запись истории по её ID")
    hist.add_argument("--name", metavar="ИМЯ",
                      help="задать имя для записи истории текущего поиска")

    p.add_argument("--endpoint", help="свой Overpass endpoint")
    return p


def resolve_center(args) -> Circle | None:
    """Определить круг поиска из --coords или --place. None при ошибке."""
    if args.coords and args.place:
        print("Ошибка: укажите либо --coords, либо --place, но не оба.", file=sys.stderr)
        return None
    if args.radius <= 0:
        print("Ошибка: радиус должен быть положительным.", file=sys.stderr)
        return None

    if args.coords:
        try:
            return Circle.from_coords(args.coords, args.radius)
        except ValueError as exc:
            print(f"Ошибка в --coords: {exc}", file=sys.stderr)
            return None

    # --place: геокодим название в координаты
    try:
        place = geocode(args.place)
    except GeocodeError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return None
    print(f"Центр найден: {place.display_name} ({place.lat:.5f}, {place.lon:.5f})",
          file=sys.stderr)
    circle = Circle(place.lat, place.lon, args.radius * 1000.0)
    circle.validate()
    return circle


def cmd_history(db_path: str) -> int:
    with Storage(db_path) as store:
        rows = store.list_searches()
    if not rows:
        print("История пуста.")
        return 0
    print("История поисков (свежие сверху):\n")
    print(f"  {'ID':>4}  {'дата':<19}  {'объектов':>8}  имя")
    print(f"  {'-' * 70}")
    for r in rows:
        print(f"  {r['id']:>4}  {r['created_at']:<19}  {r['result_count']:>8}  {r['name']}")
    print("\nПовторить поиск: --rerun ID   |   переименовать: --rename ID \"новое имя\"")
    return 0


def cmd_rename(db_path: str, id_str: str, new_name: str) -> int:
    try:
        search_id = int(id_str)
    except ValueError:
        print(f"Ошибка: ID должен быть числом, получено {id_str!r}", file=sys.stderr)
        return 2
    with Storage(db_path) as store:
        ok = store.rename_search(search_id, new_name)
    if not ok:
        print(f"Ошибка: запись истории #{search_id} не найдена.", file=sys.stderr)
        return 1
    print(f"Запись #{search_id} переименована: «{new_name}»")
    return 0


def run_search(args, circle: Circle, cats, place: str | None) -> int:
    """Выполнить поиск, сохранить, экспортировать, записать в историю."""
    source = OverpassSource(endpoint=args.endpoint) if args.endpoint else OverpassSource()

    print(f"Запрос к OpenStreetMap: {len(cats)} категорий в радиусе "
          f"{circle.radius_km:g} км от ({circle.lat:.5f}, {circle.lon:.5f})…",
          file=sys.stderr)
    try:
        pois = list(source.fetch(cats, circle))
    except Exception as exc:  # noqa: BLE001 — наверх показываем понятную ошибку
        print(f"Ошибка запроса: {exc}", file=sys.stderr)
        return 1

    print(f"Получено объектов: {len(pois)}", file=sys.stderr)

    # БД: сохраняем объекты (если не --no-db) и всегда пишем запись в историю.
    with Storage(args.db) as store:
        if not args.no_db:
            saved = store.save(pois)
            print(f"Сохранено в БД {args.db}: {saved} (всего в базе: {store.count()})",
                  file=sys.stderr)
        sid = store.record_search(
            place=place,
            center_lat=circle.lat,
            center_lon=circle.lon,
            radius_m=circle.radius_m,
            categories=[c.key for c in cats],
            result_count=len(pois),
            name=args.name,
        )
        print(f"Записано в историю под ID {sid}.", file=sys.stderr)

    if args.geojson:
        n = export_geojson(pois, args.geojson)
        print(f"Экспорт GeoJSON: {n} → {args.geojson}", file=sys.stderr)
    if args.csv:
        n = export_csv(pois, args.csv)
        print(f"Экспорт CSV: {n} → {args.csv}", file=sys.stderr)
    if args.map_html:
        n = export_map(pois, circle, args.map_html)
        print(f"Веб-карта: {n} объектов → {args.map_html}", file=sys.stderr)

    print("\n" + "=" * 50)
    print(analytics.summarize(pois, circle.area_km2()).render())
    if args.rings > 0 and pois:
        print("\n" + "=" * 50)
        print(analytics.ring_analysis(pois, circle, rings=args.rings).render())

    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_categories:
        cmd_list_categories()
        return 0
    if args.history:
        return cmd_history(args.db)
    if args.rename:
        return cmd_rename(args.db, args.rename[0], args.rename[1])
    if args.delete is not None:
        with Storage(args.db) as store:
            ok = store.delete_search(args.delete)
        if not ok:
            print(f"Ошибка: запись истории #{args.delete} не найдена.", file=sys.stderr)
            return 1
        print(f"Запись #{args.delete} удалена.")
        return 0

    # Повтор поиска из истории: восстанавливаем параметры и игнорируем center/--*.
    if args.rerun is not None:
        with Storage(args.db) as store:
            rec = store.get_search(args.rerun)
        if rec is None:
            print(f"Ошибка: запись истории #{args.rerun} не найдена.", file=sys.stderr)
            return 1
        circle = Circle(rec["center_lat"], rec["center_lon"], rec["radius_m"])
        try:
            cats = categories.resolve(rec["categories"].split(","))
        except ValueError as exc:
            print(f"Ошибка: {exc}", file=sys.stderr)
            return 1
        print(f"Повтор поиска #{args.rerun}: «{rec['name']}»", file=sys.stderr)
        return run_search(args, circle, cats, rec["place"])

    if not args.coords and not args.place:
        print("Ошибка: укажите --coords или --place "
              "(см. также --list-categories, --history).", file=sys.stderr)
        return 2

    try:
        cats = categories.resolve(args.categories)
    except ValueError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    circle = resolve_center(args)
    if circle is None:
        return 2

    return run_search(args, circle, cats, args.place)


if __name__ == "__main__":
    raise SystemExit(main())
