from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'
    
    # On garde les CGV qui sont constantes pour la société
    cgv_text = fields.Html(string="Conditions Générales de Vente", default="<h4>Article 1...</h4>")