# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------------
    # Public entry point
    # The wizard calls this method directly after collecting the reason,
    # bypassing the wizard trigger so we don't loop.
    # ------------------------------------------------------------------
    def _action_cancel_with_reason(self, reason_id=None, note=None):
        """Actually cancel the order(s) and write the audit log."""
        for order in self:
            # Write log entry before cancelling so order data is still intact
            self.env['sale.cancel.log'].create({
                'order_id': order.id,
                'order_name': order.name,
                'user_id': self.env.uid,
                'reason_id': reason_id,
                'note': note,
                'partner_id': order.partner_id.id,
                'amount_total': order.amount_total,
                'currency_id': order.currency_id.id,
            })
        # Call the original cancel logic (skipping our override via context flag)
        return super(SaleOrder, self.with_context(_skip_cancel_wizard=True)).action_cancel()

    # ------------------------------------------------------------------
    # Override action_cancel to always raise the wizard
    # ------------------------------------------------------------------
    def action_cancel(self):
        # If the wizard already confirmed and set the flag, proceed normally.
        if self.env.context.get('_skip_cancel_wizard'):
            return super().action_cancel()

        # Filter to orders that are actually cancellable (not already cancelled/draft)
        cancellable = self.filtered(lambda o: o.state not in ('cancel', 'draft'))
        if not cancellable:
            return super().action_cancel()

        # Raise the wizard for all contexts (button, server action, code…)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cancellation Reason'),
            'res_model': 'sale.cancel.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_ids': cancellable.ids,
                # preserve any caller context
                **self.env.context,
            },
        }
