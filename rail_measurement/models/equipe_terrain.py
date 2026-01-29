from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class EquipeTerrain(models.Model):
    _name = 'equipe.terrain'
    _description = 'Équipe de terrain'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string="Nom de l'équipe", required=True, tracking=True)
    active = fields.Boolean(default=True)

    # Personnel
    leader_id = fields.Many2one(
        'hr.employee', 
        string="Chef d'équipe", 
        required=True, 
        tracking=True,
        domain="[('active', '=', True)]"
    )
    
    member_ids = fields.Many2many(
        'hr.employee', 
        'equipe_terrain_employee_rel',
        'equipe_id', 
        'employee_id',
        string="Membres d'équipe",
        tracking=True
    )

    # Chariots
    chariot_lynx_id = fields.Many2one(
        'chariot', 
        string='Chariot LYNX',
        domain=[('cart_type_id.name', '=', 'LYNX')],
        tracking=True
    )

    chariot_lynx_plus_id = fields.Many2one(
        'chariot', 
        string='Chariot LYNX PLUS',
        domain=[('cart_type_id.name', '=', 'LYNX PLUS')],
        tracking=True
    )

    # === CORRECTION : RELATION CALCULÉE ===
    # On utilise un Many2many calculé pour afficher les mesures des deux champs
    measurement_ids = fields.Many2many(
        'rail.measurement',
        string='Plannings de mesures',
        compute='_compute_measurement_ids'
    )

    def _compute_measurement_ids(self):
        for record in self:
            # On cherche les mesures où l'équipe est en position 1 OU en position 2
            measurements = self.env['rail.measurement'].search([
                '|',
                ('equipe_id_1', '=', record.id),
                ('equipe_id_2', '=', record.id)
            ])
            record.measurement_ids = measurements

    color = fields.Char(
        string="Couleur de l'équipe",
        default="#875A7B",
        tracking=True
    )

    @api.constrains('member_ids', 'leader_id')
    def _check_composition_equipe(self):
        for record in self:
            if record.leader_id in record.member_ids:
                raise ValidationError(_("Le chef d'équipe ne peut pas être membre de sa propre équipe."))

    # Dans equipe_terrain.py
    def action_view_calendar(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Planning détaillé : {self.name}',
            'res_model': 'rail.measurement.planning', # On cible les lignes de semaine
            'view_mode': 'calendar,list',
            'domain': ['|', ('equipe_id_1', '=', self.id), ('equipe_id_2', '=', self.id)],
            'context': {
                'search_default_equipe_id_1': self.id,
            }
    }
        
    @api.depends_context('check_avail_start', 'check_avail_end', 'check_avail_id')
    def _compute_display_name(self):
        start_date = self.env.context.get('check_avail_start')
        end_date = self.env.context.get('check_avail_end')
        current_id = self.env.context.get('check_avail_id')

        # Dictionnaire pour stocker : {id_equipe: "code_affaire"}
        booked_teams_info = {}

        if start_date and end_date:
            # On cherche les conflits
            conflicts = self.env['rail.measurement'].search([
                ('id', '!=', current_id),
                ('date_start', '<', end_date),
                ('date_end', '>', start_date),
                ('state', '!=', 'cancel'),
            ])
            
            for conflict in conflicts:
                # On récupère le code (ou le nom si code_affaire est vide)
                label = conflict.code_affaire or conflict.name or "Inconnue"
                
                if conflict.equipe_id_1:
                    booked_teams_info[conflict.equipe_id_1.id] = label
                if conflict.equipe_id_2:
                    booked_teams_info[conflict.equipe_id_2.id] = label

        for record in self:
            prefix = "🟢"
            suffix = f" (RCE : {record.leader_id.name})"
            
            # Si l'ID de l'équipe est dans notre dictionnaire de conflits
            if record.id in booked_teams_info:
                prefix = "⚠️"
                affair_code = booked_teams_info[record.id]
                suffix = f" <Occupée : {affair_code}>"
            
            record.display_name = f"{prefix} {record.name}{suffix}"

    planning_ids_all = fields.Many2many(
        'rail.measurement.planning',
        compute='_compute_planning_ids_all',
        string="Détail de toutes les semaines"
    )

    def _compute_planning_ids_all(self):
        for record in self:
            # On cherche toutes les lignes de planning dont la mesure parente 
            # possède cette équipe en équipe 1 OU équipe 2
            planning_lines = self.env['rail.measurement.planning'].search([
                '|',
                ('measurement_id.equipe_id_1', '=', record.id),
                ('measurement_id.equipe_id_2', '=', record.id)
            ])
            record.planning_ids_all = planning_lines
