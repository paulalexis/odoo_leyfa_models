import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class Contrat(models.Model):
    _name = 'rail.measurement.contrat'
    _description = 'Contrat'

    name = fields.Char(string='Nom', required=True)
    description = fields.Text(string='Description')
    start_date = fields.Date(string='Date de début')
    end_date = fields.Date(string='Date de fin')
    client_id = fields.Many2one('res.partner', string='Client')

    # Modèle de devis associé au contrat
    quotation_template_id = fields.Many2one('sale.order.template', string='BPU')

    report_template_id = fields.Many2one(
        'ir.ui.view',
        string='Modèle de rapport PDF',
        help="Modèle de rapport PDF à utiliser pour les mesures associées à ce contrat. Doit être un template QWeb, le _raw, pas le _document.",
        domain=[('type', '=', 'qweb')],
    )