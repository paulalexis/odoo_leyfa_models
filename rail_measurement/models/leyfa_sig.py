"""
leyfa_sig.py
============
A pure-Python SVG map renderer for France.
Renders multiple layers of: track lines, stations (gares), and PK points
onto a France basemap with pan/zoom, grid, filters, and PNG export.

Changes vs previous version
----------------------------
- A legend panel is now rendered inside the SVG overlay so it appears in
  PNG exports.
- Each legend item is clickable: clicking toggles that layer's visibility
  on the map.  The legend item becomes semi-transparent when the layer is
  hidden.  The SVG elements (track, PKs, stations, labels) belonging to a
  hidden layer are given display:none so the toggle is instant.
- The legend is only shown when there are ≥ 2 layers (single-layer maps
  keep the existing info-bar behaviour).
"""

import json
import logging
import os

LAYER_COLORS = [
    "#1a56db",
    "#b15eff",
    "#0891b2",
    "#00ffea",
]


class LeyfaSIG:
    LON_MIN_FR, LON_MAX_FR = -5.2, 9.7
    LAT_MIN_FR, LAT_MAX_FR = 41.2, 51.2

    def __init__(
        self,
        regions_geojson_path: str = None,
        lon_bounds: tuple = None,
        lat_bounds: tuple = None,
        svg_size: int = 600,
    ):
        self.svg_size = svg_size
        self.lon_min = lon_bounds[0] if lon_bounds else self.LON_MIN_FR
        self.lon_max = lon_bounds[1] if lon_bounds else self.LON_MAX_FR
        self.lat_min = lat_bounds[0] if lat_bounds else self.LAT_MIN_FR
        self.lat_max = lat_bounds[1] if lat_bounds else self.LAT_MAX_FR

        self.regions_geojson = None
        if regions_geojson_path and os.path.exists(regions_geojson_path):
            with open(regions_geojson_path, "r", encoding="utf-8") as f:
                self.regions_geojson = json.load(f)

        self._layers = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_ligne_layer(
        self,
        label: str,
        track_coords: list = None,
        gares: list = None,
        pks: list = None,
        colour: str = None,
        odoo_id: int = None,
        ranges: list = None,
    ):
        idx = len(self._layers)
        col = colour or LAYER_COLORS[idx % len(LAYER_COLORS)]

        gares_data = []
        for g in (gares or []):
            lat = g.get("latitude") or g.get("lat")
            lon = g.get("longitude") or g.get("lon")
            if not lat or not lon:
                continue
            name = (g.get("name") or "").replace("\\", "\\\\").replace("'", "\\'")
            pk   = (g.get("pk") or "").replace("'", "\\'")
            is_v = "true" if g.get("isV") else "false"
            is_f = "true" if g.get("isF") else "false"
            gares_data.append(
                f"{{lat:{lat},lon:{lon},name:'{name}',pk:'{pk}',isV:{is_v},isF:{is_f},col:'{col}'}}"
            )

        pks_data = []
        for pk in (pks or []):
            lat = pk.get("lat")
            lon = pk.get("lon")
            if not lat or not lon:
                continue
            pk_name = (pk.get("name") or "").replace("'", "\\'")
            pk_val  = pk.get("pk", 0)
            is_int  = "true" if pk_val == int(pk_val) else "false"
            pk_col  = pk.get("color") or col
            pks_data.append(
                f"{{lat:{lat},lon:{lon},name:'{pk_name}',pk:{pk_val},isInt:{is_int},col:'{pk_col}'}}"
            )

        coords = track_coords or []
        coords_js = (
            "[" + ",".join(f"[{c[1]},{c[0]}]" for c in coords) + "]"
        )

        ranges_js = json.dumps(ranges or [])

        self._layers.append(dict(
            label=label,
            colour=col,
            coords_js=coords_js,
            gares_js="[" + ",".join(gares_data) + "]",
            pks_js="[" + ",".join(pks_data) + "]",
            ranges_js=ranges_js,
            n_gares=len(gares_data),
            odoo_id=odoo_id,
        ))

    def render_raw(self, title: str = "", width: str = "100%", aspect_ratio: str = "1/1",
                initial_zoom: float = 5,
                initial_lat: float = None,
                initial_lon: float = None,
                initial_layers_visible: list = None,
                initial_tiles_enabled: bool = False,
                initial_tile_type: str = "osmfr",
                initial_tile_opacity: int = 100,
                initial_station_filter: str = "all",
                initial_pk_filter: str = "km",
                initial_show_grid: bool = True,
                initial_labels_on: bool = False,
                show_consistance_labels: bool = True,
                show_safety_color: bool = False,
                pk_legend_label: str = '',
                sig_controller_id=None) -> str:
        """Return the raw HTML page (no iframe wrapper) for use in a direct HTTP route."""
        return self._build_inner_html(
            title=title,
            initial_zoom=initial_zoom,
            initial_lat=initial_lat,
            initial_lon=initial_lon,
            initial_layers_visible=initial_layers_visible,
            initial_tiles_enabled=initial_tiles_enabled,
            initial_tile_type=initial_tile_type,
            initial_tile_opacity=initial_tile_opacity,
            initial_station_filter=initial_station_filter,
            initial_pk_filter=initial_pk_filter,
            initial_show_grid=initial_show_grid,
            initial_labels_on=initial_labels_on,
            sig_controller_id=sig_controller_id,
            show_safety_color=show_safety_color,
            show_consistance_labels=show_consistance_labels,
            pk_legend_label=pk_legend_label,
        )

    def render(self, title: str = "", width: str = "100%", aspect_ratio: str = "1/1",
            initial_zoom: float = 5,
            initial_lat: float = None,
            initial_lon: float = None,
            initial_layers_visible: list = None,
            initial_tiles_enabled: bool = False,
            initial_tile_type: str = "osmfr",
            initial_tile_opacity: int = 100,
            initial_station_filter: str = "all",
            initial_pk_filter: str = "km",
            initial_show_grid: bool = True,
            initial_labels_on: bool = False,
            pk_legend_label: str = '',
            show_consistance_labels: bool = True,
            show_safety_color: bool = False,
            sig_controller_id=None) -> str:
        inner_html = self._build_inner_html(
            title=title,
            initial_zoom=initial_zoom,
            initial_lat=initial_lat,
            initial_lon=initial_lon,
            initial_layers_visible=initial_layers_visible,
            initial_tiles_enabled=initial_tiles_enabled,
            initial_tile_type=initial_tile_type,
            initial_tile_opacity=initial_tile_opacity,
            initial_station_filter=initial_station_filter,
            initial_pk_filter=initial_pk_filter,
            initial_show_grid=initial_show_grid,
            initial_labels_on=initial_labels_on,
            sig_controller_id=sig_controller_id,
            show_consistance_labels=show_consistance_labels,
            pk_legend_label=pk_legend_label,
            show_safety_color=show_safety_color,
        )
        srcdoc = inner_html.replace('"', '&quot;')
        return (
            f'<div style="width:{width};aspect-ratio:{aspect_ratio};'
            f'font-family:sans-serif;background:#fff;border-radius:8px;overflow:hidden;">'
            f'<iframe srcdoc="{srcdoc}" '
            f'style="width:100%;height:100%;min-height:250px;border:none;border-radius:6px;" '
            f'sandbox="allow-scripts allow-downloads allow-same-origin allow-popups">'
            f'</iframe></div>'
        )

    def _build_inner_html(self, title: str = "", 
                        initial_zoom: float = 5,
                        initial_lat: float = None,
                        initial_lon: float = None,
                        initial_layers_visible: list = None,
                        initial_tiles_enabled: bool = False,
                        initial_tile_type: str = "osmfr",
                        initial_tile_opacity: int = 100,
                        initial_station_filter: str = "all",
                        initial_pk_filter: str = "km",
                        initial_show_grid: bool = True,
                        initial_labels_on: bool = False,
                        initial_label_mode: str = 'auto',
                        show_consistance_labels: bool = True,
                        show_safety_color: bool = False,
                        pk_legend_label: str = '',
                        sig_controller_id=None) -> str:
        regions_geojson_js = json.dumps(self.regions_geojson) if self.regions_geojson else "null"
        all_layers_js = self._build_layers_js()

        multi_layer = len(self._layers) >= 2

        # Info bar: only shown for single-layer maps (legend replaces it for multi)
        if multi_layer:
            info_text = title or ""
        else:
            info_text = title or " &nbsp;·&nbsp; ".join(
                f'<span style="color:{l["colour"]};font-weight:600;">&#9632; {l["label"]}</span>'
                f' ({l["n_gares"]} gares)'
                for l in self._layers
            )

        center_lat = (self.lat_min + self.lat_max) / 2
        center_lon = (self.lon_min + self.lon_max) / 2
        _init_lat = initial_lat if initial_lat is not None else center_lat
        _init_lon = initial_lon if initial_lon is not None else center_lon
        _init_visible = json.dumps(initial_layers_visible or [])
        _layer_ids_js = json.dumps([l['odoo_id'] for l in self._layers])
        _init_label_mode = initial_label_mode or 'auto'

        _export_w = 480   # matches float window default width
        _export_h = 460   # matches float window default height
        
        # Context specific settings
        _show_consistance_labels = 'true' if show_consistance_labels else 'false'
        _consistance_settings_html = ''
        if show_consistance_labels is not None:
            _checked = 'checked' if show_consistance_labels else ''
            _checked_safety = 'checked' if show_safety_color else ''
            _consistance_settings_html = f"""
                <h4 class="mt">Consistance</h4>
                <div class="srow">
                    <label for="chk_consist_labels">
                        <input type="checkbox" id="chk_consist_labels" {_checked}/>
                        <span>Étiquettes N°</span>
                    </label>
                </div>
                <div class="srow">
                    <label for="chk_safety_color">
                        <input type="checkbox" id="chk_safety_color" {_checked_safety}/>
                        <span>Différencier sécurité</span>
                    </label>
                </div>
            """
        _show_safety_color = 'true' if show_safety_color else 'false'
        _pk_legend_label   = pk_legend_label.replace("'", "\\'")
        inner_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#cfe2f3; overflow:hidden; font-family:sans-serif; }}
