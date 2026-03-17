from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta

class EquipeCompositionHebdo(models.Model):
    _name = 'equipe.composition.hebdo'
    _description = 'Composition hebdomadaire de l\'équipe'
    _order = 'week_start desc, equipe_id'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    equipe_id = fields.Many2one(
        'equipe.terrain',
        string="Équipe",
        required=True,
        ondelete='cascade'
    )
    
    week_start = fields.Date(
        string="Début de semaine (Lundi)",
        required=True,
        help="Premier jour de la semaine (lundi)"
    )
    
    week_end = fields.Date(
        string="Fin de semaine (Dimanche)",
        compute='_compute_week_end',
        store=True
    )
    
    week_number = fields.Char(
        string="Semaine",
        compute='_compute_week_info',
        store=True
    )
    
    # Chef d'équipe pour cette semaine (peut être différent du chef habituel)
    leader_id = fields.Many2one(
        'hr.employee',
        string="Chef d'équipe cette semaine",
        required=True,
        domain="[('active', '=', True)]"
    )
    
    # Membres présents cette semaine
    member_ids = fields.Many2many(
        'hr.employee',
        'equipe_composition_hebdo_employee_rel',
        'composition_id',
        'employee_id',
        string="Membres présents",
        help="Employés qui seront présents cette semaine"
    )
    
    # Membres absents (pour info)
    absent_member_ids = fields.Many2many(
        'hr.employee',
        'equipe_composition_hebdo_absent_rel',
        'composition_id',
        'employee_id',
        string="Membres absents",
        help="Membres habituels de l'équipe absents cette semaine"
    )
    
    # Raison de modification
    modification_reason = fields.Text(
        string="Raison de la modification",
        help="Congés, apprentis ajoutés, remplacements, etc."
    )
    
    # Chariots assignés (peuvent changer selon la semaine)
    chariot_lynx_id = fields.Many2one(
        'chariot',
        string='Chariot LYNX cette semaine',
        domain=[('cart_type_id.name', '=', 'LYNX')]
    )
    
    chariot_lynx_plus_id = fields.Many2one(
        'chariot',
        string='Chariot LYNX PLUS cette semaine',
        domain=[('cart_type_id.name', '=', 'LYNX PLUS')]
    )
    
    # État de validation
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validé'),
    ], default='draft', string="État", tracking=True)
    
    # Champs calculés
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True
    )
    
    total_members = fields.Integer(
        compute='_compute_total_members',
        string="Effectif total"
    )
    
    # Lien vers les affaires de la semaine
    measurement_ids = fields.Many2many(
        'rail.measurement',
        compute='_compute_measurement_ids',
        string="Affaires cette semaine"
    )
    
    notes = fields.Html(string="Notes")
    
    @api.depends('week_start')
    def _compute_week_end(self):
        for record in self:
            if record.week_start:
                # Le dimanche est 6 jours après le lundi
                record.week_end = record.week_start + timedelta(days=6)
            else:
                record.week_end = False
    
    @api.depends('week_start')
    def _compute_week_info(self):
        for record in self:
            if record.week_start:
                week_num = record.week_start.isocalendar()[1]
                year = record.week_start.year
                record.week_number = f"S{week_num:02d} - {year}"
            else:
                record.week_number = ""
    
    @api.depends('equipe_id', 'week_number')
    def _compute_display_name(self):
        for record in self:
            if record.equipe_id and record.week_number:
                record.display_name = f"{record.equipe_id.name} - {record.week_number}"
            else:
                record.display_name = "Nouvelle composition"
    
    @api.depends('member_ids')
    def _compute_total_members(self):
        for record in self:
            record.total_members = len(record.member_ids) + 1  # +1 pour le chef
    
    def _compute_measurement_ids(self):
        for record in self:
            if record.week_start and record.week_end:
                measurements = self.env['rail.measurement'].search([
                    '|',
                    ('equipe_id_1', '=', record.equipe_id.id),
                    ('equipe_id_2', '=', record.equipe_id.id),
                    ('date_start', '<=', record.week_end),
                    ('date_end', '>=', record.week_start),
                    ('state', '!=', 'cancel')
                ])
                record.measurement_ids = measurements
            else:
                record.measurement_ids = False
    
    @api.constrains('member_ids', 'leader_id')
    def _check_composition(self):
        for record in self:
            if record.leader_id in record.member_ids:
                raise ValidationError(
                    _("Le chef d'équipe ne peut pas être aussi dans les membres.")
                )
    
    @api.constrains('week_start', 'equipe_id')
    def _check_unique_week(self):
        for record in self:
            existing = self.search([
                ('id', '!=', record.id),
                ('equipe_id', '=', record.equipe_id.id),
                ('week_start', '=', record.week_start)
            ])
            if existing:
                raise ValidationError(
                    _("Une composition existe déjà pour cette équipe cette semaine.")
                )
    
    @api.onchange('equipe_id', 'week_start')
    def _onchange_equipe_defaults(self):
        """Pré-remplit avec la composition standard de l'équipe"""
        if self.equipe_id and not self.leader_id:
            self.leader_id = self.equipe_id.leader_id
            self.member_ids = self.equipe_id.member_ids
            self.chariot_lynx_id = self.equipe_id.chariot_lynx_id
            self.chariot_lynx_plus_id = self.equipe_id.chariot_lynx_plus_id
    
    def action_validate(self):
        self.write({'state': 'validated'})
    
    def action_draft(self):
        self.write({'state': 'draft'})
    
    def action_copy_from_previous_week(self):
        """Copie la composition de la semaine précédente"""
        self.ensure_one()
        if not self.week_start:
            return
        
        previous_week = self.week_start - timedelta(days=7)
        previous_composition = self.search([
            ('equipe_id', '=', self.equipe_id.id),
            ('week_start', '=', previous_week)
        ], limit=1)
        
        if previous_composition:
            self.write({
                'leader_id': previous_composition.leader_id.id,
                'member_ids': [(6, 0, previous_composition.member_ids.ids)],
                'chariot_lynx_id': previous_composition.chariot_lynx_id.id,
                'chariot_lynx_plus_id': previous_composition.chariot_lynx_plus_id.id,
            })
    
    @api.model
    def _search_panel_domain_image(self, field_name, domain, set_count=False, limit=False):
        """Pour les filtres de recherche avancés"""
        return super()._search_panel_domain_image(field_name, domain, set_count, limit)
    
    # Domaines pour les filtres
    @api.model
    def _get_current_week_domain(self):
        """Retourne le domaine pour la semaine en cours"""
        today = fields.Date.today()
        return [
            ('week_start', '<=', today),
            ('week_end', '>=', today)
        ]
    
    @api.model
    def _get_future_weeks_domain(self):
        """Retourne le domaine pour les semaines futures"""
        today = fields.Date.today()
        return [('week_start', '>=', today)]
    
    @api.model
    def _get_past_weeks_domain(self):
        """Retourne le domaine pour les semaines passées"""
        today = fields.Date.today()
        return [('week_end', '<', today)]
    
    @api.model
    def _get_this_month_domain(self):
        """Retourne le domaine pour ce mois"""
        today = fields.Date.today()
        first_day = today.replace(day=1)
        # Dernier jour du mois
        if today.month == 12:
            last_day = today.replace(day=31)
        else:
            last_day = (today.replace(month=today.month + 1, day=1) - timedelta(days=1))
        
        return [
            ('week_start', '>=', first_day),
            ('week_start', '<=', last_day)
        ]

