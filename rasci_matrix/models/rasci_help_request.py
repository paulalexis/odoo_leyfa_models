# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class RasciHelpRequest(models.Model):
    _name = 'rasci.help.request'
    _description = 'RASCI Support'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Sujet',
        required=True,
        default='Support demandé',
    )
    project_id = fields.Many2one(
        'rasci.project',
        string='Projet',
        required=True,
        ondelete='cascade',
    )
    task_id = fields.Many2one(
        'rasci.task',
        string='Tâche',
        required=True,
        ondelete='cascade',
        domain="[('project_id', '=', project_id)]",
    )
    requester_id = fields.Many2one(
        'hr.employee',
        string='Demandé par',
        required=True,
        default=lambda self: self.env.user.employee_id,
    )
    description = fields.Text(string='Description du besoin')
    state = fields.Selection(
        [
            ('open', 'Ouvert'),
            ('meeting_scheduled', 'Réunion planifiée'),
            ('resolved', 'Résolu'),
            ('cancelled', 'Annulé'),
        ],
        string='Etat',
        default='open',
        tracking=True,
    )
    volunteer_ids = fields.Many2many(
        'hr.employee',
        'rasci_help_volunteer_rel',
        'help_request_id',
        'employee_id',
        string='Voluntaires',
    )
    volunteer_count = fields.Integer(
        string='Nombre de volontaires',
        compute='_compute_volunteer_count',
        store=True,
    )
    meeting_id = fields.Many2one(
        'calendar.event',
        string='Réunion planifiée',
        readonly=True,
    )
    meeting_date = fields.Datetime(
        related='meeting_id.start',
        string='Date de la réunion',
        readonly=True,
    )
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Urgent')],
        string='Priorité',
        default='0',
    )

    @api.depends('volunteer_ids')
    def _compute_volunteer_count(self):
        for rec in self:
            rec.volunteer_count = len(rec.volunteer_ids)

    def action_volunteer(self):
        """Current user volunteers to help."""
        self.ensure_one()
        employee = self.env.user.employee_id
        if not employee:
            raise UserError("Vous devez être associé(e) à un employé pour pouvoir participer.")
        if employee in self.volunteer_ids:
            raise UserError("Vous avez déjà participé à cette demande.")
        self.volunteer_ids = [(4, employee.id)]
        return True

    def action_withdraw_volunteer(self):
        """Current user withdraws from volunteering."""
        self.ensure_one()
        employee = self.env.user.employee_id
        if employee in self.volunteer_ids:
            self.volunteer_ids = [(3, employee.id)]

    def action_schedule_meeting(self):
        """Open wizard to schedule a meeting with all volunteers."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Planifier une réunion de support',
            'res_model': 'rasci.schedule.meeting.wizard',
            'view_mode': 'form',
            'context': {
                'default_help_request_id': self.id,
            },
            'target': 'new',
        }

    def action_resolve(self):
        self.write({'state': 'resolved'})

    def action_reopen(self):
        self.write({'state': 'open'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
