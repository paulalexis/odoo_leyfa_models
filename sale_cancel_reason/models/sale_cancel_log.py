# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleCancelLog(models.Model):
    _name = 'sale.cancel.log'
    _description = 'Sale Order Cancellation Log'
    _order = 'cancel_date desc'
    # Read-only audit log — no one should edit or delete entries.
    _rec_name = 'order_name'

    order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        ondelete='set null',   # keep log even if SO is deleted
        index=True,
    )
    order_name = fields.Char(
        string='Order Reference',
        required=True,
        help='Stored at cancellation time so the log survives order deletion.',
    )
    cancel_date = fields.Datetime(
        string='Cancelled On',
        required=True,
        default=fields.Datetime.now,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Cancelled By',
        required=True,
        default=lambda self: self.env.user,
    )
    reason_id = fields.Many2one(
        'sale.cancel.reason',
        string='Reason',
        ondelete='restrict',
    )
    note = fields.Text(string='Additional Note')
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
    )
    amount_total = fields.Monetary(
        string='Order Total',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one('res.currency', string='Currency')
