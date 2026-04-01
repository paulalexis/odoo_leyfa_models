# -*- coding: utf-8 -*-
from odoo import models, fields, api


class RasciTask(models.Model):
    _name = 'rasci.task'
    _description = 'Tâche RASCI'
    _order = 'sequence, id'

    name = fields.Char(string='Nom de la Tâche', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    project_id = fields.Many2one(
        'rasci.project',
        string='Projet',
        required=True,
        ondelete='cascade',
    )
    description = fields.Text(string='Description')
    state = fields.Selection(
        [
            ('not_started', 'Non commencé'),
            ('in_progress', 'En cours'),
            ('blocked', 'Bloqué'),
            ('done', 'Terminé'),
        ],
        string='Etat',
        default='not_started',
        tracking=True,
    )
    state_color = fields.Char(
        string='Couleur de l\'état',
        compute='_compute_state_color',
    )
    role_assignment_ids = fields.One2many(
        'rasci.role.assignment',
        'task_id',
        string='Désignations de rôles',
    )
    help_request_ids = fields.One2many(
        'rasci.help.request',
        'task_id',
        string='Demandes de support',
    )
    open_help_request_count = fields.Integer(
        string='Demandes de support ouvertes',
        compute='_compute_open_help_requests',
    )

    @api.depends('state')
    def _compute_state_color(self):
        color_map = {
            'not_started': '#e0e0e0',
            'in_progress': '#fff3cd',
            'blocked': '#f8d7da',
            'done': '#d4edda',
        }
        for task in self:
            task.state_color = color_map.get(task.state, '#ffffff')

    def _compute_open_help_requests(self):
        for task in self:
            task.open_help_request_count = self.env['rasci.help.request'].search_count([
                ('task_id', '=', task.id),
                ('state', 'in', ('open', 'meeting_scheduled')),
            ])

    def get_role_for_employee(self, employee_id):
        """Return the RASCI role letter for a given employee on this task, or empty string."""
        assignment = self.role_assignment_ids.filtered(
            lambda a: a.employee_id.id == employee_id
        )
        return assignment.role if assignment else ''

    def action_request_help(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Demande de support — {self.name}',
            'res_model': 'rasci.help.request',
            'view_mode': 'form',
            'context': {
                'default_task_id': self.id,
                'default_project_id': self.project_id.id,
            },
            'target': 'new',
        }


    def action_open_help_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Demandes de support — {self.name}',
            'res_model': 'rasci.help.request',
            'view_mode': 'kanban,list,form',
            'domain': [('task_id', '=', self.id)],
            'context': {'default_task_id': self.id, 'default_project_id': self.project_id.id},
        }