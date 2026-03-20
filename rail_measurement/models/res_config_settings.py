from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sncf_reseau_id = fields.Many2one(
        'res.partner',
        string='SNCF Réseau (société parente)',
        config_parameter='rail_measurement.sncf_reseau_id',
    )