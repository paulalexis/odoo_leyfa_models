from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'
    
    # On ne garde qu'un champ global pour la fin des mentions
    contract_footer_text = fields.Html(
        string="Fin des mentions contractuelles (Fixe)",
        help="Ce texte apparaîtra à la fin de tous les devis.",
        default="""<p><strong>Validité :</strong> Cette offre est valable 30 jours.</p>
<p><strong>Paiement :</strong> 30% à la commande, solde à 30 jours fin de mois.</p>"""
    )
    
    # On garde les CGV qui sont constantes pour la société
    cgv_text = fields.Html(string="Conditions Générales de Vente", default="<h4>Article 1...</h4>")

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Champ spécifique au devis
    contract_intro_text = fields.Html(
        string="Introduction spécifique au devis",
        default="""<p>Nous avons le plaisir de vous faire parvenir notre proposition pour...</p>"""
    )