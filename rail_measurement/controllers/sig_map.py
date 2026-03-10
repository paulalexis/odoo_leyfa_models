# controllers/sig_map.py
from odoo import http
from odoo.http import request
import json
import os

class SigMapController(http.Controller):

    @http.route('/leyfa/sig/map/<int:controller_id>', auth='user', type='http')
    def sig_map(self, controller_id, **kwargs):
        ctrl = request.env['leyfa.sig.controller'].browse(controller_id)
        if not ctrl.exists():
            return request.not_found()

        # Invalidate cache to get fresh data
        request.env['leyfa.sig.layer'].invalidate_model(['ranges_json'])

        from ..models.leyfa_sig import LeyfaSIG

        GEOJSON_PATH = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'static', 'src', 'geoJSON', 'regions.geojson'
        )

        sig = LeyfaSIG(regions_geojson_path=GEOJSON_PATH)

        for layer in ctrl.layer_ids:
            track_coords, gares, pks = [], [], []

            # Parse ranges from layer
            try:
                ranges = json.loads(layer.ranges_json or '[]')
            except Exception:
                ranges = []

            if layer.ligne_id:
                ligne = layer.ligne_id
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

                for g in ligne.gare_ids:
                    if not g.latitude or not g.longitude:
                        continue
                    gares.append({
                        'name':      g.name or '',
                        'latitude':  g.latitude,
                        'longitude': g.longitude,
                        'isV':       g.is_voyageurs,
                        'isF':       g.is_fret,
                    })

                for pk_point in ligne.pk_ids:
                    if not pk_point.lat or not pk_point.lon:
                        continue
                    pks.append({
                        'pk':   pk_point.pk,
                        'name': pk_point.name or str(pk_point.pk),
                        'lat':  pk_point.lat,
                        'lon':  pk_point.lon,
                        # no color — JS computes it from layer.ranges
                    })

            sig.add_ligne_layer(
                label=layer.label,
                track_coords=track_coords,
                gares=gares,
                pks=pks,
                colour=layer.colour,
                odoo_id=layer.id,
                ranges=ranges,    # ← key change
            )

        html = sig.render_raw(
            title=f"<strong>{ctrl.name}</strong>",
            initial_zoom=ctrl.zoom,
            initial_lat=ctrl.center_lat,
            initial_lon=ctrl.center_lon,
            initial_layers_visible=[l.visible for l in ctrl.layer_ids],
            initial_tiles_enabled=ctrl.tiles_enabled,
            initial_tile_type=ctrl.tile_type,
            initial_tile_opacity=ctrl.tile_opacity,
            initial_station_filter=ctrl.station_filter,
            initial_pk_filter=ctrl.pk_filter,
            initial_show_grid=ctrl.show_grid,
            initial_labels_on=ctrl.labels_on,
            sig_controller_id=ctrl.id,
            show_consistance_labels=ctrl.show_consistance_labels,
            pk_legend_label=ctrl.pk_legend_label,
        )

        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('X-Frame-Options', 'SAMEORIGIN'),
        ])