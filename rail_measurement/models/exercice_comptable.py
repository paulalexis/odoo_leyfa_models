from odoo import models, fields

class ExerciceComptable(models.Model):
    _name = 'leyfa.exercice.comptable'
    _description = 'Exercice Comptable'
    _order = 'date_start desc'

    name = fields.Char(
        string='Code Exercice', 
        required=True, 
        help="Lettre d'identification (ex: X, C) utilisée dans le code affaire."
    )
    date_start = fields.Date(string='Date de début', required=True)
    date_end = fields.Date(string='Date de fin', required=True)
    active = fields.Boolean(default=True)

    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.name}] {record.date_start.year}"
            result.append((record.id, name))
        return result