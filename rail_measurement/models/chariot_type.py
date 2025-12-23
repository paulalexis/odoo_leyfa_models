from odoo import models, fields

class ChariotType(models.Model):
    _name = 'chariot.type'
    _description = 'Type de chariot de mesure'

    name = fields.Char(string='Type de chariot', required=True)
    manufacturer = fields.Char(string='Fabricant')

    notes = fields.Text(string='Description / capacités')

    # cart_ids = fields.One2many(
    #     'chariot',
    #     'cart_type_id',
    #     string='Chariots physiques'
    # )