class EquipeTerrain(models.Model):
    _name = 'equipe.terrain'
    _description = 'Équipe de terrain'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string="Nom de l'équipe", required=True, tracking=True)
    active = fields.Boolean(default=True)

    # Personnel (COMPOSITION STANDARD)
    leader_id = fields.Many2one(
        'hr.employee', 
        string="Chef d'équipe (Standard)", 
        required=True, 
        tracking=True,
        domain="[('active', '=', True)]",
        help="Chef d'équipe habituel (peut être modifié chaque semaine)"
    )
    
    member_ids = fields.Many2many(
        'hr.employee', 
        'equipe_terrain_employee_rel',
        'equipe_id', 
        'employee_id',
        string="Membres d'équipe (Standard)",
        tracking=True,
        help="Composition standard de l'équipe (peut être modifiée chaque semaine)"
    )

    # Chariots (STANDARD)
    chariot_lynx_id = fields.Many2one(
        'chariot', 
        string='Chariot LYNX (Standard)',
        domain=[('cart_type_id.name', '=', 'LYNX')],
        tracking=True
    )

    chariot_lynx_plus_id = fields.Many2one(
        'chariot', 
        string='Chariot LYNX PLUS (Standard)',
        domain=[('cart_type_id.name', '=', 'LYNX PLUS')],
        tracking=True
    )

    # NOUVEAU : Compositions hebdomadaires
    composition_hebdo_ids = fields.One2many(
        'equipe.composition.hebdo',
        'equipe_id',
        string="Compositions hebdomadaires",
        help="Compositions spécifiques par semaine"
    )
    
    # Compteur de compositions futures
    future_compositions_count = fields.Integer(
        compute='_compute_future_compositions_count',
        string="Compositions futures"
    )

    # === CORRECTION : RELATION CALCULÉE ===
    measurement_ids = fields.Many2many(
        'rail.measurement',
        string='Plannings de mesures',
        compute='_compute_measurement_ids'
    )

    def _compute_measurement_ids(self):
        for record in self:
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

    def action_view_calendar(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Planning détaillé : {self.name}',
            'res_model': 'rail.measurement.planning',
            'views': [
                (self.env.ref('rail_measurement.view_rail_measurement_planning_calendar').id, 'calendar'),
                (False, 'list')
            ],
            'view_mode': 'calendar,list',
            'domain': ['|', ('equipe_id_1', '=', self.id), ('equipe_id_2', '=', self.id)],
            'context': {'search_default_equipe_id_1': self.id},
            'target': 'current',
        }
    
    def _compute_future_compositions_count(self):
        today = fields.Date.today()
        for record in self:
            record.future_compositions_count = self.env['equipe.composition.hebdo'].search_count([
                ('equipe_id', '=', record.id),
                ('week_start', '>=', today)
            ])
    
    def action_view_compositions(self):
        """Ouvre la vue des compositions hebdomadaires"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Compositions hebdomadaires : {self.name}',
            'res_model': 'equipe.composition.hebdo',
            'view_mode': 'kanban,list,form,calendar',
            'domain': [('equipe_id', '=', self.id)],
            'context': {
                'default_equipe_id': self.id,
                'default_leader_id': self.leader_id.id,
                'default_member_ids': [(6, 0, self.member_ids.ids)],
            }
        }
    
    def action_plan_next_weeks(self):
        """Crée automatiquement les compositions pour les 4 prochaines semaines"""
        self.ensure_one()
        today = fields.Date.today()
        # Trouver le lundi de cette semaine
        days_since_monday = today.weekday()
        this_monday = today - timedelta(days=days_since_monday)
        
        created_count = 0
        for week_offset in range(4):
            week_start = this_monday + timedelta(weeks=week_offset)
            
            # Vérifier si existe déjà
            existing = self.env['equipe.composition.hebdo'].search([
                ('equipe_id', '=', self.id),
                ('week_start', '=', week_start)
            ])
            
            if not existing:
                self.env['equipe.composition.hebdo'].create({
                    'equipe_id': self.id,
                    'week_start': week_start,
                    'leader_id': self.leader_id.id,
                    'member_ids': [(6, 0, self.member_ids.ids)],
                    'chariot_lynx_id': self.chariot_lynx_id.id,
                    'chariot_lynx_plus_id': self.chariot_lynx_plus_id.id,
                })
                created_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Compositions créées'),
                'message': _(f'{created_count} composition(s) créée(s) pour les 4 prochaines semaines'),
                'type': 'success',
                'sticky': False,
            }
        }
        
    @api.depends_context('check_avail_start', 'check_avail_end', 'check_avail_id')
    def _compute_display_name(self):
        start_date = self.env.context.get('check_avail_start')
        end_date = self.env.context.get('check_avail_end')
        current_id = self.env.context.get('check_avail_id')

        booked_teams_info = {}

        if start_date and end_date:
            conflicts = self.env['rail.measurement'].search([
                ('id', '!=', current_id),
                ('date_start', '<', end_date),
                ('date_end', '>', start_date),
                ('state', '!=', 'cancel'),
            ])
            
            for conflict in conflicts:
                label = conflict.code_affaire or conflict.name or "Inconnue"
                
                if conflict.equipe_id_1:
                    booked_teams_info[conflict.equipe_id_1.id] = label
                if conflict.equipe_id_2:
                    booked_teams_info[conflict.equipe_id_2.id] = label

        for record in self:
            prefix = "🟢"
            suffix = f" (RCE : {record.leader_id.name})"
            
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

    # def _compute_planning_ids_all(self):
    #     for record in self:
    #         planning_lines = self.env['rail.measurement'].search([
    #             '|',
    #             ('equipe_id_1', '=', record.id),
    #             ('equipe_id_2', '=', record.id)
    #         ])
    #         record.planning_ids_all = planning_lines
    
    def _compute_planning_ids_all(self):
        for record in self:
            # Search all rail.measurement linked to this team
            measurements = self.env['rail.measurement'].search([
                '|',
                ('equipe_id_1', '=', record.id),
                ('equipe_id_2', '=', record.id)
            ])
            # If planning_ids_all should link to measurement IDs
            record.planning_ids_all = [(6, 0, measurements.ids)]
    
    def get_composition_for_week(self, week_start):
        """
        Retourne la composition pour une semaine donnée.
        Si aucune composition spécifique n'existe, retourne la composition standard.
        """
        self.ensure_one()
        composition = self.env['equipe.composition.hebdo'].search([
            ('equipe_id', '=', self.id),
            ('week_start', '=', week_start)
        ], limit=1)
        
        if composition:
            return {
                'leader': composition.leader_id,
                'members': composition.member_ids,
                'chariot_lynx': composition.chariot_lynx_id,
                'chariot_lynx_plus': composition.chariot_lynx_plus_id,
            }
        else:
            # Composition standard
            return {
                'leader': self.leader_id,
                'members': self.member_ids,
                'chariot_lynx': self.chariot_lynx_id,
                'chariot_lynx_plus': self.chariot_lynx_plus_id,
            }