from ast import Import
import logging
from odoo import models, fields, api, _
import base64
import csv
import io
from odoo.exceptions import UserError
import json
import os
from .leyfa_sig import LeyfaSIG

try:
    import openpyxl
except ImportError:
    openpyxl = None


class PK(models.Model):
    _name = 'leyfa.pk'
    _description = 'Point Kilométrique'

    name = fields.Char(string="PK", compute="_compute_name", store=True)
    ligne_id = fields.Many2one('leyfa.ligne', string="Ligne", ondelete='cascade')
    pk = fields.Float(string="PK (km)")
    vitesse = fields.Float(string="Vitesse (km/h)")
    altitude = fields.Float(string="Altitude (m)")
    altitude_tunnels = fields.Float(string="Altitude Tunnels (m)")
    altitude_declivites = fields.Float(string="Altitude Déclivités (m)")
    lat = fields.Float(string="Latitude")
    lon = fields.Float(string="Longitude")

    @api.depends('pk')
    def _compute_name(self):
        for record in self:
            pk_int = int(record.pk)
            pk_dec = int(round((record.pk - pk_int) * 1000))
            if record.pk >= 0:
                record.name = f"{pk_int:03d}+{pk_dec:03d}" if record.pk is not None else "NaN"
            else:
                record.name = f"{pk_int:03d}-{abs(pk_dec):03d}" if record.pk is not None else "NaN"


class Ligne(models.Model):
    _name = 'leyfa.ligne'
    _description = 'Ligne Ferroviaire'
    _rec_name = 'display_name'

    name = fields.Char(string="Nom de la voie (ex: L650000)", required=True)
    surnom = fields.Char(string="Surnom / Code court", required=True)
    type_voie = fields.Selection([
        ('normale', 'Voie Normale (1435mm)'),
        ('metrique', 'Voie Métrique (1000mm)')
    ], string="Type de voie", default='normale')
    
    gare_ids = fields.One2many('leyfa.gare', 'ligne_id', string="Gares")
    longueur = fields.Float(string="Longueur (km)", digits=(10, 3))
    active = fields.Boolean(default=True)
    display_name = fields.Char(compute="_compute_display_name", store=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Le nom de la ligne doit être unique !'),
        ('surnom_unique', 'unique(surnom)', 'Le surnom de la ligne doit être unique !')
    ]

    @api.depends('name', 'surnom')
    def _compute_display_name(self):
        for record in self:
            surnom = record.surnom or ''
            record.display_name = f"[{surnom}] {record.name}" if surnom else record.name
    
    geo_shape = fields.Text(string="Tracé Géométrique (JSON)", translate=False)
    pk_debut = fields.Char(string="PK Début ligne")
    pk_fin = fields.Char(string="PK Fin ligne")
    statut_ligne = fields.Char(string="Statut")
    pk_ids = fields.One2many('leyfa.pk', 'ligne_id', string="Points Kilométriques")

    map_html = fields.Html(
        compute='_compute_map_html',
        sanitize=False,
        sanitize_tags=False,
        store=False,
    )

    @api.depends('pk_ids', 'gare_ids', 'pk_ids.lat', 'pk_ids.lon',
                'gare_ids.latitude', 'gare_ids.longitude')
    def _compute_map_html(self):
        import os, json
        GEOJSON_PATH = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'static', 'src', 'geoJSON', 'regions.geojson'
        )
        for rec in self:
            if not rec.pk_ids:
                rec.map_html = '<div style="color:#94a3b8;padding:16px;">Aucun PK disponible</div>'
                continue

            sig = LeyfaSIG(regions_geojson_path=GEOJSON_PATH)

            track_coords = [(pk.lat, pk.lon) for pk in rec.pk_ids if pk.lat and pk.lon]
            gares = [{
                'name': g.name,
                'lat':  g.latitude,
                'lon':  g.longitude,
                'pk':   g.pk_text,
                'isV':  True,
                'isF':  False,
            } for g in rec.gare_ids if g.latitude and g.longitude]
            pks = [{
                'pk':    pk.pk,
                'name':  pk.name,
                'lat':   pk.lat,
                'lon':   pk.lon,
                'isInt': (pk.pk == int(pk.pk)) if pk.pk else False,
            } for pk in rec.pk_ids if pk.lat and pk.lon]

            sig.add_ligne_layer(
                label=rec.name,
                track_coords=track_coords,
                gares=gares,
                pks=pks,
                colour='#1a56db',
                odoo_id=None,
                ranges=[],
            )

            # Use render() which wraps in an iframe with fixed dimensions
            rec.map_html = sig.render(
                title=rec.name or '',
                width='100%',
                aspect_ratio='16/9',
                initial_zoom=8,
                initial_station_filter='all',
                initial_labels_on=True,
                initial_pk_filter='km',
                initial_show_grid=True,
                initial_tiles_enabled=False,
            )

