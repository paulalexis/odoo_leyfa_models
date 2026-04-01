# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class RasciScheduleMeetingWizard(models.TransientModel):
    _name = 'rasci.schedule.meeting.wizard'
    _description = 'Schedule Help Meeting Wizard'

    help_request_id = fields.Many2one(
        'rasci.help.request',
        string='Help Request',
        required=True,
    )
    meeting_name = fields.Char(
        string='Meeting Title',
        compute='_compute_defaults',
        store=True,
        readonly=False,
    )
    start_datetime = fields.Datetime(
        string='Start',
        required=True,
        default=fields.Datetime.now,
    )
    duration = fields.Float(
        string='Duration (hours)',
        default=1.0,
    )
    attendee_ids = fields.Many2many(
        'hr.employee',
        string='Attendees',
        compute='_compute_defaults',
        store=True,
        readonly=False,
    )
    location = fields.Char(string='Location / Link')
    notes = fields.Text(string='Meeting Notes / Agenda')

    @api.depends('help_request_id')
    def _compute_defaults(self):
        for wizard in self:
            if wizard.help_request_id:
                req = wizard.help_request_id
                wizard.meeting_name = f"[Help] {req.task_id.name} — {req.name}"
                # Include requester + all volunteers
                employees = req.volunteer_ids | req.requester_id
                wizard.attendee_ids = [(6, 0, employees.ids)]
            else:
                wizard.meeting_name = ''
                wizard.attendee_ids = [(5,)]

    def action_create_meeting(self):
        self.ensure_one()
        req = self.help_request_id

        # Build partner list from employees
        partners = self.attendee_ids.mapped('user_id.partner_id').filtered(bool)
        if not partners:
            raise UserError(
                "No attendees have linked user accounts. "
                "Please ensure employees have Odoo user accounts."
            )

        import datetime
        stop = self.start_datetime + datetime.timedelta(hours=self.duration)

        meeting_vals = {
            'name': self.meeting_name,
            'start': self.start_datetime,
            'stop': stop,
            'location': self.location or '',
            'description': self.notes or '',
            'partner_ids': [(6, 0, partners.ids)],
        }
        meeting = self.env['calendar.event'].create(meeting_vals)

        req.write({
            'meeting_id': meeting.id,
            'state': 'meeting_scheduled',
        })

        # Log a note on the help request
        req.message_post(
            body=f'Meeting scheduled: <b>{self.meeting_name}</b> on {self.start_datetime.strftime("%d/%m/%Y %H:%M")}',
            subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Meeting',
            'res_model': 'calendar.event',
            'res_id': meeting.id,
            'view_mode': 'form',
            'target': 'current',
        }
