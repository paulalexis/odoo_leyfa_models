# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError

class RasciProject(models.Model):
    _name = 'rasci.project'
    _description = 'Projet RASCI'
    _order = 'sequence, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom du projet', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    client = fields.Char(string='Client')
    deadline = fields.Date(string='Date limite')
    description = fields.Html(string='Description')
    state = fields.Selection(
        [
            ('draft', 'Brouillon'),
            ('active', 'Actif'),
            ('on_hold', 'En attente'),
            ('done', 'Terminé'),
            ('cancelled', 'Annulé'),
        ],
        string='Etat',
        default='draft',
        tracking=True,
    )
    color = fields.Integer(string='Color')
    task_ids = fields.One2many(
        'rasci.task',
        'project_id',
        string='Tâches',
    )
    task_count = fields.Integer(
        string='Total Tâches',
        compute='_compute_progress',
        store=True,
    )
    done_task_count = fields.Integer(
        string='Tâches Terminées',
        compute='_compute_progress',
        store=True,
    )
    progress = fields.Float(
        string='Progression (%)',
        compute='_compute_progress',
        store=True,
    )
    help_request_ids = fields.One2many(
        'rasci.help.request',
        'project_id',
        string='Demandes de support',
    )
    open_help_request_count = fields.Integer(
        string='Demandes de support ouvertes',
        compute='_compute_open_help_requests',
    )
    matrix_project_id = fields.Integer(
        string='Matrice ID',
        compute='_compute_matrix_project_id',
    )
    member_ids = fields.One2many('rasci.project.member', 'project_id', string='Membres')
    
    def _get_default_pilot(self):
        return self.env.user.employee_id
    
    pilot_id = fields.Many2one(
        'hr.employee', 
        string='Pilote du projet', 
        default=_get_default_pilot,
        tracking=True
    )

    @api.onchange('pilot_id')
    def _onchange_pilot_id(self):
        """ Automatically adds the pilot to the member list if not already present """
        if self.pilot_id:
            # Check if this employee is already in the member list
            existing_member = self.member_ids.filtered(lambda m: m.employee_id == self.pilot_id)
            if not existing_member:
                # Add pilot as a new member
                # (0, 0, values) is the Odoo command to create a new linked record
                self.member_ids = [(0, 0, {
                    'employee_id': self.pilot_id.id,
                    'sequence': 5, # Give pilot a high priority sequence
                })]
    
    @api.model_create_multi
    def create(self, vals_list):
        """ Ensure pilot is added to members on creation even if onchange didn't fire """
        projects = super(RasciProject, self).create(vals_list)
        for project in projects:
            if project.pilot_id:
                existing = project.member_ids.filtered(lambda m: m.employee_id == project.pilot_id)
                if not existing:
                    self.env['rasci.project.member'].create({
                        'project_id': project.id,
                        'employee_id': project.pilot_id.id,
                        'sequence': 5,
                    })
        return projects


    def _compute_matrix_project_id(self):
        for rec in self:
            rec.matrix_project_id = rec.id

    @api.depends('task_ids', 'task_ids.state')
    def _compute_progress(self):
        for project in self:
            tasks = project.task_ids
            total = len(tasks)
            done = len(tasks.filtered(lambda t: t.state == 'done'))
            project.task_count = total
            project.done_task_count = done
            project.progress = (done / total * 100) if total else 0.0

    def _compute_open_help_requests(self):
        for project in self:
            project.open_help_request_count = self.env['rasci.help.request'].search_count([
                ('project_id', '=', project.id),
                ('state', 'in', ('open', 'meeting_scheduled')),
            ])

    def action_open_help_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Demandes de support — {self.name}',
            'res_model': 'rasci.help.request',
            'view_mode': 'kanban,list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_open_tasks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Tâches — {self.name}',
            'res_model': 'rasci.task',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_view_matrix(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Matrice RASCI — {self.name}',
            'res_model': 'rasci.project',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('rasci_matrix.view_rasci_project_matrix_form').id, 'form')],
            'target': 'current',
        }
    
    my_roles_summary = fields.Html(
        string='Mes rôles sur ce projet',
        compute='_compute_my_roles_summary'
    )

    @api.depends_context('uid')
    def _compute_my_roles_summary(self):
        employee = self.env.user.employee_id
        
        # Color map for RASCI badges
        color_map = {
            'R': '#198754', 'A': '#0d6efd', 'S': '#6f42c1', 'C': '#fd7e14', 'I': '#6c757d',
        }
        
        # Symbol map for Task States
        state_symbols = {
            'not_started': '○',
            'in_progress': '◐',
            'blocked':     '✕',
            'done':        '✓',
        }

        for project in self:
            if not employee:
                project.my_roles_summary = False
                continue
            
            assignments = self.env['rasci.role.assignment'].search([
                ('task_id.project_id', '=', project.id),
                ('employee_id', '=', employee.id)
            ])
            
            if not assignments:
                project.my_roles_summary = False
                continue

            # Group by task record instead of just name to access .state
            task_data = {}
            for asn in assignments:
                task = asn.task_id
                if task not in task_data:
                    task_data[task] = []
                task_data[task].append(asn.role)
            
            summary_parts = []
            RASCI_ORDER = ['R', 'A', 'S', 'C', 'I']
            for task_rec, roles in task_data.items():
                # 1. Generate RASCI badges — sorted in R→A→S→C→I order
                role_badges = "".join([
                    f"<span style='background:{color_map.get(r)};color:#fff;padding:1px 5px;border-radius:3px;font-size:10px;margin-right:3px;font-weight:bold;'>{r}</span>"
                    for r in sorted(roles, key=lambda r: RASCI_ORDER.index(r) if r in RASCI_ORDER else 99)
                ])
                
                # 2. Get State Symbol and Color
                symbol = state_symbols.get(task_rec.state, '')
                # Optional: Color coding the symbols
                symbol_color = "#198754" if task_rec.state == 'done' else \
                               "#dc3545" if task_rec.state == 'blocked' else "#6c757d"

                # 3. Build row with Flexbox to push symbol to the right
                summary_parts.append(
                    f"<li style='margin-bottom:4px; display: flex; align-items: center; justify-content: space-between;'>"
                    f"<span>{role_badges} <span style='font-size: 11px;'>{task_rec.name}</span></span>"
                    f"<span style='color: {symbol_color}; font-weight: bold; margin-left: 10px;'>{symbol}</span>"
                    f"</li>"
                )
            
            project.my_roles_summary = f"<ul style='list-style:none;padding-left:0;margin-bottom:0;'>{''.join(summary_parts)}</ul>"

    @api.model
    def get_current_user_can_edit(self, project_id):
        project = self.browse(project_id)
        employee = self.env.user.employee_id
        if project.pilot_id:
            if employee and project.pilot_id == employee:
                return True
            if project.pilot_id.user_id == self.env.user:
                return True
        if not employee:
            return False
        member = self.env['rasci.project.member'].sudo().search([
            ('project_id', '=', project_id),
            ('employee_id', '=', employee.id),
        ], limit=1)
        return member.can_edit if member else False

    can_edit = fields.Boolean(
        string='Peut modifier',
        compute='_compute_can_edit',
    )

    @api.depends_context('uid')
    def _compute_can_edit(self):
        for project in self:
            if project._origin.id:
                project.can_edit = project.get_current_user_can_edit(project._origin.id)
            else:
                project.can_edit = True  # new unsaved record

    def _is_pilot(self):
        """Check if current user is the pilot, with or without an employee record."""
        self.ensure_one()
        if not self.pilot_id:
            return False
        employee = self.env.user.employee_id
        if employee and self.pilot_id == employee:
            return True
        return self.pilot_id.user_id == self.env.user

    def _check_edit_rights(self):
        if self.env.su:
            return
        for project in self:
            if project._is_pilot():
                continue
            employee = self.env.user.employee_id
            if not employee:
                raise UserError("Vous n'avez pas les droits pour modifier ce projet.")
            member = self.env['rasci.project.member'].sudo().search([
                ('project_id', '=', project.id),
                ('employee_id', '=', employee.id),
            ], limit=1)
            if not member or not member.can_edit:
                raise UserError("Vous n'avez pas les droits pour modifier ce projet.")

    def unlink(self):
        if not self.env.su:
            for project in self:
                if not project._is_pilot():
                    employee = self.env.user.employee_id
                    member = self.env['rasci.project.member'].sudo().search([
                        ('project_id', '=', project.id),
                        ('employee_id', '=', employee.id),
                    ], limit=1)
                    if not member or not member.can_edit:
                        raise UserError("Vous n'avez pas les droits pour supprimer ce projet. Si vous pensez que c'est une erreur, contactez le pilote du projet.")
        return super().unlink()

    def action_active(self):
        self._check_edit_rights()
        self.write({'state': 'active'})

    def action_done(self):
        self._check_edit_rights()
        self.write({'state': 'done'})

    def action_reset_draft(self):
        self._check_edit_rights()
        self.write({'state': 'draft'})

    deadline_color_code = fields.Char(
        compute="_compute_deadline_color_code",
        store=False,
    )
    deadline_days_left = fields.Integer(
        compute="_compute_deadline_color_code",
        store=False,
    )

    @api.depends("deadline")
    def _compute_deadline_color_code(self):
        today = fields.Date.today()
        for record in self:
            if not record.deadline:
                record.deadline_color_code = "none"
                record.deadline_days_left = 0
            else:
                delta = (record.deadline - today).days
                record.deadline_days_left = abs(delta)
                if record.deadline == today:
                    record.deadline_color_code = "danger"
                elif delta < 0:
                    record.deadline_color_code = "danger"
                elif delta <= 15:
                    record.deadline_color_code = "soon"
                else:
                    record.deadline_color_code = "muted"

class RasciProjectMember(models.Model):
    _name = 'rasci.project.member'
    _description = 'Membre du projet'
    _order = 'sequence, id'

    project_id = fields.Many2one('rasci.project', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', required=False, ondelete='cascade')
    is_external = fields.Boolean(string='Membre externe', default=False)
    external_name = fields.Char(string='Nom externe')
    sequence = fields.Integer(default=10)
    department_id = fields.Many2one(
        related='employee_id.department_id',
        store=True, readonly=True
    )
    can_edit = fields.Boolean(string='Peut modifier la matrice', default=False)

    @api.constrains('is_external', 'employee_id', 'external_name')
    def _check_member_identity(self):
        for rec in self:
            if rec.is_external:
                if not rec.external_name:
                    raise UserError("Un membre externe doit avoir un nom.")
            else:
                if not rec.employee_id:
                    raise UserError("Un membre interne doit avoir un employé associé.")

    def unlink(self):
        for member in self:
            if not member.is_external and member.employee_id:
                self.env['rasci.role.assignment'].search([
                    ('employee_id', '=', member.employee_id.id),
                    ('task_id.project_id', '=', member.project_id.id)
                ]).unlink()
        return super().unlink()
    