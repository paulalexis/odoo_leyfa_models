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
        'rasci.task', string='Tâche', required=True, ondelete='cascade',
    )
    project_id = fields.Many2one(
        'rasci.project', related='task_id.project_id',
        string='Projet', store=True, readonly=True,
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employé', ondelete='cascade',
    )
    external_member_id = fields.Many2one(
        'rasci.project.member', string='Membre externe', ondelete='cascade',
    )
    role = fields.Selection(RASCI_ROLES, string='Rôle', required=True)
    role_label = fields.Char(string='Label du rôle', compute='_compute_role_label')
    description = fields.Char(string='Rôle spécifique')
    report = fields.Text(string='Rapport')

    @api.depends('role')
    def _compute_role_label(self):
        role_map = dict(RASCI_ROLES)
        for rec in self:
            rec.role_label = role_map.get(rec.role, '')

    @api.constrains('employee_id', 'external_member_id')
    def _check_assignee(self):
        for rec in self:
            if not rec.employee_id and not rec.external_member_id:
                raise models.ValidationError(
                    "Une désignation de rôle doit avoir un employé ou un membre externe."
                )
            if rec.employee_id and rec.external_member_id:
                raise models.ValidationError(
                    "Une désignation de rôle ne peut pas avoir à la fois un employé et un membre externe."
                )

    _sql_constraints = [
        (
            'unique_task_employee_role',
            'UNIQUE(task_id, employee_id, role)',
            'Ce rôle est déjà attribué à cet employé pour cette tâche.',
        ),
        (
            'unique_task_external_role',
            'UNIQUE(task_id, external_member_id, role)',
            'Ce rôle est déjà attribué à ce membre externe pour cette tâche.',
        ),
    ]

    @api.model
    def get_matrix_data(self, project_id):
        assignments = self.search([('project_id', '=', project_id)])
        result = {}
        for a in assignments:
            # Use ext_{member_id} as key for externals, employee_id for internals
            if a.external_member_id:
                member_key = f'ext_{a.external_member_id.id}'
            else:
                member_key = str(a.employee_id.id)
            key = f'{a.task_id.id}_{member_key}'
            if key not in result:
                result[key] = []
            result[key].append({
                'role':        a.role,
                'description': a.description or '',
                'report':      a.report or '',
            })
        role_order = ['R', 'A', 'S', 'C', 'I']
        for key in result:
            result[key].sort(
                key=lambda x: role_order.index(x['role']) if x['role'] in role_order else 99
            )
        return result

    @api.model
    def set_role(self, task_id, member_key, role, description="", report=""):
        """
        member_key is either:
          - an integer employee_id  (internal member)
          - a string "ext_{member_id}"  (external member)
        """
        is_external = isinstance(member_key, str) and member_key.startswith('ext_')
        domain = [('task_id', '=', task_id), ('role', '=', role)]
        vals = {'task_id': task_id, 'role': role,
                'description': description or '', 'report': report or ''}

        if is_external:
            ext_id = int(member_key.split('_', 1)[1])
            domain.append(('external_member_id', '=', ext_id))
            vals['external_member_id'] = ext_id
        else:
            domain.append(('employee_id', '=', int(member_key)))
            vals['employee_id'] = int(member_key)

        existing = self.search(domain, limit=1)
        if existing:
            existing.unlink()
            return {'member_key': member_key, 'role': role, 'action': 'removed'}
        else:
            self.create(vals)
            return {'member_key': member_key, 'role': role, 'action': 'added'}

    @api.model
    def update_role(self, task_id, member_key, role, description="", report=""):
        is_external = isinstance(member_key, str) and member_key.startswith('ext_')
        domain = [('task_id', '=', task_id), ('role', '=', role)]

        if is_external:
            ext_id = int(member_key.split('_', 1)[1])
            domain.append(('external_member_id', '=', ext_id))
        else:
            domain.append(('employee_id', '=', int(member_key)))

        existing = self.search(domain, limit=1)
        if existing:
            existing.write({'description': description or '', 'report': report or ''})
            return True
        return False