#map-container {{ position:relative; width:100vw; height:100vh; overflow:hidden; }}
#leaflet-map {{ position:absolute; inset:0; z-index:0; background:#cfe2f3; }}
#overlay-svg {{
    position:absolute; inset:0; z-index:2;
    pointer-events:none;
    width:100%; height:100%;
    overflow:visible;
}}
/* Legend items need pointer events */
#legend-g {{ pointer-events:all; }}

#osm-warning {{
    display:none;
    position:absolute; bottom:30px; left:50%; transform:translateX(-50%);
    z-index:50; background:rgba(220,38,38,0.92); color:#fff;
    border-radius:6px; padding:5px 14px; font-size:11px;
    backdrop-filter:blur(4px); white-space:nowrap; pointer-events:none;
}}
#osm-warning.show {{ display:block; animation: fadeout 0.3s ease 4s forwards; }}
@keyframes fadeout {{ to {{ opacity:0; pointer-events:none; }} }}

#info {{
    position:absolute; top:6px; left:6px; z-index:10;
    background:rgba(255,255,255,0.85); border-radius:5px;
    padding:3px 8px; font-size:12px; color:#475569;
    backdrop-filter:blur(4px); max-width:60%; pointer-events:none;
}}
#toolbar {{
    position:absolute; top:8px; right:8px; z-index:20;
    display:flex; gap:6px; align-items:center;
}}
#btn_settings {{
    border:1px solid #e2e8f0; background:rgba(255,255,255,0.9);
    border-radius:4px; font-size:16px; color:#475569;
    cursor:pointer; padding:1px 8px; backdrop-filter:blur(4px); line-height:1.4;
}}

