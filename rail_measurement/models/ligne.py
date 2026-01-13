from odoo import models, fields, api

class Ligne(models.Model):
    _name = 'leyfa.ligne'
    _description = 'Ligne Ferroviaire'

    name = fields.Char(string="Nom de la voie (ex: L650000)", required=True)
    surnom = fields.Char(string="Surnom / Code court (ex: 650, TMB)", required=True, help="Utilisé pour la génération du code affaire")
    
    type_voie = fields.Selection([
        ('normale', 'Voie Normale (1435mm)'),
        ('metrique', 'Voie Métrique (1000mm)')
    ], string="Type de voie", default='normale')
    
    gares = fields.Char(string="Gares")
    
    longueur = fields.Float(string="Longueur (km)", digits=(10, 3))
    
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint(
        'unique(name)', 
        'Le nom de la ligne doit être unique !'
    )
    
    _surnom_unique = models.Constraint(
        'unique(surnom)', 
        'Le surnom de la ligne doit être unique !'
    )

    def name_get(self):
        result = []
        for rec in self:
            name = rec.name or ''
            surnom = rec.surnom or ''
            if surnom:
                display = f"{name} ({surnom})"
            else:
                display = name
            result.append((rec.id, display))
        return result


class TypeVoie(models.Model):
    _name = 'leyfa.type.voie'
    _description = 'Type de Voie de circulation'
    _order = 'sequence, name'

    name = fields.Char(string="Code", required=True, help="Ex: V1, V2, VU, VC")
    description = fields.Char(string="Description", help="Ex: Voie 1, Voie Unique")
    sequence = fields.Integer(string="Séquence", default=10)
    
    color = fields.Integer(string='Couleur Index')
    
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint(
        'unique(name)', 
        'Ce code de voie existe déjà !'
    )
    
    def name_get(self):
        result = []
        for voie in self:
            if voie.description:
                name = f"{voie.name} - {voie.description}"
            else:
                name = voie.name
            result.append((voie.id, name))
        return result