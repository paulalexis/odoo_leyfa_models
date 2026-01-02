from odoo import models, fields, api
import logging

class Chariot(models.Model):
    _name = 'chariot'
    _description = 'Chariot physique'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin'] # Utile pour le suivi

    name = fields.Char(string='Nom du chariot', required=True, tracking=True)
    
    cart_type_id = fields.Many2one(
        'chariot.type',
        string='Type de chariot',
        required=True,
        ondelete='restrict'
    )

    serial_number = fields.Char(string='Numéro de série', required=True)
    
    # On garde le state pour l'état physique (panne, etc.), 
    # mais plus pour la disponibilité planning.
    state = fields.Selection([
        ('available', 'Opérationnel'),
        ('maintenance', 'En maintenance'),
        ('out_of_service', 'Hors service')
    ], default='available', required=True, string="État physique", tracking=True)

    # === CORRECTION DE LA RELATION ===
    measurement_ids = fields.Many2many(
        'rail.measurement',
        'rail_measurement_chariot_assigned_rel', # Même relation que dans RailMeasurement
        'chariot_id',
        'measurement_id',
        string='Planning des mesures',
        readonly=True
    )

    notes = fields.Text()
    active = fields.Boolean(default=True)

    _serial_unique = models.Constraint(
        'unique(serial_number)', 
        'Le numéro de série doit être unique.'
    )

    # === ACTION POUR VOIR LE CALENDRIER ===
    def action_view_calendar(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Planning du {self.name}',
            'res_model': 'rail.measurement',
            'view_mode': 'calendar,list,form',
            'domain': [('assigned_chariot_ids', 'in', self.id)],
            'context': {'default_assigned_chariot_ids': [self.id]}
        }
    
    @api.depends_context('check_avail_start', 'check_avail_end', 'check_avail_id')
    @api.depends('name', 'state', 'serial_number')
    def _compute_display_name(self):
        """
        Calcule le nom affiché dans la liste déroulante.
        Vérifie l'état physique ET la disponibilité calendrier.
        """
        # 1. Récupération des dates depuis le contexte (envoyées par la vue XML)
        start_date = self.env.context.get('check_avail_start')
        end_date = self.env.context.get('check_avail_end')
        current_measure_id = self.env.context.get('check_avail_id')
        
        # 2. Pré-calcul des chariots occupés (Performance)
        booked_cart_ids = []
        if start_date and end_date:
            # On cherche toutes les mesures confirmées/planifiées qui chevauchent
            conflicts = self.env['rail.measurement'].search([
                ('id', '!=', current_measure_id),             # Pas celle-ci
                ('state', 'in', ['planned', 'in_progress']),  # Mesures actives
                ('date_start', '<', end_date),                # Chevauchement
                ('date_end', '>', start_date),
            ])
            # On récupère tous les IDs de chariots utilisés dans ces mesures
            booked_cart_ids = conflicts.mapped('chariot_type_lines.assigned_chariot_ids').ids

        for record in self:
            name = record.name
            prefix = ""
            suffix = ""

            # CAS 1 : Problème Physique (Prioritaire)
            if record.state == 'maintenance':
                prefix = "🔧"
                suffix = " (Maintenance)"
            elif record.state == 'out_of_service':
                prefix = "🔴"
                suffix = " (Hors service)"
            
            # CAS 2 : Problème Planning (Déjà réservé ailleurs)
            elif record.id in booked_cart_ids:
                prefix = "⚠️" # Orange pour attention
                suffix = " (Déjà réservé)"
            
            # CAS 3 : Disponible
            elif record.state == 'available':
                prefix = "🟢"
                suffix = "" # Pas de suffixe, c'est le cas normal
            
            # Construction du nom final
            # Ex: "🟢 LYNX1" ou "⚠️ LYNX2 (Déjà réservé)"
            record.display_name = f"{prefix} {name}{suffix}"
            