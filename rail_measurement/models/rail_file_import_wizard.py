import base64
import logging
from datetime import datetime
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)

class RailFileImportWizard(models.TransientModel):
    _name = 'rail.file.import.wizard'
    _description = 'Wizard Import Fichier de Mesure'

    file = fields.Binary(string="Fichier .lx / .txt", required=True)
    file_name = fields.Char()
    
    state = fields.Selection([('upload', 'Import'), ('select', 'Sélection')], default='upload')
    match_ids = fields.Many2many('rail.measurement', string="Mesures correspondantes")
    selected_measurement_id = fields.Many2one('rail.measurement', string="Choisir la mesure")

    # Champs techniques pour conserver les données parsées entre deux étapes du wizard
    parsed_date = fields.Date()
    parsed_first_pk = fields.Float()
    parsed_last_pk = fields.Float()

    def action_analyze(self):
        self.ensure_one()
        
        # 1. Décodage et lecture
        try:
            file_binary = base64.b64decode(self.file)
        except Exception:
            raise exceptions.UserError("Erreur lors de la lecture du fichier binaire.")

        content = False
        for encoding in ['utf-8', 'iso-8859-1']:
            try:
                content = file_binary.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not content:
            raise exceptions.UserError("Format de texte non reconnu (UTF-8 ou Latin-1 requis).")

        # 2. Parsing du Header
        header = {}
        lines = content.splitlines()
        for line in lines:
            if ':' in line:
                key, val = line.split(':', 1)
                header[key.strip()] = val.strip()

        try:
            # Nettoyage des données pour correspondre aux surnoms/noms Odoo
            h_ligne_raw = header.get('LIGNE', '').strip()
            h_ligne = 'L' + h_ligne_raw if not h_ligne_raw.startswith('L') else h_ligne_raw
            
            h_date_raw = header.get('DATE', '')
            h_date = datetime.strptime(h_date_raw, '%d/%m/%Y').date()
            
            h_voie_raw = header.get('VOIE', '').strip()
            h_voie = 'V' + h_voie_raw if not h_voie_raw.startswith('V') else h_voie_raw
            
            h_lorry = header.get('LORRY', '').strip()
            h_pk_header = float(header.get('PK', 0))
        except (ValueError, TypeError):
            raise exceptions.UserError("Entête de fichier invalide (Ligne, Date, Voie, Lorry ou PK manquants).")

        # 3. Parsing du tableau (Extraction PK début et fin)
        data_lines = []
        table_started = False
        for line in lines:
            if "PK" in line and "Temps" in line:
                table_started = True
                continue
            if table_started and line.strip():
                data_lines.append(line)

        if not data_lines:
            raise exceptions.UserError("Le fichier ne contient aucune donnée de mesure après l'entête.")

        try:
            # On extrait les PK réels du tableau (Colonne 2, index 1)
            first_pk = float(data_lines[0].split('\t')[1].strip())
            last_pk = float(data_lines[-1].split('\t')[1].strip())
        except (ValueError, IndexError):
            raise exceptions.UserError("Erreur lors de l'extraction des PK dans le tableau de mesures.")

        # Mémorisation technique dans le wizard
        self.write({
            'parsed_date': h_date,
            'parsed_first_pk': first_pk,
            'parsed_last_pk': last_pk
        })

        # 4. Recherche de la mesure
        domain = [
            ('ligne_id', '=', h_ligne),
            ('date_start', '<=', h_date),
            ('date_end', '>=', h_date),
            ('pk_initial', '<=', h_pk_header),
            ('pk_final', '>=', h_pk_header),
            ('chariot_type_lines.assigned_chariot_ids.serial_number', '=', h_lorry),
            ('voie_ids.name', '=', h_voie)
        ]
        
        matches = self.env['rail.measurement'].search(domain)

        if not matches:
            # Aide au debug pour l'utilisateur
            last = self.env['rail.measurement'].search([], order='create_date desc', limit=1)
            error_msg = _("❌ Aucune mesure correspondante trouvée.\n\n")
            error_msg += f"FICHIER : Ligne {h_ligne} | Date {h_date} | Voie {h_voie} | Lorry {h_lorry} | PK {h_pk_header:.3f}\n\n"
            if last:
                v = ", ".join(last.voie_ids.mapped('name'))
                l = ", ".join(last.chariot_type_lines.mapped('assigned_chariot_ids.serial_number'))
                error_msg += f"DERNIÈRE ODOO ({last.reference}) : Ligne {last.ligne_id.surnom} | Voies [{v}] | Lorrys [{l}] | PK {last.pk_initial:.3f} à {last.pk_final:.3f}"
            raise exceptions.UserError(error_msg)

        if len(matches) == 1:
            return self._attach_to_measurement(matches[0])

        # Cas multiples : on passe à l'étape de sélection
        self.write({
            'state': 'select',
            'match_ids': [(6, 0, matches.ids)]
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm_selection(self):
        self.ensure_one()
        if not self.selected_measurement_id:
            raise exceptions.UserError("Veuillez sélectionner une mesure dans la liste.")
        return self._attach_to_measurement(self.selected_measurement_id)

    def _attach_to_measurement(self, measurement):
        """Affectation finale au jour et à la semaine correspondante"""
        
        # 1. Trouver le jour (mon, tue...)
        day_map = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        day_key = day_map[self.parsed_date.weekday()]

        # 2. Trouver la semaine de planning
        planning_line = measurement.planning_ids.filtered(
            lambda p: p.date_start <= self.parsed_date <= p.date_end
        )

        if not planning_line:
            # Si le planning n'est pas généré, on l'annule ou on crée le fichier sur la mesure
            raise exceptions.UserError(f"Le planning de la mesure {measurement.reference} n'est pas généré pour la date du {self.parsed_date}.")

        # 3. Créer l'enregistrement du fichier journalier
        self.env['rail.measurement.day.file'].create({
            'planning_id': planning_line[0].id,
            'day': day_key,
            'file': self.file,
            'file_name': self.file_name,
        })

        # 4. Mettre à jour l'avancement de la mesure globale
        measurement.write({
            'avancement_start': self.parsed_first_pk,
            'avancement_end': self.parsed_last_pk,
        })

        _logger.info("Fichier lié avec succès à %s (Semaine %s, Jour %s)", measurement.reference, planning_line[0].week_label, day_key)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Importation réussie',
                'message': f'Le fichier a été classé dans le planning de {measurement.reference}.',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }