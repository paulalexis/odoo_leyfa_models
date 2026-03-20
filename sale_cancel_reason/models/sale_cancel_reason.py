# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleCancelReason(models.Model):
    _name = 'sale.cancel.reason'
    _description = 'Sale Order Cancellation Reason'
    _order = 'sequence, name'

    name = fields.Char(string='Reason', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    require_note = fields.Boolean(
        string='Require additional note',
        help='If checked, the user must fill in a free-text note when selecting this reason.',
    )
