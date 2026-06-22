"""Генерация интерактивной веб-карты (Leaflet) с кругом поиска и маркерами.

Результат — самодостаточный HTML-файл: данные встроены прямо в страницу,
поэтому он открывается двойным кликом и не требует веб-сервера. Leaflet
подгружается с CDN (нужен интернет при первом открытии).
"""

from __future__ import annotations

import json
from pathlib import Path

from .categories import all_categories
from .models import POI
from .sources.base import Circle

# Цвет маркеров по группам категорий.
GROUP_COLORS: dict[str, str] = {
    "education": "#1f78b4",  # синий
    "food": "#e31a1c",       # красный
    "sport": "#33a02c",      # зелёный
    "health": "#ff7f00",     # оранжевый
    "retail": "#6a3d9a",     # фиолетовый
    "transport": "#b15928",  # коричневый
    "recreation": "#b2df8a", # светло-зелёный (общественные пространства)
    "nature": "#1f9e89",     # бирюзовый
    "industry": "#7f7f7f",   # серый
}
DEFAULT_COLOR = "#555555"

_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Инфраструктура — карта</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body { margin: 0; height: 100%; }
  #map { height: 100%; }
  .legend, .info {
    background: rgba(255,255,255,0.92); padding: 8px 10px; border-radius: 6px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.3); font: 13px/1.4 sans-serif; color: #222;
  }
  .legend i { display: inline-block; width: 12px; height: 12px; margin-right: 6px;
    border-radius: 50%; vertical-align: middle; }
  .legend div { margin: 2px 0; }
  .popup-title { font-weight: 600; margin-bottom: 3px; }
  .popup-meta { color: #555; font-size: 12px; }
  .md-btn {
    background: #2d6cdf; color: #fff; border: none; padding: 8px 12px;
    border-radius: 6px; font: 13px sans-serif; cursor: pointer;
    box-shadow: 0 1px 4px rgba(0,0,0,0.3);
  }
  .md-btn:hover { background: #1f55b8; }
</style>
</head>
<body>
<div id="map"></div>
<script>
const DATA = __DATA__;

const map = L.map('map');
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

// Круг поиска
const circle = L.circle(DATA.center, {
  radius: DATA.radius_m, color: '#000', weight: 1.5,
  fillColor: '#000', fillOpacity: 0.04
}).addTo(map);
L.marker(DATA.center).addTo(map).bindPopup('Центр поиска');
map.fitBounds(circle.getBounds());

// Маркеры по группам (каждая группа — отдельный переключаемый слой)
const layers = {};
function colorFor(group) { return DATA.groupColors[group] || DATA.defaultColor; }

function popupHtml(p) {
  const title = p.name || DATA.titles[p.category] || p.category;
  let html = '<div class="popup-title">' + escapeHtml(title) + '</div>';
  html += '<div class="popup-meta">' + escapeHtml(DATA.titles[p.category] || p.category) + '</div>';
  if (p.address) html += '<div class="popup-meta">' + escapeHtml(p.address) + '</div>';
  if (p.phone) html += '<div class="popup-meta">☎ ' + escapeHtml(p.phone) + '</div>';
  if (p.opening_hours) html += '<div class="popup-meta">🕒 ' + escapeHtml(p.opening_hours) + '</div>';
  if (p.website) html += '<div class="popup-meta"><a href="' + encodeURI(p.website) +
    '" target="_blank" rel="noopener">сайт</a></div>';
  return html;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

for (const f of DATA.features) {
  const p = f.properties, c = f.geometry.coordinates; // [lon, lat]
  const group = p.group;
  if (!layers[group]) layers[group] = L.layerGroup().addTo(map);
  L.circleMarker([c[1], c[0]], {
    radius: 5, color: '#fff', weight: 1,
    fillColor: colorFor(group), fillOpacity: 0.9
  }).bindPopup(popupHtml(p)).addTo(layers[group]);
}

// Переключатель слоёв по группам (с количеством)
const counts = {};
for (const f of DATA.features) counts[f.properties.group] = (counts[f.properties.group]||0)+1;
const overlays = {};
for (const g of Object.keys(layers)) {
  overlays['<span style="color:' + colorFor(g) + '">●</span> ' + g + ' (' + counts[g] + ')'] = layers[g];
}
L.control.layers(null, overlays, { collapsed: false }).addTo(map);

// Легенда
const legend = L.control({ position: 'bottomright' });
legend.onAdd = function () {
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = '<div><b>Группы</b></div>';
  for (const g of Object.keys(DATA.groupColors)) {
    if (counts[g]) div.innerHTML +=
      '<div><i style="background:' + DATA.groupColors[g] + '"></i>' + g + '</div>';
  }
  return div;
};
legend.addTo(map);

// Кнопка выгрузки в Markdown (генерация на стороне браузера)
function mdCell(s) {
  return String(s == null ? '' : s).replace(/\\|/g, '\\\\|').replace(/[\\r\\n]+/g, ' ').trim();
}

function buildMarkdown() {
  const d = DATA;
  const lines = [];
  lines.push('# Инфраструктура в радиусе ' + (d.radius_m / 1000) + ' км');
  lines.push('');
  lines.push('- **Центр:** ' + d.center[0] + ', ' + d.center[1]);
  lines.push('- **Радиус:** ' + (d.radius_m / 1000) + ' км');
  lines.push('- **Всего объектов:** ' + d.features.length);
  lines.push('');

  // Группировка: группа -> категория -> объекты
  const byGroup = {};
  for (const f of d.features) {
    const p = f.properties;
    (byGroup[p.group] = byGroup[p.group] || {});
    (byGroup[p.group][p.category] = byGroup[p.group][p.category] || []).push(f);
  }

  // Сводка
  lines.push('## Сводка');
  lines.push('');
  lines.push('| Категория | Объектов |');
  lines.push('| --- | ---: |');
  const catCounts = {};
  for (const f of d.features) catCounts[f.properties.category] = (catCounts[f.properties.category]||0)+1;
  Object.keys(catCounts).sort((a,b) => catCounts[b]-catCounts[a]).forEach(c => {
    lines.push('| ' + mdCell(d.titles[c] || c) + ' | ' + catCounts[c] + ' |');
  });
  lines.push('');

  // Детализация
  for (const g of Object.keys(byGroup).sort()) {
    lines.push('## ' + mdCell(g));
    lines.push('');
    for (const cat of Object.keys(byGroup[g]).sort()) {
      const items = byGroup[g][cat];
      lines.push('### ' + mdCell(d.titles[cat] || cat) + ' (' + items.length + ')');
      lines.push('');
      lines.push('| Название | Координаты | Адрес | Телефон | Часы | Сайт |');
      lines.push('| --- | --- | --- | --- | --- | --- |');
      items.sort((a,b) => (a.properties.name||'').localeCompare(b.properties.name||'', 'ru'));
      for (const f of items) {
        const p = f.properties, c = f.geometry.coordinates; // [lon, lat]
        const coord = c[1].toFixed(6) + ', ' + c[0].toFixed(6);
        const site = p.website ? '[ссылка](' + encodeURI(p.website) + ')' : '';
        lines.push('| ' + mdCell(p.name || '—') + ' | ' + coord + ' | ' + mdCell(p.address) + ' | ' +
          mdCell(p.phone) + ' | ' + mdCell(p.opening_hours) + ' | ' + site + ' |');
      }
      lines.push('');
    }
  }
  return lines.join('\\n');
}

function downloadMarkdown() {
  const blob = new Blob([buildMarkdown()], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'infrastructure.md';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const mdControl = L.control({ position: 'topleft' });
mdControl.onAdd = function () {
  const div = L.DomUtil.create('div');
  const btn = L.DomUtil.create('button', 'md-btn', div);
  btn.innerHTML = '⬇ Скачать .md';
  btn.title = 'Выгрузить все объекты в Markdown';
  L.DomEvent.disableClickPropagation(div);
  L.DomEvent.on(btn, 'click', downloadMarkdown);
  return div;
};
mdControl.addTo(map);

// Инфо-панель
const info = L.control({ position: 'topright' });
info.onAdd = function () {
  const div = L.DomUtil.create('div', 'info');
  div.innerHTML = '<b>Объектов:</b> ' + DATA.features.length +
    '<br><b>Радиус:</b> ' + (DATA.radius_m/1000) + ' км';
  return div;
};
info.addTo(map);
</script>
</body>
</html>
"""


def export_map(pois: list[POI], circle: Circle, path: str | Path) -> int:
    """Сгенерировать HTML-карту с кругом поиска и маркерами объектов."""
    titles = {c.key: c.title for c in all_categories()}
    data = {
        "center": [circle.lat, circle.lon],
        "radius_m": circle.radius_m,
        "features": [p.as_geojson_feature() for p in pois],
        "groupColors": GROUP_COLORS,
        "defaultColor": DEFAULT_COLOR,
        "titles": titles,
    }
    html = _TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    Path(path).write_text(html, encoding="utf-8")
    return len(pois)
