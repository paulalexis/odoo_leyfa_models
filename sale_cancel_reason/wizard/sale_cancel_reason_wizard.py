# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleCancelReasonWizard(models.TransientModel):
    _name = 'sale.cancel.reason.wizard'
    _description = 'Sale Order Cancellation Wizard'

    order_ids = fields.Many2many(
        'sale.order',
        string='Orders to Cancel',
        required=True,
    )
    reason_id = fields.Many2one(
        'sale.cancel.reason',
        string='Cancellation Reason',
        required=True,
    )
    note = fields.Text(string='Additional Note')
    require_note = fields.Boolean(
        related='reason_id.require_note',
        readonly=True,
    )
    # Summary display
    order_count = fields.Integer(compute='_compute_order_count')
    order_names = fields.Char(compute='_compute_order_count')

    @api.depends('order_ids')
    def _compute_order_count(self):
        for rec in self:
            rec.order_count = len(rec.order_ids)
            rec.order_names = ', '.join(rec.order_ids.mapped('name'))

    @api.constrains('reason_id', 'note')
    def _check_note_required(self):
        for rec in self:
            if rec.reason_id and rec.reason_id.require_note and not (rec.note or '').strip():
                raise ValidationError(
                    _('The selected reason requires an additional note. Please fill it in.')
                )

    def action_confirm_cancel(self):
        self.ensure_one()
        # Trigger the actual cancel (with audit log)
        self.order_ids._action_cancel_with_reason(
            reason_id=self.reason_id.id,
            note=self.note,
        )
        # Close the wizard — caller will refresh the view
        return {'type': 'ir.actions.act_window_close'}