class Gare(models.Model):
    _name = 'leyfa.gare'
    _description = 'Gare Ferroviaire'
    _order = 'pk_metrique asc'

    name = fields.Char(string="Nom de la Gare", required=True)
    code_uic = fields.Char(string="Code UIC")
    pk_text = fields.Char(string="PK (Format 000+000)")
    pk_metrique = fields.Integer(string="PK (mètres)", help="Utilisé pour le tri")
    commune = fields.Char(string="Commune")
    departement = fields.Char(string="Département")
    
    ligne_id = fields.Many2one('leyfa.ligne', string="Ligne", ondelete='cascade')
    
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))

    is_voyageurs = fields.Boolean(string="Gare Voyageurs", default=False)
    is_fret = fields.Boolean(string="Gare Fret", default=False)

class ImportGaresWizard(models.TransientModel):
    _name = 'import.gares.wizard' # On définit le nom une fois pour toutes
    _description = 'Importateur Excel SNCF'

    file = fields.Binary(string="Fichier Excel (.xlsx)", required=True)
    filename = fields.Char()

    def action_import(self):
        """ Import du référentiel des GARES (Excel 1) """
        if not self.file: return
        
        file_data = base64.b64decode(self.file)
        wb = openpyxl.load_workbook(io.BytesIO(file_data), data_only=True)
        sheet = wb.active

        ligne_obj = self.env['leyfa.ligne']
        gare_obj = self.env['leyfa.gare']

        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row[4]: continue  # Si pas de code ligne, on passe
            
            code_ligne = str(row[4]).strip()
            
            # Recherche ou création de la ligne
            ligne = ligne_obj.search([('name', '=', code_ligne)], limit=1)
            if not ligne:
                ligne = ligne_obj.create({
                    'name': code_ligne, 
                    'surnom': code_ligne[:3]
                })

            # Calcul du PK métrique pour le tri
            pk_m = 0
            pk_str = str(row[6])
            if '+' in pk_str:
                try:
                    parts = pk_str.split('+')
                    pk_m = int(parts[0]) * 1000 + int(parts[1])
                except: pk_m = 0

            # Création de la gare avec coordonnées
            gare_obj.create({
                'name': str(row[1]).strip(),
                'code_uic': str(row[0]).strip(),
                'pk_text': pk_str,
                'pk_metrique': pk_m,
                'commune': str(row[7]),
                'departement': str(row[8]),
                'longitude': float(row[13]) if row[13] else 0.0,
                'latitude': float(row[14]) if row[14] else 0.0,
                'ligne_id': ligne.id,
                'is_voyageurs': True if str(row[3]) == "O" else False,
                'is_fret': True if str(row[2]) == "O" else False,
            })
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_import_geometry(self):
        """Import des TRACÉS et PK depuis un fichier GeoJSON"""
        if not self.file:
            return

        import json

        file_data = base64.b64decode(self.file)
        try:
            geojson = json.loads(file_data.decode('utf-8'))
        except Exception as e:
            raise UserError(f"Fichier GeoJSON invalide : {e}")

        if geojson.get('type') != 'FeatureCollection':
            raise UserError("Le fichier doit être une FeatureCollection GeoJSON.")

        ligne_obj = self.env['leyfa.ligne']

        for feature in geojson.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})

            code_ligne = str(props.get('code_ligne', '')).strip()
            if not code_ligne:
                continue

            vals = {
                'statut_ligne': props.get('statut', False),
                'pk_debut': props.get('pkd', False),
                'pk_fin': props.get('pkf', False),
                'geo_shape': json.dumps(geom, ensure_ascii=False),
            }

            ligne = ligne_obj.search([('name', '=', code_ligne)], limit=1)
            if ligne:
                ligne.write(vals)
            else:
                vals.update({'name': code_ligne, 'surnom': code_ligne[:3]})
                ligne_obj.create(vals)

        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_import_pks(self):
        """Import des PKs depuis un fichier CSV"""
        if not self.file:
            raise UserError("Veuillez sélectionner un fichier CSV.")

        import csv
        import io

        file_data = base64.b64decode(self.file)
        text = file_data.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text), delimiter=',')

        # Preload all lignes into a dict {name: id} — one single query
        lignes = self.env['leyfa.ligne'].search_read([], ['id', 'name'])
        ligne_map = {l['name']: l['id'] for l in lignes}

        def parse_float(val):
            v = str(val or '').strip().strip('"')
            if not v or v.upper() == 'NULL':
                return 0.0
            try:
                return float(v)
            except ValueError:
                return 0.0

        rows_to_insert = []
        skipped = 0
        not_found = set()

        for row in reader:
            row = {k.strip().strip('"'): v for k, v in row.items()}
            code_ligne = str(row.get('code_ligne', '') or '').strip().strip('"').zfill(6)

            if not code_ligne or code_ligne == '000000':
                skipped += 1
                continue

            ligne_id = ligne_map.get(code_ligne)
            if not ligne_id:
                not_found.add(code_ligne)
                skipped += 1
                continue

            rows_to_insert.append((
                ligne_id,
                parse_float(row.get('pk')),
                parse_float(row.get('vitesse')),
                parse_float(row.get('altitude')),
                parse_float(row.get('altitude_tunnels')),
                parse_float(row.get('altitude_declivites')),
                parse_float(row.get('lat')),
                parse_float(row.get('lon')),
            ))

        # Bulk insert with raw SQL in chunks of 10k
        created = 0
        CHUNK = 10000
        cr = self.env.cr
        for i in range(0, len(rows_to_insert), CHUNK):
            chunk = rows_to_insert[i:i+CHUNK]
            args_str = ','.join(
                cr.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s)", r).decode('utf-8')
                for r in chunk
            )
            cr.execute(f"""
                INSERT INTO leyfa_pk
                    (ligne_id, pk, vitesse, altitude, altitude_tunnels, altitude_declivites, lat, lon)
                VALUES {args_str}
            """)
            created += len(chunk)

        # Recompute name field for all inserted records
        self.env['leyfa.pk'].search([]).modified(['pk'])

        msg = f'{created} PK(s) importé(s), {skipped} ignoré(s).'
        if not_found:
            msg += f' Lignes introuvables : {", ".join(sorted(not_found))}'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Import PKs terminé',
                'message': msg,
                'type': 'warning' if not_found else 'success',
                'sticky': bool(not_found),
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }


class TypeVoie(models.Model):
    _name = 'leyfa.type.voie'
    _description = 'Type de Voie de circulation'
    _order = 'sequence, name'

    name = fields.Char(string="Code", required=True, help="Ex: V1, V2, VU, VC")
    description = fields.Char(string="Description", help="Ex: Voie 1, Voie Unique")
    sequence = fields.Integer(string="Séquence", default=10)
    
    color = fields.Integer(string='Couleur Index')
    
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint(
        'unique(name)', 
        'Ce code de voie existe déjà !'
    )
    
    def name_get(self):
        result = []
        for voie in self:
            if voie.description:
                name = f"{voie.name} - {voie.description}"
            else:
                name = voie.name
            result.append((voie.id, name))
        return result