#settings_panel {{
    display:none;
    position:absolute; top:38px; right:8px; z-index:30;
    background:rgba(255,255,255,0.97); border:1px solid #e2e8f0;
    border-radius:8px; padding:12px 16px; min-width:230px;
    box-shadow:0 4px 20px rgba(0,0,0,0.13);
    font-size:12px; color:#475569;
}}
#settings_panel.open {{ display:block; }}
#settings_panel h4 {{
    font-size:10px; font-weight:700; color:#94a3b8;
    text-transform:uppercase; letter-spacing:0.07em; margin:0 0 6px 0;
}}
#settings_panel h4.mt {{ margin-top:12px; }}
.srow {{
    display:flex; align-items:center; justify-content:space-between;
    padding:5px 0; border-bottom:1px solid #f1f5f9; gap:8px;
}}
.srow:last-child {{ border-bottom:none; }}
.srow label {{ display:flex; align-items:center; gap:6px; cursor:pointer; flex:1; }}
.srow select {{
    border:1px solid #e2e8f0; background:#f8fafc; border-radius:4px;
    font-size:11px; color:#475569; cursor:pointer; padding:2px 4px;
}}
.srow .hint {{ font-size:9px; color:#94a3b8; font-style:italic; }}
#tile-options {{ display:none; padding:6px 0 2px 0; border-bottom:1px solid #f1f5f9; }}
#tile-options.open {{ display:block; }}
.tile-opt-row {{
    display:flex; align-items:center; justify-content:space-between;
    padding:3px 0; gap:8px;
}}
.tile-opt-row label {{ font-size:11px; color:#475569; min-width:60px; }}
.tile-opt-row select {{
    border:1px solid #e2e8f0; background:#f8fafc; border-radius:4px;
    font-size:11px; color:#475569; cursor:pointer; padding:2px 4px; flex:1;
}}
.tile-opt-row input[type=range] {{ flex:1; accent-color:#1a56db; cursor:pointer; }}
.tile-opt-row .val-badge {{ font-size:10px; color:#475569; min-width:28px; text-align:right; }}
#hint {{
    position:absolute; bottom:6px; right:6px; z-index:10;
    background:rgba(255,255,255,0.7); border-radius:4px;
    padding:2px 6px; font-size:1.4vw; color:#94a3b8; pointer-events:none;
}}
</style>
</head>
<body>
<div id="map-container">
    <div id="leaflet-map"></div>

    <svg id="overlay-svg" xmlns="http://www.w3.org/2000/svg">
        <rect id="bg-rect" width="100%" height="100%" fill="#cfe2f3"/>
        <g id="regions-g"></g>
        <g id="grid-g"></g>
        <g id="tracks-g"></g>
        <g id="pks-g"></g>
        <g id="stations-g"></g>
        <g id="labels-g"></g>
        <!-- Legend lives inside the SVG so it appears in PNG exports -->
        <g id="legend-g"></g>
        <g id="scale-g" style="pointer-events:none;"></g>
    </svg>

    <div id="sig-tooltip" style="
        display:none;
        position:absolute;
        background:rgba(15,23,42,0.85);
        color:#fff;
        font-size:11px;
        font-family:sans-serif;
        padding:3px 8px;
        border-radius:4px;
        pointer-events:none;
        z-index:100;
        white-space:nowrap;
    "></div>

    <div id="osm-warning">&#9888; Tuiles OSM inaccessibles — fond de carte désactivé</div>
    <div id="info">{info_text}</div>

    <div id="toolbar">
        <button id="btn_settings" title="Paramètres">&#9881;</button>
    </div>

    <div id="settings_panel">
        <h4>Fond de carte</h4>
        <div class="srow">
            <label for="chk_osm">
                <input type="checkbox" id="chk_osm"/>
                <span>Tuiles</span>
            </label>
            <span class="hint" id="osm_hint">désactivé</span>
        </div>
        <div id="tile-options">
            <div class="tile-opt-row">
                <label for="tile_type">Type</label>
                <select id="tile_type">
                    <option value="osmfr">OSM France</option>
                    <option value="osm">OSM Standard</option>
                    <option value="topo">OSM Topo (OpenTopoMap)</option>
                    <option value="carto_light">Carto Voyager</option>
                    <option value="carto_dark">Carto Dark Matter</option>
                    <option value="esri_sat">Satellite (ESRI)</option>
                    <option value="esri_topo">Topo (ESRI)</option>
                    <option value="esri_streets">Streets (ESRI)</option>
                    <option value="wikimedia">Wikimedia</option>
                </select>
            </div>
            <div class="tile-opt-row" style="margin-top:4px;">
                <label for="tile_opacity">Opacité</label>
                <input type="range" id="tile_opacity" min="10" max="100" value="100" step="5"/>
                <span class="val-badge" id="opacity_val">100%</span>
            </div>
        </div>

        <h4 class="mt">Gares</h4>
        <div class="srow">
            <span>Filtre</span>
            <select id="filter">
                <option value="all">Toutes</option>
                <option value="voyageurs">Voyageurs</option>
                <option value="fret">Fret</option>
                <option value="none">Aucune</option>
            </select>
        </div>
        <div class="srow">
            <label for="chk_labels">
                <input type="checkbox" id="chk_labels"/>
                <span>Étiquettes</span>
            </label>
            <span class="hint" id="label_hint">auto</span>
        </div>

        <h4 class="mt">Points Kilométriques</h4>
        <div class="srow">
            <span>Affichage</span>
            <select id="pk_filter">
                <option value="none">Aucun</option>
                <option value="km" selected>km entiers</option>
                <option value="tenth">1/10 km</option>
            </select>
            <div class="srow">
                <label for="chk_pk_labels">
                    <input type="checkbox" id="chk_pk_labels" checked/>
                    <span>Étiquettes PK</span>
                </label>
            </div>
        </div>

        <h4 class="mt">Carte</h4>
        <div class="srow">
            <label for="chk_grid">
                <input type="checkbox" id="chk_grid" checked/>
                <span>Grille coordonnées</span>
            </label>
        </div>

        <!-- Only shown for consistance_view context -->
        {_consistance_settings_html}
    </div>
</div>

<script>
// ── Data ─────────────────────────────────────────────────────────────────
const LAYERS        = {all_layers_js};
const REGIONS_DATA  = {regions_geojson_js};
const CENTER_LAT    = {center_lat};
const CENTER_LON    = {center_lon};
const MULTI_LAYER   = {'true' if multi_layer else 'false'};
let SHOW_CONSISTANCE_LABELS = {_show_consistance_labels};
const EXPORT_W = {_export_w};
const EXPORT_H = {_export_h};
let SHOW_SAFETY_COLOR = {_show_safety_color};
const PK_LEGEND_LABEL = '{_pk_legend_label}';

// Per-layer visibility state (all visible by default)
const layerVisible = LAYERS.map(() => true);

// ── Tile catalogue ────────────────────────────────────────────────────────
const TILE_PROVIDERS = {{
    osmfr:              {{ url:'https://{{s}}.tile.openstreetmap.fr/osmfr/{{z}}/{{x}}/{{y}}.png',     sub:'abc', attr:'© OSM France / ODbL' }},
    osm:                {{ url:'https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',          sub:'abc', attr:'© OpenStreetMap contributors' }},
    topo:               {{ url:'https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png',            sub:'abc', attr:'© OpenTopoMap' }},
    carto_light:        {{ url:'https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', sub:'abcd', attr:'© CARTO' }},
    carto_dark:         {{ url:'https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',           sub:'abcd', attr:'© CARTO' }},
    esri_sat:           {{ url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',        sub:'', attr:'© Esri, Maxar, Earthstar Geographics' }},
    esri_topo:          {{ url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}',       sub:'', attr:'© Esri' }},
    esri_streets:       {{ url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}',     sub:'', attr:'© Esri' }},
    wikimedia:          {{ url:'https://maps.wikimedia.org/osm-intl/{{z}}/{{x}}/{{y}}{{r}}.png',      sub:'',   attr:'© Wikimedia / OSM' }},
}};

// ── Leaflet map ───────────────────────────────────────────────────────────
const leafletMap = L.map('leaflet-map', {{
    center: [CENTER_LAT, CENTER_LON],
    zoom: 5,
    zoomControl: false,
    attributionControl: true,
}});

// ── DOM refs ──────────────────────────────────────────────────────────────
const overlaySVG  = document.getElementById('overlay-svg');
const bgRect      = document.getElementById('bg-rect');
const regionsG    = document.getElementById('regions-g');
const gridG       = document.getElementById('grid-g');
const tracksG     = document.getElementById('tracks-g');
const pksG        = document.getElementById('pks-g');
const stationsG   = document.getElementById('stations-g');
const labelsG     = document.getElementById('labels-g');
const legendG     = document.getElementById('legend-g');
const osmHint     = document.getElementById('osm_hint');
const osmWarning  = document.getElementById('osm-warning');
const chkOsm      = document.getElementById('chk_osm');
const tileOptions = document.getElementById('tile-options');
const tileTypeSel = document.getElementById('tile_type');
const tileOpacity = document.getElementById('tile_opacity');
const opacityVal  = document.getElementById('opacity_val');
const chkGrid     = document.getElementById('chk_grid');
const chkLabels   = document.getElementById('chk_labels');
const labelHint   = document.getElementById('label_hint');
const filterSel   = document.getElementById('filter');
const pkFilter    = document.getElementById('pk_filter');
pksG.style.pointerEvents = 'all';

// ── Tile layer state ──────────────────────────────────────────────────────
let tileLayer    = null;
let tilesEnabled = false;
let tileFailCount = 0;
const TILE_FAIL_THRESHOLD = 3;

function geoToPixel(lat, lon) {{
    const pt = leafletMap.latLngToContainerPoint(L.latLng(lat, lon));
    return {{ x: pt.x, y: pt.y }};
}}

function applyTileOpacity() {{
    if (tileLayer) tileLayer.setOpacity(parseInt(tileOpacity.value) / 100);
}}

function loadTileLayer() {{
    if (tileLayer) {{ tileLayer.remove(); tileLayer = null; }}
    tileFailCount = 0;
    const key = tileTypeSel.value;
    const p   = TILE_PROVIDERS[key];
    const opts = {{
        minZoom:1, maxZoom:20,
        attribution: p.attr,
        crossOrigin: true,
        opacity: parseInt(tileOpacity.value) / 100,
    }};
    if (p.sub) opts.subdomains = p.sub;
    tileLayer = L.tileLayer(p.url, opts);
    tileLayer.on('tileerror', () => {{
        tileFailCount++;
        if (tileFailCount >= TILE_FAIL_THRESHOLD) disableTiles(true);
    }});
    tileLayer.on('tileload', () => {{
        tileFailCount = 0;
        osmHint.textContent = tileTypeSel.options[tileTypeSel.selectedIndex].text + ' ✓';
        osmHint.style.color = '#16a34a';
    }});
    tileLayer.addTo(leafletMap);
    bgRect.setAttribute('fill', 'transparent');
    regionsG.style.display = 'none';
}}

function enableTiles() {{
    tilesEnabled = true;
    osmHint.textContent = 'chargement…'; osmHint.style.color = '#94a3b8';
    tileOptions.classList.add('open');
    loadTileLayer();
}}

function disableTiles(showWarning=false) {{
    tilesEnabled = false; chkOsm.checked = false;
    tileOptions.classList.remove('open');
    osmHint.textContent = showWarning ? 'indisponible' : 'désactivé';
    osmHint.style.color = showWarning ? '#dc2626' : '#94a3b8';
    if (tileLayer) {{ tileLayer.remove(); tileLayer = null; }}
    bgRect.setAttribute('fill', '#cfe2f3');
    regionsG.style.display = '';
    if (showWarning) {{
        osmWarning.classList.remove('show');
        void osmWarning.offsetWidth;
        osmWarning.classList.add('show');
    }}
}}

chkOsm.addEventListener('change', () => {{ if (chkOsm.checked) enableTiles(); else disableTiles(); }});
tileTypeSel.addEventListener('change', () => {{ if (tilesEnabled) loadTileLayer(); }});
tileOpacity.addEventListener('input', () => {{
    opacityVal.textContent = tileOpacity.value + '%';
    applyTileOpacity();
}});

// ── Regions ───────────────────────────────────────────────────────────────
function renderRegions() {{
    regionsG.innerHTML = '';
    if (!REGIONS_DATA) return;
    for (const feature of REGIONS_DATA.features || []) {{
        const geom = feature.geometry;
        if (!geom) continue;
        const rings = geom.type === 'Polygon'
            ? geom.coordinates
            : geom.type === 'MultiPolygon'
                ? geom.coordinates.flat(1)
                : [];
        let d = '';
        for (const ring of rings) {{
            const pts = ring.map(([lon, lat]) => {{
                const p = geoToPixel(lat, lon);
                return `${{p.x}},${{p.y}}`;
            }});
            d += 'M ' + pts.join(' L ') + ' Z ';
        }}
        if (d) {{
            const path = document.createElementNS('http://www.w3.org/2000/svg','path');
            path.setAttribute('d', d);
            path.setAttribute('fill', '#e8ede8');
            path.setAttribute('stroke', '#d4ddd4');
            path.setAttribute('stroke-width', '0.5');
            regionsG.appendChild(path);
        }}
    }}
}}

// ── Label mode ────────────────────────────────────────────────────────────
let labelMode = 'auto';
let labelsOn  = false;

function setLabelsAuto(on) {{
    labelsOn = on; chkLabels.checked = on;
    labelHint.textContent = 'auto'; labelHint.style.color = '#94a3b8';
}}
function setLabelsManual(on) {{
    labelMode = 'manual'; labelsOn = on; chkLabels.checked = on;
    labelHint.textContent = 'manuel'; labelHint.style.color = '#1a56db';
}}

// State — add alongside labelMode/labelsOn at the top of the script
let pkLabelMode = 'auto';  // 'auto' | 'manual'
let pkLabelsOn  = true;

chkLabels.addEventListener('change', () => {{ setLabelsManual(chkLabels.checked); renderOverlay(); debouncePersist();}});
filterSel.addEventListener('change', renderOverlay);
pkFilter.addEventListener('change', renderOverlay);
chkGrid.addEventListener('change', renderGrid);

tileOpacity.addEventListener('input', () => {{
    opacityVal.textContent = tileOpacity.value + '%';
    applyTileOpacity();
    debouncePersist();  // ← was missing
}});

const chkConsistLabels = document.getElementById('chk_consist_labels');
if (chkConsistLabels) {{
    chkConsistLabels.addEventListener('change', () => {{
        SHOW_CONSISTANCE_LABELS = chkConsistLabels.checked;
        renderOverlay();
        debouncePersist();
    }});
}}

// ── Settings panel ────────────────────────────────────────────────────────
const btnSettings = document.getElementById('btn_settings');
const panel = document.getElementById('settings_panel');
btnSettings.addEventListener('click', e => {{ e.stopPropagation(); panel.classList.toggle('open'); }});
document.addEventListener('click', e => {{
    if (!panel.contains(e.target) && e.target !== btnSettings) panel.classList.remove('open');
}});

const chkSafetyColor = document.getElementById('chk_safety_color');
if (chkSafetyColor) {{
    chkSafetyColor.addEventListener('change', () => {{
        SHOW_SAFETY_COLOR = chkSafetyColor.checked;
        renderOverlay();
        debouncePersist();
    }});
}}

// ── GRID ──────────────────────────────────────────────────────────────────
function renderGrid() {{
    gridG.innerHTML = '';
    if (!chkGrid.checked) return;

    const bounds  = leafletMap.getBounds();
    const lon0 = bounds.getWest(), lon1 = bounds.getEast();
    const lat0 = bounds.getSouth(), lat1 = bounds.getNorth();
    const lonSpan = lon1 - lon0;

    const steps = [10,5,2,1,0.5,0.2,0.1,0.05,0.02,0.01,0.005,0.002,0.001];
    const step  = steps.find(st => lonSpan/st >= 3 && lonSpan/st <= 8) || steps[steps.length-1];
    const dec   = step >= 1 ? 1 : step >= 0.1 ? 2 : step >= 0.01 ? 3 : 4;
    const H = overlaySVG.clientHeight || window.innerHeight;
    const W = overlaySVG.clientWidth  || window.innerWidth;

    const lonStart = Math.ceil(lon0 / step) * step;
    for (let i = 0; i < 40; i++) {{
        const lon = Math.round((lonStart + i*step)*1e6)/1e6;
        if (lon > lon1 + step) break;
        const p1 = geoToPixel(lat1, lon);
        const p2 = geoToPixel(lat0, lon);
        const ln = document.createElementNS('http://www.w3.org/2000/svg','line');
        ln.setAttribute('x1',p1.x); ln.setAttribute('y1',0);
        ln.setAttribute('x2',p2.x); ln.setAttribute('y2',H);
        ln.setAttribute('stroke','#94a3b8'); ln.setAttribute('stroke-width','0.5');
        ln.setAttribute('stroke-dasharray','2,4'); ln.setAttribute('opacity','0.5');
        gridG.appendChild(ln);
        const t = document.createElementNS('http://www.w3.org/2000/svg','text');
        t.setAttribute('x', p1.x + 2); t.setAttribute('y', 14);
        t.setAttribute('font-size','11'); t.setAttribute('fill','#475569');
        t.setAttribute('font-family','sans-serif'); t.setAttribute('opacity','0.9');
        t.textContent = lon.toFixed(dec) + '°E';
        gridG.appendChild(t);
    }}

    const latStart = Math.ceil(lat0 / step) * step;
    for (let i = 0; i < 40; i++) {{
        const lat = Math.round((latStart + i*step)*1e6)/1e6;
        if (lat > lat1 + step) break;
        const p1 = geoToPixel(lat, lon0);
        const p2 = geoToPixel(lat, lon1);
        const ln = document.createElementNS('http://www.w3.org/2000/svg','line');
        ln.setAttribute('x1',0);  ln.setAttribute('y1',p1.y);
        ln.setAttribute('x2',W);  ln.setAttribute('y2',p2.y);
        ln.setAttribute('stroke','#94a3b8'); ln.setAttribute('stroke-width','0.5');
        ln.setAttribute('stroke-dasharray','2,4'); ln.setAttribute('opacity','0.5');
        gridG.appendChild(ln);
        const t = document.createElementNS('http://www.w3.org/2000/svg','text');
        t.setAttribute('x', 2); t.setAttribute('y', p1.y - 2);
        t.setAttribute('font-size','11'); t.setAttribute('fill','#475569');
        t.setAttribute('font-family','sans-serif'); t.setAttribute('opacity','0.9');
        t.textContent = lat.toFixed(dec) + '°N';
        gridG.appendChild(t);
    }}
}}

function renderScale() {{
    const scaleG = document.getElementById('scale-g');
    scaleG.innerHTML = '';

    const W = overlaySVG.clientWidth  || window.innerWidth;
    const H = overlaySVG.clientHeight || window.innerHeight;

    // Pick a round target distance (metres) based on zoom
    const zoom = leafletMap.getZoom();
    const metersPerPixel = 156543.03392 * Math.cos(leafletMap.getCenter().lat * Math.PI / 180) / Math.pow(2, zoom);

    const TARGET_PX = 100; // aim for ~100px wide bar
    const rawMeters = TARGET_PX * metersPerPixel;

    // Round to a clean number
    const magnitude = Math.pow(10, Math.floor(Math.log10(rawMeters)));
    const nice = [1, 2, 5, 10];
    let niceMeters = magnitude;
    for (const n of nice) {{
        const candidate = n * magnitude;
        if (candidate / rawMeters >= 0.5) {{ niceMeters = candidate; break; }}
    }}

    const barPx = niceMeters / metersPerPixel;

    // Label
    let label;
    if (niceMeters >= 1000) {{
        label = (niceMeters / 1000 % 1 === 0)
            ? (niceMeters / 1000) + ' km'
            : (niceMeters / 1000).toFixed(1) + ' km';
    }} else {{
        label = Math.round(niceMeters) + ' m';
    }}

    // Position: bottom-right, above the hint
    const PAD   = 10;
    const BAR_H = 4;
    const x0    = W - PAD - barPx;
    const x1    = W - PAD;
    const y     = H - 28;

    // White halo background for readability over any tile
    const halo = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    halo.setAttribute('x',      x0 - 6);
    halo.setAttribute('y',      y - 20);
    halo.setAttribute('width',  barPx + 12);
    halo.setAttribute('height', BAR_H + 22);
    halo.setAttribute('rx',     3);
    halo.setAttribute('fill',   'rgba(255,255,255,0.75)');
    scaleG.appendChild(halo);

    // Ticked bar: left cap | flat bar | right cap
    const barLine = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    barLine.setAttribute('d',
        `M${{x0}},${{y - 5}} L${{x0}},${{y}} L${{x1}},${{y}} L${{x1}},${{y - 5}}`
    );
    barLine.setAttribute('fill',         'none');
    barLine.setAttribute('stroke',       '#1e293b');
    barLine.setAttribute('stroke-width', '1.5');
    barLine.setAttribute('stroke-linecap', 'round');
    scaleG.appendChild(barLine);

    // Alternating filled segments (2 halves, like a real scale bar)
    const midX = x0 + barPx / 2;
    for (const [sx, sw, fill] of [
        [x0,   barPx / 2, '#1e293b'],
        [midX, barPx / 2, '#fff'  ],
    ]) {{
        const seg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        seg.setAttribute('x',      sx);
        seg.setAttribute('y',      y - BAR_H);
        seg.setAttribute('width',  sw);
        seg.setAttribute('height', BAR_H);
        seg.setAttribute('fill',   fill);
        seg.setAttribute('stroke', '#1e293b');
        seg.setAttribute('stroke-width', '0.5');
        scaleG.appendChild(seg);
    }}

    // Label centred above the bar
    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x',           (x0 + x1) / 2);
    txt.setAttribute('y',           y - BAR_H - 4);
    txt.setAttribute('text-anchor', 'middle');
    txt.setAttribute('font-size',   '10');
    txt.setAttribute('font-weight', '600');
    txt.setAttribute('font-family', 'sans-serif');
    txt.setAttribute('fill',        '#1e293b');
    txt.textContent = label;
    scaleG.appendChild(txt);
}}

// ── LABEL PLACEMENT ───────────────────────────────────────────────────────
function bestLabelPos(px, py, lw, lh, placed, offset) {{
    const r = offset * 1.5;
    const candidates = [
        [r,-lh*0.5],[r,lh],[r,-lh*1.5],
        [-lw-r,-lh*0.5],[-lw-r,lh],[-lw-r,-lh*1.5],
        [-lw*0.5,-r-lh],[-lw*0.5,r],
    ];
    for (const [ox,oy] of candidates) {{
        const lx = px+ox, ly = py+oy;
        if (!overlaps(lx, ly, lw, lh, placed)) return [lx, ly];
    }}
    return null;
}}
function overlaps(nx, ny, nw, nh, placed) {{
    for (const [px,py,pw,ph] of placed)
        if (nx < px+pw && nx+nw > px && ny < py+ph && ny+nh > py) return true;
    return false;
}}

// ── LEGEND ───────────────────────────────────────────────────────────────
// The legend is drawn inside the SVG overlay so it lands in PNG exports.
// Each row is a clickable <g> that toggles the corresponding layer.

const LEGEND_X       = 10;   // px from left edge
const LEGEND_PAD     = 8;    // inner padding
const LEGEND_ROW_H   = 22;   // height per layer row
const LEGEND_SWATCH  = 14;   // colour square size
const LEGEND_FONT    = 12;

function renderLegend() {{
    legendG.innerHTML = '';

    const n = LAYERS.length;  // ← must be BEFORE pkRows/legendH

    const pkEntries = [];
    if (PK_LEGEND_LABEL) {{
        pkEntries.push({{ color: '#dc2626', label: PK_LEGEND_LABEL }});
        if (SHOW_SAFETY_COLOR) {{
            pkEntries.push({{ color: '#ffdd00', label: 'Sécurité Amont/Aval' }});
        }}
    }}

    const pkRows  = pkEntries.length;
    const legendH = LEGEND_PAD * 2
                  + n * LEGEND_ROW_H
                  + (pkRows > 0 ? 8 + pkRows * LEGEND_ROW_H : 0);

    // Measure longest label for width
    let maxLabelW = 60;
    const probeT = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    probeT.setAttribute('font-size', LEGEND_FONT);
    probeT.setAttribute('font-family', 'sans-serif');
    probeT.setAttribute('visibility', 'hidden');
    legendG.appendChild(probeT);
    for (const l of LAYERS) {{
        probeT.textContent = 'Ligne ' + l.label;
        maxLabelW = Math.max(maxLabelW, probeT.getComputedTextLength());
    }}
    for (const e of pkEntries) {{
        probeT.textContent = e.label;
        maxLabelW = Math.max(maxLabelW, probeT.getComputedTextLength());
    }}
    legendG.removeChild(probeT);

    const legendW = LEGEND_PAD * 4 + LEGEND_SWATCH + maxLabelW + 4;

    const H       = overlaySVG.clientHeight || window.innerHeight;
    const legendY = H - legendH - 30;

    // Background
    const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    bg.setAttribute('x', LEGEND_X);
    bg.setAttribute('y', legendY);
    bg.setAttribute('width', legendW);
    bg.setAttribute('height', legendH);
    bg.setAttribute('rx', 6);
    bg.setAttribute('fill', 'rgba(255,255,255,0.88)');
    bg.setAttribute('stroke', '#e2e8f0');
    bg.setAttribute('stroke-width', '1');
    legendG.appendChild(bg);

    // ── Layer rows ────────────────────────────────────────────────────────
    LAYERS.forEach((layer, i) => {{
        const rowY   = legendY + LEGEND_PAD + i * LEGEND_ROW_H;
        const visible = layerVisible[i];

        const rowG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        rowG.setAttribute('opacity', visible ? '1' : '0.35');
        rowG.style.cursor = 'pointer';

        const hit = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        hit.setAttribute('x', LEGEND_X);
        hit.setAttribute('y', rowY);
        hit.setAttribute('width', legendW);
        hit.setAttribute('height', LEGEND_ROW_H);
        hit.setAttribute('fill', 'transparent');
        rowG.appendChild(hit);

        const sw = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        sw.setAttribute('x', LEGEND_X + LEGEND_PAD);
        sw.setAttribute('y', rowY + (LEGEND_ROW_H - LEGEND_SWATCH) / 2);
        sw.setAttribute('width', LEGEND_SWATCH);
        sw.setAttribute('height', LEGEND_SWATCH);
        sw.setAttribute('rx', 3);
        sw.setAttribute('fill', layer.colour);
        rowG.appendChild(sw);

        if (!visible) {{
            const sl = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            const sy = rowY + LEGEND_ROW_H / 2;
            sl.setAttribute('x1', LEGEND_X + LEGEND_PAD);
            sl.setAttribute('y1', sy);
            sl.setAttribute('x2', LEGEND_X + LEGEND_PAD + LEGEND_SWATCH);
            sl.setAttribute('y2', sy);
            sl.setAttribute('stroke', '#64748b');
            sl.setAttribute('stroke-width', '2');
            rowG.appendChild(sl);
        }}

        const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        txt.setAttribute('x', LEGEND_X + LEGEND_PAD * 2 + LEGEND_SWATCH);
        txt.setAttribute('y', rowY + LEGEND_ROW_H * 0.65);
        txt.setAttribute('font-size', LEGEND_FONT);
        txt.setAttribute('font-family', 'sans-serif');
        txt.setAttribute('fill', '#1e293b');
        txt.textContent = 'Ligne ' + layer.label;
        rowG.appendChild(txt);

        rowG.addEventListener('click', () => {{
            layerVisible[i] = !layerVisible[i];
            renderOverlay();
        }});

        legendG.appendChild(rowG);
    }});

    // ── PK legend rows ────────────────────────────────────────────────────
    if (pkRows > 0) {{
        // Separator
        const sepY = legendY + LEGEND_PAD + n * LEGEND_ROW_H + 3;
        const sep  = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        sep.setAttribute('x1', LEGEND_X + LEGEND_PAD);
        sep.setAttribute('y1', sepY);
        sep.setAttribute('x2', LEGEND_X + legendW - LEGEND_PAD);
        sep.setAttribute('y2', sepY);
        sep.setAttribute('stroke', '#e2e8f0');
        sep.setAttribute('stroke-width', '1');
        legendG.appendChild(sep);

        pkEntries.forEach((entry, i) => {{
            const rowY = legendY + LEGEND_PAD + n * LEGEND_ROW_H + 8 + i * LEGEND_ROW_H;

            const rowG = document.createElementNS('http://www.w3.org/2000/svg', 'g');

            // Circle swatch
            const sw = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            sw.setAttribute('cx', LEGEND_X + LEGEND_PAD + LEGEND_SWATCH / 2);
            sw.setAttribute('cy', rowY + LEGEND_ROW_H / 2);
            sw.setAttribute('r',  LEGEND_SWATCH / 2);
            sw.setAttribute('fill', entry.color);
            sw.setAttribute('stroke', '#fff');
            sw.setAttribute('stroke-width', '1');
            rowG.appendChild(sw);

            const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            txt.setAttribute('x', LEGEND_X + LEGEND_PAD * 2 + LEGEND_SWATCH);
            txt.setAttribute('y', rowY + LEGEND_ROW_H * 0.65);
            txt.setAttribute('font-size', LEGEND_FONT);
            txt.setAttribute('font-family', 'sans-serif');
            txt.setAttribute('fill', '#1e293b');
            txt.textContent = entry.label;
            rowG.appendChild(txt);

            legendG.appendChild(rowG);
        }});
    }}
}}

// ── RENDER OVERLAY (tracks + PKs + stations + legend) ─────────────────────
function renderOverlay() {{
    const zoom  = leafletMap.getZoom();
    const f     = filterSel.value;
    const pkf   = pkFilter.value;
    const showPK = zoom >= 12;

    const autoOn = zoom >= 10;
    if (labelMode === 'auto') setLabelsAuto(autoOn);

    const dotR    = Math.max(3, 8 - zoom * 0.3);
    const innerR  = dotR * 0.38;
    const strokeW = 1.5;
    const fontSize = 12, fontSizePK = 10, offset = 7;
    const trackW  = Math.max(1, 2.5 - zoom * 0.05);

    tracksG.innerHTML   = '';
    pksG.innerHTML      = '';
    stationsG.innerHTML = '';
    labelsG.innerHTML   = '';

    const placed = [];
    const bounds = leafletMap.getBounds();
    const tooltip = document.getElementById('sig-tooltip');

    LAYERS.forEach((layer, li) => {{
        if (!layerVisible[li]) return;   // skip hidden layers entirely
        const col = layer.colour;

        // Track
        if (layer.coords.length > 1) {{
            const pts = layer.coords.map(([lat, lon]) => {{
                const p = geoToPixel(lat, lon);
                return `${{p.x}},${{p.y}}`;
            }}).join(' ');
            const poly = document.createElementNS('http://www.w3.org/2000/svg','polyline');
            poly.setAttribute('points', pts);
            poly.setAttribute('fill','none'); poly.setAttribute('stroke',col);
            poly.setAttribute('stroke-width',trackW);
            poly.setAttribute('stroke-linecap','round'); poly.setAttribute('stroke-linejoin','round');
            tracksG.appendChild(poly);
        }}

        // PKs
        const pkR = Math.max(2, Math.min(5, zoom * 0.25));
        if (pkf !== 'none') {{
            const normalPks = [], orangePks = [], redPks = [];

            for (const pk of layer.pks) {{
                if (pkf === 'km' && !pk.isInt) continue;
                if (!bounds.contains([pk.lat, pk.lon])) continue;

                let pkColor = col;
                for (const r of (layer.ranges || [])) {{
                    if (pk.pk >= r.work_start - 0.0005 && pk.pk <= r.work_end + 0.0005) {{
                        pkColor = '#dc2626';
                        break;
                    }}
                    if (pk.pk >= r.safety_start - 0.0005 && pk.pk <= r.safety_end + 0.0005) {{
                        pkColor = SHOW_SAFETY_COLOR ? '#ffdd00' : '#dc2626';
                    }}
                }}

                if (pkColor === '#dc2626')      redPks.push({{pk, pkColor}});
                else if (pkColor === '#ffdd00') orangePks.push({{pk, pkColor}});
                else                            normalPks.push({{pk, pkColor}});
            }}

            const PK_LABEL_ZOOM = 13;
            const autoOnPk = zoom >= PK_LABEL_ZOOM;
            if (pkLabelMode === 'auto') setPkLabelsAuto(autoOnPk);

            const showPkLabels = pkLabelsOn;

            for (const {{pk, pkColor}} of [...normalPks, ...redPks, ...orangePks]) {{
                const p = geoToPixel(pk.lat, pk.lon);

                // ── wrapper group — one handler for dot + badge ───────────────────
                const pkG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                pkG.style.cursor = 'pointer';

                pkG.addEventListener('mouseenter', (e) => {{
                    tooltip.textContent = 'PK ' + pk.name;
                    tooltip.style.display = 'block';
                }});
                pkG.addEventListener('mousemove', (e) => {{
                    const rect = document.getElementById('map-container').getBoundingClientRect();
                    tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
                    tooltip.style.top  = (e.clientY - rect.top  - 28) + 'px';
                }});
                pkG.addEventListener('mouseleave', () => {{
                    tooltip.style.display = 'none';
                }});
                pkG.addEventListener('click', (e) => {{
                    e.stopPropagation();
                    const url = 'https://gecko.imajnet.net/#loc=' + pk.lat + ',' + pk.lon + ';map=OSM;zoom=15;';
                    window.open(url, '_blank');
                }});

                // Circle
                const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                c.setAttribute('cx', p.x);
                c.setAttribute('cy', p.y);
                c.setAttribute('r', pkR);
                c.setAttribute('fill', pkColor);
                c.setAttribute('stroke', pkColor === col ? 'none' : '#fff');
                c.setAttribute('stroke-width', pkColor === col ? '0' : '0.5');
                pkG.appendChild(c);

                // Badge
                if (showPkLabels && pk.isInt) {{
                    const label = String(Math.round(pk.pk));
                    const fontSize = 10;
                    const padX = 3, padY = 1;
                    const charW = fontSize * 0.6;
                    const tw = label.length * charW;
                    const bw = tw + padX * 2;
                    const bh = fontSize + padY * 2;
                    const bx = p.x + pkR + 2;
                    const by = p.y - bh / 2;

                    const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    bg.setAttribute('x',            bx);
                    bg.setAttribute('y',            by);
                    bg.setAttribute('width',        bw);
                    bg.setAttribute('height',       bh);
                    bg.setAttribute('rx',           2);
                    bg.setAttribute('fill',         '#22c55e');
                    bg.setAttribute('stroke',       '#fff');
                    bg.setAttribute('stroke-width', '0.5');
                    pkG.appendChild(bg);

                    const lbl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    lbl.setAttribute('x',           bx + padX);
                    lbl.setAttribute('y',           by + bh - padY - 0.5);
                    lbl.setAttribute('font-size',   fontSize);
                    lbl.setAttribute('font-weight', '700');
                    lbl.setAttribute('font-family', 'sans-serif');
                    lbl.setAttribute('fill',        '#14532d');
                    lbl.textContent = label;
                    pkG.appendChild(lbl);
                }}

                pksG.appendChild(pkG);
            }}
        }}

        // ── Consistance range labels ──────────────────────────────────────────
        if (SHOW_CONSISTANCE_LABELS) {{
            for (const r of (layer.ranges || [])) {{
                if (!r.index) continue;

                // 1. Find PK closest to work zone midpoint FIRST
                const mid = (r.work_start + r.work_end) / 2;
                let closestPk = null;
                let closestDist = Infinity;
                for (const pk of layer.pks) {{
                    const d = Math.abs(pk.pk - mid);
                    if (d < closestDist) {{
                        closestDist = d;
                        closestPk = pk;
                    }}
                }}
                if (!closestPk) continue;
                if (!bounds.pad(0.2).contains([closestPk.lat, closestPk.lon])) continue;

                const p = geoToPixel(closestPk.lat, closestPk.lon);

                const idxStr  = String(r.index);
                const voieStr = r.voie ? ' (' + r.voie + ')' : '';
                const badgeH  = 16, badgeR = 4;
                const idxW    = idxStr.length * 6 + 6;
                const voieW   = voieStr.length * 4.5;
                const badgeW  = idxW + voieW;

                // 2. Compute perpendicular direction AFTER closestPk is known
                let perpX = 0, perpY = -1;
                const pkIdx = layer.pks.indexOf(closestPk);
                if (pkIdx > 0 && pkIdx < layer.pks.length - 1) {{
                    const prev = layer.pks[pkIdx - 1];
                    const next = layer.pks[pkIdx + 1];
                    const pp = geoToPixel(prev.lat, prev.lon);
                    const np = geoToPixel(next.lat, next.lon);
                    const dx = np.x - pp.x;
                    const dy = np.y - pp.y;
                    const len = Math.sqrt(dx*dx + dy*dy) || 1;
                    perpX = -dy / len;
                    perpY =  dx / len;
                }}

                const BADGE_OFFSET = 32;

                // 3. Try perpendicular sides first, then fallback
                const candidates = [
                    [p.x + perpX * BADGE_OFFSET - badgeW/2, p.y + perpY * BADGE_OFFSET - badgeH/2],
                    [p.x - perpX * BADGE_OFFSET - badgeW/2, p.y - perpY * BADGE_OFFSET - badgeH/2],
                ];

                let chosenPos = null;
                for (const [cx, cy] of candidates) {{
                    if (!overlaps(cx, cy, badgeW, badgeH, placed)) {{
                        chosenPos = [cx, cy];
                        break;
                    }}
                }}
                if (!chosenPos) chosenPos = bestLabelPos(p.x, p.y, badgeW, badgeH, placed, offset);
                if (!chosenPos) continue;

                const [bx, by] = chosenPos;
                placed.push([bx, by, badgeW, badgeH]);

                const badgeG = document.createElementNS('http://www.w3.org/2000/svg', 'g');

                // Connector
                const connector = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                connector.setAttribute('x1', p.x);
                connector.setAttribute('y1', p.y - dotR);
                connector.setAttribute('x2', bx + badgeW / 2);
                connector.setAttribute('y2', by + badgeH);
                connector.setAttribute('stroke', col);
                connector.setAttribute('stroke-width', '2');
                connector.setAttribute('stroke-dasharray', '2,2');
                badgeG.appendChild(connector);

                // Background
                const badgeBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                badgeBg.setAttribute('x', bx);
                badgeBg.setAttribute('y', by);
                badgeBg.setAttribute('width', badgeW);
                badgeBg.setAttribute('height', badgeH);
                badgeBg.setAttribute('rx', badgeR);
                badgeBg.setAttribute('fill', col);
                badgeBg.setAttribute('stroke', '#fff');
                badgeBg.setAttribute('stroke-width', '1.5');
                badgeG.appendChild(badgeBg);

                // Index number
                const badgeTxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                badgeTxt.setAttribute('x', bx + 4);
                badgeTxt.setAttribute('y', by + badgeH * 0.72);
                badgeTxt.setAttribute('font-size', '10');
                badgeTxt.setAttribute('font-weight', '700');
                badgeTxt.setAttribute('fill', '#fff');
                badgeTxt.setAttribute('font-family', 'sans-serif');
                badgeTxt.textContent = idxStr;
                badgeG.appendChild(badgeTxt);

                // Voie label
                if (voieStr) {{
                    const voieTxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    voieTxt.setAttribute('x', bx + idxW);
                    voieTxt.setAttribute('y', by + badgeH * 0.72);
                    voieTxt.setAttribute('font-size', '8');
                    voieTxt.setAttribute('font-weight', '400');
                    voieTxt.setAttribute('fill', 'rgba(255,255,255,0.85)');
                    voieTxt.setAttribute('font-family', 'sans-serif');
                    voieTxt.textContent = voieStr;
                    badgeG.appendChild(voieTxt);
                }}

                labelsG.appendChild(badgeG);
            }}
        }}

        // Stations
        for (const s of layer.gares) {{
            if (f === 'voyageurs' && !s.isV) continue;
            if (f === 'fret'      && !s.isF) continue;
            if (f === 'none') continue;
            if (!bounds.pad(0.1).contains([s.lat, s.lon])) continue;

            const p = geoToPixel(s.lat, s.lon);
            const color = s.isV ? col : s.isF ? '#e67e22' : '#64748b';
            const g = document.createElementNS('http://www.w3.org/2000/svg','g');

            const c1 = document.createElementNS('http://www.w3.org/2000/svg','circle');
            c1.setAttribute('cx',p.x); c1.setAttribute('cy',p.y); c1.setAttribute('r',dotR);
            c1.setAttribute('fill','#fff'); c1.setAttribute('stroke',color); c1.setAttribute('stroke-width',strokeW);
            g.appendChild(c1);

            const c2 = document.createElementNS('http://www.w3.org/2000/svg','circle');
            c2.setAttribute('cx',p.x); c2.setAttribute('cy',p.y); c2.setAttribute('r',innerR);
            c2.setAttribute('fill',color); g.appendChild(c2);

            const ttl = document.createElementNS('http://www.w3.org/2000/svg','title');
            ttl.textContent = s.name + (s.pk ? ' — PK ' + s.pk : '');
            g.appendChild(ttl);

            if (labelsOn) {{
                const probe = document.createElementNS('http://www.w3.org/2000/svg','text');
                probe.setAttribute('font-size', fontSize);
                probe.setAttribute('font-weight', '600');
                probe.setAttribute('font-family', 'sans-serif');
                probe.setAttribute('visibility', 'hidden');
                probe.textContent = s.name;
                labelsG.appendChild(probe);
                const lw = probe.getComputedTextLength();
                labelsG.removeChild(probe);

                const lh = fontSize * 1.4;
                const pos = bestLabelPos(p.x, p.y, lw, lh, placed, offset);
                if (pos) {{
                    const [lx, ly] = pos;
                    placed.push([lx, ly, lw, lh]);

                    const lg = document.createElementNS('http://www.w3.org/2000/svg','g');

                    const leader = document.createElementNS('http://www.w3.org/2000/svg','line');
                    leader.setAttribute('x1', p.x); leader.setAttribute('y1', p.y);
                    leader.setAttribute('x2', lx + lw * 0.5); leader.setAttribute('y2', ly + lh * 0.5);
                    leader.setAttribute('stroke','#cbd5e1'); leader.setAttribute('stroke-width','1.5');
                    lg.appendChild(leader);

                    const pad = 3;
                    const bg = document.createElementNS('http://www.w3.org/2000/svg','rect');
                    bg.setAttribute('x', lx - pad);
                    bg.setAttribute('y', ly);
                    bg.setAttribute('width',  lw + pad * 2);
                    bg.setAttribute('height', lh);
                    bg.setAttribute('rx', 2);
                    bg.setAttribute('fill', 'rgba(255,255,255,0.75)');
                    lg.appendChild(bg);

                    const t = document.createElementNS('http://www.w3.org/2000/svg','text');
                    t.setAttribute('x', lx); t.setAttribute('y', ly + lh * 0.75);
                    t.setAttribute('font-size', fontSize); t.setAttribute('font-weight','600');
                    t.setAttribute('fill','#1e293b'); t.setAttribute('font-family','sans-serif');
                    t.textContent = s.name;
                    lg.appendChild(t);

                    if (showPK && s.pk) {{
                        const t2 = document.createElementNS('http://www.w3.org/2000/svg','text');
                        t2.setAttribute('x', lx); t2.setAttribute('y', ly + lh * 0.75 + fontSizePK * 1.2);
                        t2.setAttribute('font-size', fontSizePK); t2.setAttribute('fill','#64748b');
                        t2.setAttribute('font-family','sans-serif');
                        t2.textContent = s.pk;
                        lg.appendChild(t2);
                    }}

                    labelsG.appendChild(lg);
                }}
            }}
            stationsG.appendChild(g);
        }}
    }});

    // Redraw the legend after every render (so toggle state is reflected)
    renderLegend();
}}

// ── Master redraw ─────────────────────────────────────────────────────────
function redrawAll() {{
    if (!tilesEnabled) renderRegions();
    renderGrid();
    renderOverlay();
    renderScale();
}}

leafletMap.on('move',   redrawAll);
leafletMap.on('zoom',   redrawAll);
leafletMap.on('resize', () => {{
    // Suppress persist on resize — this fires when tab becomes visible again
    const wasInitializing = _isInitializing;
    _isInitializing = true;
    redrawAll();
    setTimeout(() => {{
        clearTimeout(_persistTimer);
        _isInitializing = wasInitializing;
    }}, 200);
}});
document.addEventListener('visibilitychange', () => {{
    if (!document.hidden) {{
        _isInitializing = true;
        setTimeout(() => {{
            clearTimeout(_persistTimer);
            _isInitializing = false;
        }}, 300);
    }}
}});

// ── Shared canvas builder ─────────────────────────────────────────────────
async function buildMapCanvas() {{
    const w = overlaySVG.clientWidth  || 800;
    const h = overlaySVG.clientHeight || 600;
    const scale = 2;

    const canvas = document.createElement('canvas');
    canvas.width  = w * scale;
    canvas.height = h * scale;
    const ctx = canvas.getContext('2d');
    ctx.scale(scale, scale);

    ctx.fillStyle = '#cfe2f3';
    ctx.fillRect(0, 0, w, h);

    if (tilesEnabled && tileLayer) {{
        const tileImgs = document.querySelectorAll(
            '.leaflet-tile-container img.leaflet-tile'
        );
        await Promise.allSettled(
            Array.from(tileImgs).map(img => new Promise(resolve => {{
                if (img.complete && img.naturalWidth > 0) {{ resolve(img); return; }}
                img.onload  = () => resolve(img);
                img.onerror = () => resolve(null);
            }}))
        );
        const savedAlpha = ctx.globalAlpha;
        ctx.globalAlpha = tileLayer.options.opacity ?? 1;
        for (const img of tileImgs) {{
            if (!img.complete || img.naturalWidth === 0) continue;
            const mapContainerRect = document.getElementById('leaflet-map').getBoundingClientRect();
            const tileRect = img.getBoundingClientRect();
            const dx = tileRect.left - mapContainerRect.left;
            const dy = tileRect.top  - mapContainerRect.top;
            try {{ ctx.drawImage(img, dx, dy, tileRect.width, tileRect.height); }}
            catch(e) {{ /* CORS-tainted */ }}
        }}
        ctx.globalAlpha = savedAlpha;
    }}

    const serializer = new XMLSerializer();
    const svgClone = overlaySVG.cloneNode(true);
    svgClone.setAttribute('width',  w);
    svgClone.setAttribute('height', h);
    svgClone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    const svgData = serializer.serializeToString(svgClone);
    const blob    = new Blob([svgData], {{ type: 'image/svg+xml;charset=utf-8' }});
    const url     = URL.createObjectURL(blob);

    await new Promise((resolve, reject) => {{
        const img = new Image();
        img.onload = () => {{
            ctx.drawImage(img, 0, 0, w, h);
            URL.revokeObjectURL(url);
            resolve();
        }};
        img.onerror = reject;
        img.src = url;
    }});

    return canvas;
}}


// ── AUTO-SAVE PNG to DB ───────────────────────────────────────────────────
async function autoSavePng() {{
    if (!CTRL_ID) return;
    try {{
        const canvas = await buildMapCanvas();
        canvas.toBlob(blob => {{
            const reader = new FileReader();
            reader.onloadend = () => {{
                const b64 = reader.result.split(',')[1];
                fetch('/web/dataset/call_kw', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        jsonrpc: '2.0', method: 'call', id: 1,
                        params: {{
                            model:  'leyfa.sig.controller',
                            method: 'save_png',
                            args:   [[CTRL_ID], b64],
                            kwargs: {{}},
                        }}
                    }})
                }});
            }};
            reader.readAsDataURL(blob);
        }}, 'image/png');
    }} catch(e) {{
        console.warn('autoSavePng failed:', e);
    }}
}}

// Auto-save 3s after map loads (tiles need time to load)
setTimeout(autoSavePng, 3000);

// ── INIT ──────────────────────────────────────────────────────────────────
const CTRL_ID      = {sig_controller_id if sig_controller_id else 'null'};
const STORAGE_KEY  = `leyfa_sig_state_${{CTRL_ID}}`;

// 1. Valeurs par défaut (venant d'Odoo/Python)
let INIT_ZOOM    = {initial_zoom};
let INIT_LAT     = {_init_lat};
let INIT_LON     = {_init_lon};
let INIT_VISIBLE = {_init_visible};
let INIT_TILES   = {str(initial_tiles_enabled).lower()};
let INIT_TILE_T  = '{initial_tile_type}';
let INIT_TILE_O  = '{initial_tile_opacity}';
let INIT_S_FILT  = '{initial_station_filter}';
let INIT_P_FILT  = '{initial_pk_filter}';
let INIT_GRID    = {'true' if initial_show_grid else 'false'};
let INIT_LABELS  = {'true' if initial_labels_on else 'false'};
let INIT_CONSIST = {'true' if show_consistance_labels else 'false'};
let INIT_SAFETY  = {'true' if show_safety_color else 'false'};

// 2. Tenter de restaurer depuis la session du navigateur (plus récent que le dernier refresh Odoo)
try {{
    const sessionState = JSON.parse(sessionStorage.getItem(STORAGE_KEY));
    if (sessionState) {{
        INIT_ZOOM    = sessionState.zoom || INIT_ZOOM;
        INIT_LAT     = sessionState.center_lat || INIT_LAT;
        INIT_LON     = sessionState.center_lon || INIT_LON;
        INIT_VISIBLE = sessionState.layers_visible ? sessionState.layers_visible.map(l => l.visible) : INIT_VISIBLE;
        INIT_TILES   = sessionState.tiles_enabled !== undefined ? sessionState.tiles_enabled : INIT_TILES;
        INIT_TILE_T  = sessionState.tile_type || INIT_TILE_T;
        INIT_TILE_O  = sessionState.tile_opacity || INIT_TILE_O;
        INIT_S_FILT  = sessionState.station_filter || INIT_S_FILT;
        INIT_P_FILT  = sessionState.pk_filter || INIT_P_FILT;
        INIT_GRID    = sessionState.show_grid !== undefined ? sessionState.show_grid : INIT_GRID;
        INIT_LABELS  = sessionState.labels_on !== undefined ? sessionState.labels_on : INIT_LABELS;
        if (sessionState.show_consistance_labels !== undefined) {{
            INIT_CONSIST = sessionState.show_consistance_labels;
        }}
        if (sessionState.show_safety_color !== undefined) {{
            INIT_SAFETY = sessionState.show_safety_color;
        }}
    }}
}} catch(e) {{ console.error("Session restore failed", e); }}

const LAYER_IDS    = {_layer_ids_js};
if (chkConsistLabels) chkConsistLabels.checked = INIT_CONSIST;
if (chkSafetyColor)   chkSafetyColor.checked   = INIT_SAFETY;
SHOW_CONSISTANCE_LABELS = INIT_CONSIST;
SHOW_SAFETY_COLOR       = INIT_SAFETY;

const chkPkLabels = document.getElementById('chk_pk_labels');
// Auto-setter (called from renderOverlay)
function setPkLabelsAuto(on) {{
    pkLabelsOn = on;
    chkPkLabels.checked = on;
}}
function setPkLabelsManual(on) {{
    pkLabelMode = 'manual';
    pkLabelsOn  = on;
    chkPkLabels.checked = on;
}}

// Wire the checkbox
chkPkLabels.addEventListener('change', () => {{
    setPkLabelsManual(chkPkLabels.checked);
    renderOverlay();
    debouncePersist();
}});

// ── Persist state back to Odoo ────────────────────────────────────────────
let _isInitializing = true;

function persistState() {{
    if (!CTRL_ID) return;
    if (_isInitializing) return;
    
    const center = leafletMap.getCenter();
    const state = {{
        zoom:           leafletMap.getZoom(),
        center_lat:     center.lat,
        center_lon:     center.lng,
        layers_visible: LAYER_IDS.map((id, i) => ({{id: id, visible: layerVisible[i]}})),
        tiles_enabled:  tilesEnabled,
        tile_type:      tileTypeSel.value,
        tile_opacity:   parseInt(tileOpacity.value),
        station_filter: filterSel.value,
        pk_filter:      pkFilter.value,
        show_grid:      chkGrid.checked,
        labels_on:      labelsOn,
        label_mode:     labelMode,
        show_consistance_labels: chkConsistLabels ? chkConsistLabels.checked : null,
        show_safety_color: chkSafetyColor ? chkSafetyColor.checked : null,
    }};

    // SAUVEGARDE EN SESSION (pour les changements d'onglets)
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));

    // SAUVEGARDE EN BASE (pour le futur)
    fetch('/web/dataset/call_kw', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{
            jsonrpc: '2.0', method: 'call', id: 1,
            params: {{
                model:  'leyfa.sig.controller',
                method: 'save_state',
                args:   [[CTRL_ID], state],
                kwargs: {{}},
            }}
        }})
    }});
}}

