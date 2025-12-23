from odoo import models, fields

class TypeAffaire(models.Model):
    _name = 'leyfa.affaire.type'
    _description = "Type d'affaire LeyFa"
    _order = 'sequence, id'

    name = fields.Char(string="Nom du type", required=True, help="ex: Préparation de chantier")
    code = fields.Char(string="Code", required=True, help="ex: P, C, INS, MOE")
    description = fields.Text(string="Description / Notes")
    sequence = fields.Integer(default=10) # Pour gérer l'ordre d'affichage
    active = fields.Boolean(default=True)
    requires_nature = fields.Boolean(
        string="Nécessite Nature (R/E)", 
        default=False,
        help="Si coché, l'utilisateur devra choisir entre Relevé (R) ou Étude (E) pour le code."
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Le code du type d\'affaire doit être unique !')
    ]