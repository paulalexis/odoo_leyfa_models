# -*- coding: utf-8 -*-
from odoo import models, fields, api


RASCI_ROLES = [
    ('R', 'R — Responsible'),
    ('A', 'A — Accountable'),
    ('S', 'S — Supportive'),
    ('C', 'C — Consulted'),
    ('I', 'I — Informed'),
]


class RasciRoleAssignment(models.Model):
    _name = 'rasci.role.assignment'
    _description = 'Désignation des rôles RASCI'
    _order = 'task_id, employee_id'

    task_id = fields.Many2one(
        'rasci.task',
        string='Tâche',
        required=True,
        ondelete='cascade',
    )
    project_id = fields.Many2one(
        'rasci.project',
        related='task_id.project_id',
        string='Projet',
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employé',
        required=True,
        ondelete='cascade',
    )
    role = fields.Selection(
        RASCI_ROLES,
        string='Rôle',
        required=True,
    )
    role_label = fields.Char(
        string='Label du rôle',
        compute='_compute_role_label',
    )
    description = fields.Char(string='Rôle spécifique')
    report = fields.Text(string='Rapport')

    @api.depends('role')
    def _compute_role_label(self):
        role_map = dict(RASCI_ROLES)
        for rec in self:
            rec.role_label = role_map.get(rec.role, '')

    _sql_constraints = [
        (
            'unique_task_employee_role',
            'UNIQUE(task_id, employee_id, role)',
            'Ce rôle est déjà attribué à cet employé pour cette tâche.',
        )
    ]

    @api.model
    def get_matrix_data(self, project_id):
        assignments = self.search([('project_id', '=', project_id)])
        result = {}
        for a in assignments:
            key = f'{a.task_id.id}_{a.employee_id.id}'
            if key not in result:
                result[key] = []
            result[key].append({
                'role': a.role,
                'description': a.description or '',
                'report': a.report or '',
            })
        role_order = ['R', 'A', 'S', 'C', 'I']
        for key in result:
            result[key].sort(key=lambda x: role_order.index(x['role']) if x['role'] in role_order else 99)
        return result

    @api.model
    def set_role(self, task_id, employee_id, role, description="", report=""):
        existing = self.search([
            ('task_id', '=', task_id),
            ('employee_id', '=', employee_id),
            ('role', '=', role),
        ], limit=1)
        if existing:
            existing.unlink()
            return {'task_id': task_id, 'employee_id': employee_id, 'role': role, 'action': 'removed'}
        else:
            self.create({
                'task_id': task_id,
                'employee_id': employee_id,
                'role': role,
                'description': description or '',
                'report': report or '',
            })
            return {'task_id': task_id, 'employee_id': employee_id, 'role': role, 'action': 'added'}
        
    @api.model
    def update_role(self, task_id, employee_id, role, description="", report=""):
        """Update description/report without toggling the role."""
        existing = self.search([
            ('task_id', '=', task_id),
            ('employee_id', '=', employee_id),
            ('role', '=', role),
        ], limit=1)
        if existing:
            existing.write({
                'description': description or '',
                'report': report or '',
            })
            return True
        return False