let _persistTimer = null;
function debouncePersist() {{
    clearTimeout(_persistTimer);
    _persistTimer = setTimeout(persistState, 1200);
}}

// Wire all interactive elements BEFORE setView so events are caught but blocked by flag
leafletMap.on('moveend', debouncePersist);
leafletMap.on('zoomend', debouncePersist);
[tileTypeSel, chkOsm].forEach(
    el => el.addEventListener('change', debouncePersist)
);

// Restore state — all events fired here are blocked by _isInitializing
leafletMap.setView([INIT_LAT, INIT_LON], INIT_ZOOM);
INIT_VISIBLE.forEach((v, i) => {{ if (i < layerVisible.length) layerVisible[i] = v; }});
filterSel.value   = INIT_S_FILT;
pkFilter.value    = INIT_P_FILT;
chkGrid.checked   = INIT_GRID;
chkLabels.checked = INIT_LABELS;
labelMode = '{_init_label_mode}';

if (INIT_TILES) {{
    chkOsm.checked = true;
    tileTypeSel.value = INIT_TILE_T;
    tileOpacity.value = INIT_TILE_O;
    opacityVal.textContent = INIT_TILE_O + '%';
    enableTiles();
}}

if ({str(initial_tiles_enabled).lower()}) {{
    chkOsm.checked = true;
    tileTypeSel.value = '{initial_tile_type}';
    tileOpacity.value = '{initial_tile_opacity}';
    opacityVal.textContent = '{initial_tile_opacity}%';
    enableTiles();
}}

