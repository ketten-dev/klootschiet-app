#!/usr/bin/env python3
"""Maakt route.svg en de routelijst in index.html uit de Google My Maps-kaart (KML).

Gebruik:  python3 tools/route_svg.py            (haalt de KML online op)
          python3 tools/route_svg.py kaart.kml  (lokaal bestand)

- Lijnen uit de kaart worden doorgetrokken getekend.
- Gaten tussen opeenvolgende lijnen (stukken die Google niet kent)
  worden gestippeld aangevuld.
- Alleen de zelf benoemde punten (blauwe markers) komen op de kaart;
  de automatisch toegevoegde adres-markers van routes worden overgeslagen.
- Naam en beschrijving van elk punt komen in index.html tussen
  <!-- route:start --> en <!-- route:end -->.
"""
import html
import re
import math
import sys
import urllib.request
import xml.etree.ElementTree as ET

MAP_ID = '1GWpJKJcyX5PjGuHJzG13yZkYYQDCbX4'
KML_URL = f'https://www.google.com/maps/d/kml?mid={MAP_ID}&forcekml=1'
OUT = 'route.svg'
HTML = 'index.html'
POINT_STYLE = '#icon-1899-0288D1'   # blauwe markers = eigen punten
GAP_M = 15                          # kleiner gat wordt niet gestippeld

NS = {'k': 'http://www.opengis.net/kml/2.2'}


def load_kml():
    if len(sys.argv) > 1:
        return ET.parse(sys.argv[1]).getroot()
    with urllib.request.urlopen(KML_URL) as r:
        return ET.fromstring(r.read())


def coords(el):
    text = el.find('.//k:coordinates', NS).text
    return [tuple(map(float, c.split(',')[:2])) for c in text.split()]


def main():
    root = load_kml()
    lines, points = [], []
    for pm in root.iter('{%s}Placemark' % NS['k']):
        style = pm.findtext('k:styleUrl', default='', namespaces=NS)
        name = (pm.findtext('k:name', default='', namespaces=NS) or '').strip()
        desc = (pm.findtext('k:description', default='', namespaces=NS) or '').strip()
        if pm.find('.//k:LineString', NS) is not None:
            lines.append(coords(pm))
        elif pm.find('.//k:Point', NS) is not None and style.startswith(POINT_STYLE):
            points.append((name, coords(pm)[0], desc))

    # Lokale projectie in meters (equirectangulair, ruim nauwkeurig genoeg voor ~1 km)
    allpts = [p for l in lines for p in l] + [p for _, p, _ in points]
    lat0 = sum(p[1] for p in allpts) / len(allpts)
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540

    def m(p):
        return (p[0] * kx, -p[1] * ky)

    xs, ys = zip(*(m(p) for p in allpts))
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    W, pad = 400, 40
    s = (W - 2 * pad) / max(maxx - minx, maxy - miny)
    H = round((maxy - miny) * s + 2 * pad)

    def xy(p):
        x, y = m(p)
        return (pad + (x - minx) * s, pad + (y - miny) * s)

    def path(pts):
        return ' '.join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}'
                        for i, (x, y) in enumerate(map(xy, pts)))

    def dist(a, b):
        (ax, ay), (bx, by) = m(a), m(b)
        return math.hypot(ax - bx, ay - by)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="system-ui, sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#f8fafc"/>']
    total = 0
    for i, l in enumerate(lines):
        total += sum(dist(a, b) for a, b in zip(l, l[1:]))
        out.append(f'<path d="{path(l)}" fill="none" stroke="#059669" stroke-width="5" '
                   'stroke-linecap="round" stroke-linejoin="round"/>')
        if i + 1 < len(lines) and dist(l[-1], lines[i + 1][0]) > GAP_M:
            total += dist(l[-1], lines[i + 1][0])
            out.append(f'<path d="{path([l[-1], lines[i + 1][0]])}" fill="none" stroke="#059669" '
                       'stroke-width="4" stroke-dasharray="2 8" stroke-linecap="round"/>')

    for n, (name, p, _) in enumerate(points, 1):
        x, y = xy(p)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="#047857" stroke="#fff" stroke-width="2"/>')
        out.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="11" '
                   f'font-weight="700" fill="#fff">{n}</text>')
        out.append(f'<text x="{x + 14:.1f}" y="{y + 4:.1f}" font-size="12" font-weight="600" '
                   f'fill="#1e293b" stroke="#f8fafc" stroke-width="3" paint-order="stroke">{html.escape(name)}</text>')

    # Schaalbalk 100 m en noordpijl
    bar = 100 * s
    out.append(f'<path d="M{pad},{H - 14} h{bar:.1f}" stroke="#334155" stroke-width="2"/>'
               f'<text x="{pad + bar / 2:.1f}" y="{H - 20}" text-anchor="middle" font-size="10" '
               f'fill="#334155">100 m</text>')
    out.append(f'<path d="M{W - 20},34 l-6,14 h12 z" fill="#334155"/>'
               f'<text x="{W - 20}" y="28" text-anchor="middle" font-size="11" '
               f'font-weight="700" fill="#334155">N</text>')
    out.append(f'<text x="{W - 10}" y="{H - 10}" text-anchor="end" font-size="10" fill="#64748b">'
               f'ca. {total / 1000:.1f} km</text>')
    out.append('</svg>')

    with open(OUT, 'w') as f:
        f.write('\n'.join(out) + '\n')
    print(f'{OUT}: {len(lines)} lijnen, {len(points)} punten, ca. {total:.0f} m')
    write_html_list(points)
    print('Punten:', ', '.join(n for n, _, _ in points))


def clean(text):
    # My Maps-beschrijvingen kunnen <br> en andere HTML bevatten
    text = re.sub(r'<br\s*/?>', ' ', text)
    text = re.sub(r'<[^>]+>', '', text)
    return html.escape(' '.join(html.unescape(text).split()))


def write_html_list(points):
    items = []
    for name, _, desc in points:
        line = f'<b>{clean(name)}</b>' + (f': {clean(desc)}' if desc else '')
        items.append(f'        <li>{line}</li>')
    block = '<!-- route:start -->\n      <ol>\n' + '\n'.join(items) + '\n      </ol>\n      <!-- route:end -->'
    with open(HTML) as f:
        page = f.read()
    new, n = re.subn(r'<!-- route:start -->.*?<!-- route:end -->', lambda _: block, page, flags=re.S)
    if n != 1:
        sys.exit(f'{HTML}: markers <!-- route:start/end --> niet gevonden')
    with open(HTML, 'w') as f:
        f.write(new)


if __name__ == '__main__':
    main()