redrawAll();

// Lift the flag AND cancel any timers queued during init
setTimeout(() => {{
    clearTimeout(_persistTimer);
    _isInitializing = false;
}}, 200);
</script>
</body>
</html>"""

        return inner_html

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _render_regions(self) -> str:
        if not self.regions_geojson:
            return ""
        W = H = self.svg_size
        paths = []
        for feature in self.regions_geojson.get("features", []):
            geom      = feature.get("geometry", {})
            geom_type = geom.get("type")

            def ring_to_d(ring):
                pts = []
                for lon, lat in ring:
                    x = (lon - self.lon_min) / (self.lon_max - self.lon_min) * W
                    y = (self.lat_max - lat) / (self.lat_max - self.lat_min) * H
                    pts.append(f"{round(x,1)},{round(y,1)}")
                return "M " + " L ".join(pts) + " Z "

            d = ""
            if geom_type == "Polygon":
                for ring in geom["coordinates"]:
                    d += ring_to_d(ring)
            elif geom_type == "MultiPolygon":
                for polygon in geom["coordinates"]:
                    for ring in polygon:
                        d += ring_to_d(ring)
            if d:
                paths.append(
                    f'<path d="{d}" fill="#e8ede8" stroke="#e8ede8" stroke-width="0.5"/>'
                )
        return "\n".join(paths)

    def _build_layers_js(self) -> str:
        parts = []
        for l in self._layers:
            col = l["colour"].replace("'", "\\'")
            parts.append(
                f'{{'
                f'label:\'{l["label"]}\','
                f'colour:\'{col}\','
                f'gares:{l["gares_js"]},'
                f'pks:{l["pks_js"]},'
                f'coords:{l["coords_js"]},'
                f'ranges:{l.get("ranges_js", "[]")}'
                f'}}'
            )
        return "[" + ",".join(parts) + "]"
    
from odoo import models, fields, api
import json
import os

class LeyfaSigController(models.Model):
    _name = 'leyfa.sig.controller'
    _description = 'Contrôleur de carte SIG (état persistant, générique)'

    name = fields.Char(string="Nom", required=True, default="Nouvelle carte")
    sig_context = fields.Char(
        string="Contexte",
        default="generic",
        help="Identifies who/what created this controller (e.g. 'consistance_view', 'auto', etc.)"
    )


    # ── Map viewport state ────────────────────────────────────────────────
    zoom        = fields.Float(default=5.0)
    center_lat  = fields.Float(default=46.5)
    center_lon  = fields.Float(default=2.5)

    # ── Settings panel state ──────────────────────────────────────────────
    tiles_enabled  = fields.Boolean(default=False)
    tile_type      = fields.Char(default="osmfr")
    tile_opacity   = fields.Integer(default=100)
    station_filter = fields.Selection([
        ('all', 'Toutes'), ('voyageurs', 'Voyageurs'),
        ('fret', 'Fret'),  ('none', 'Aucune'),
    ], default='all')
    pk_filter = fields.Selection([
        ('none', 'Aucun'), ('km', 'km entiers'), ('tenth', '1/10 km'),
    ], default='km')
    show_grid  = fields.Boolean(default=True)
    labels_on  = fields.Boolean(default=False)
    label_mode = fields.Selection([
        ('auto', 'Auto'),
        ('manual', 'Manuel'),
    ], default='auto')

    # ── Context-specific settings ─────────────────────────────────────────
    # consistance_view settings
    show_consistance_labels = fields.Boolean(
        string="Afficher les étiquettes de consistance",
        default=True,
    )
    show_safety_color = fields.Boolean(
        string="Différencier zones de sécurité (orange)",
        default=False,
    )
    pk_legend_label = fields.Char(
        string="Légende PKs",
        default="",
    )

    # ── Layers (the heart of the new design) ─────────────────────────────
    layer_ids = fields.One2many(
        'leyfa.sig.layer', 'controller_id', string="Couches"
    )

    # ── Rendered output ───────────────────────────────────────────────────
    map_html = fields.Html(
        compute="_compute_map_html",
        sanitize=False, sanitize_tags=False,
        store=False,
    )

    @api.depends(
        # ONLY geodata — NOT zoom/center/tiles/filters/etc.
        # State is injected at render time by reading self.* directly,
        # but changes to state alone do NOT retrigger a recompute.
        'layer_ids',
        'layer_ids.ligne_id',
        'layer_ids.ligne_id.geo_shape',
        'layer_ids.ligne_id.gare_ids',
        'layer_ids.ligne_id.pk_ids',
        'layer_ids.highlight_pk_from',
        'layer_ids.highlight_pk_to',
        'layer_ids.colour',
        'layer_ids.label',
        'layer_ids.visible',
        'show_consistance_labels',
        'show_safety_color',
        'name',
    )
    def _compute_map_html(self):
        from .leyfa_sig import LeyfaSIG
        GEOJSON_PATH = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'static', 'src', 'geoJSON', 'regions.geojson'
        )
        for rec in self:
            sig = LeyfaSIG(regions_geojson_path=GEOJSON_PATH)

            for layer in rec.layer_ids:
                track_coords, gares, pks = [], [], []

                # ── Resolve data source ───────────────────────────────────
                if layer.ligne_id:
                    ligne = layer.ligne_id

                    # Track geometry — read directly from the line record
                    if ligne.geo_shape:
                        try:
                            geo = json.loads(ligne.geo_shape)
                            if geo.get('type') == 'LineString':
                                track_coords = geo['coordinates']
                            elif geo.get('type') == 'MultiLineString':
                                for seg in geo['coordinates']:
                                    track_coords.extend(seg)
                        except Exception:
                            pass

                    # Stations — read directly from the line's gare_ids
                    for g in ligne.gare_ids:
                        if not g.latitude or not g.longitude:
                            continue
                        gares.append({
                            'name': g.name or '',
                            'latitude': g.latitude,
                            'longitude': g.longitude,
                            'isV': g.is_voyageurs,
                            'isF': g.is_fret,
                        })

                    pks = []
                    for pk_point in ligne.pk_ids:
                        if not pk_point.lat or not pk_point.lon:
                            continue
                        pks.append({
                            'pk':   pk_point.pk,
                            'name': pk_point.name or str(pk_point.pk),
                            'lat':  pk_point.lat,
                            'lon':  pk_point.lon,
                            # no color here
                        })

                    # Parse ranges from layer
                    try:
                        ranges = json.loads(layer.ranges_json or '[]')
                    except Exception:
                        ranges = []

                    sig.add_ligne_layer(
                        label=layer.label,
                        track_coords=track_coords,
                        gares=gares,
                        pks=pks,
                        colour=layer.colour,
                        odoo_id=layer.id,
                        ranges=ranges,
                    )

            rec.map_html = sig.render(
                title=f"<strong>{rec.name}</strong>",
                width="100%",
                aspect_ratio="1/1",
                initial_zoom=rec.zoom,
                initial_lat=rec.center_lat,
                initial_lon=rec.center_lon,
                initial_layers_visible=[l.visible for l in rec.layer_ids],
                initial_tiles_enabled=rec.tiles_enabled,
                initial_tile_type=rec.tile_type,
                initial_tile_opacity=rec.tile_opacity,
                initial_station_filter=rec.station_filter,
                initial_pk_filter=rec.pk_filter,
                initial_show_grid=rec.show_grid,
                initial_labels_on=rec.labels_on,
                sig_controller_id=rec.id,
                show_consistance_labels=rec.show_consistance_labels,
                show_safety_color=rec.show_safety_color,
                pk_legend_label=rec.pk_legend_label or '',
            )

    def save_state(self, state: dict):
        self.ensure_one()
        vals = {
            'zoom':           state.get('zoom', self.zoom),
            'center_lat':     state.get('center_lat', self.center_lat),
            'center_lon':     state.get('center_lon', self.center_lon),
            'tiles_enabled':  state.get('tiles_enabled', self.tiles_enabled),
            'tile_type':      state.get('tile_type', self.tile_type),
            'tile_opacity':   int(state.get('tile_opacity', self.tile_opacity)),
            'station_filter': state.get('station_filter', self.station_filter),
            'pk_filter':      state.get('pk_filter', self.pk_filter),
            'show_grid':      state.get('show_grid', self.show_grid),
            'labels_on':      state.get('labels_on', self.labels_on),
            'label_mode':     state.get('label_mode', self.label_mode),
        }

        if state.get('show_consistance_labels') is not None:
            vals['show_consistance_labels'] = state['show_consistance_labels']
        if state.get('show_safety_color') is not None:
            vals['show_safety_color'] = state['show_safety_color']

        self.write(vals)

        # Persist per-layer visibility (list of {id, visible})
        for item in state.get('layers_visible', []):
            layer = self.layer_ids.filtered(lambda l: l.id == item['id'])
            if layer:
                layer.visible = item['visible']
        return True
    
    map_png = fields.Binary(string="Carte PNG", attachment=True)
    map_png_filename = fields.Char(default="carte_sig.png")

    def save_png(self, b64_data: str):
        self.ensure_one()
        self.map_png = b64_data
        return True

class LeyfaSigLayer(models.Model):
    _name = 'leyfa.sig.layer'
    _description = 'Couche SIG — référence vers une source de données'
    _order = 'sequence, id'

    controller_id = fields.Many2one(
        'leyfa.sig.controller', required=True, ondelete='cascade', index=True
    )
    sequence  = fields.Integer(default=10)
    label     = fields.Char(string="Libellé", required=True)
    colour    = fields.Char(string="Couleur", default="#1a56db")
    visible   = fields.Boolean(default=True)

    ranges_json = fields.Text(
        string="Zones de travaux (JSON)",
        default="[]",
    )
    @property
    def has_highlight(self):
        try:
            import json
            return bool(json.loads(self.ranges_json or '[]'))
        except Exception:
            return False

    # ── Data source: exactly one should be set ────────────────────────────
    # Today: a rail line. Tomorrow: add more source_* fields here.
    ligne_id = fields.Many2one(
        'leyfa.ligne', string="Ligne ferroviaire",
        ondelete='set null',
    )
    # Future sources (not implemented yet, just show the pattern):
    # infrastructure_id = fields.Many2one('rail.infrastructure', ...)
    # zone_id           = fields.Many2one('rail.zone', ...)

    # ── Optional highlight range (e.g. work zone, consistance) ───────────
    # These are PK values in km. Empty = no highlight.
    highlight_pk_from = fields.Float(string="PK début highlight (km)", default=0.0)
    highlight_pk_to   = fields.Float(string="PK fin highlight (km)",   default=0.0)

    @property
    def has_highlight(self):
        return bool(self.highlight_pk_to and
                    self.highlight_pk_to > self.highlight_pk_from)

    # Pour le td consistance dans le pdf
    colour_rgba = fields.Char(compute='_compute_colour_rgba')
    def _compute_colour_rgba(self):
        for rec in self:
            c = rec.colour.lstrip('#')
            r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            rec.colour_rgba = f"rgba({r},{g},{b},0.12)"