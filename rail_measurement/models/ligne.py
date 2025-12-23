from odoo import models, fields

class Ligne(models.Model):
    _name = 'leyfa.ligne'
    _description = 'Ligne Ferroviaire'

    name = fields.Char(string="Nom de la voie (ex: L650000)", required=True)
    surnom = fields.Char(string="Surnom / Code court (ex: 650, TMB)", required=True, help="Utilisé pour la génération du code affaire")
    
    type_voie = fields.Selection([
        ('normale', 'Voie Normale (1435mm)'),
        ('metrique', 'Voie Métrique (1000mm)')
    ], string="Type de voie", default='normale')
    
    gare_depart = fields.Char(string="Gare de début")
    gare_fin = fields.Char(string="Gare de fin")
    
    longueur = fields.Float(string="Longueur (km)", digits=(10, 3))
    
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Le nom de la ligne doit être unique !'),
        ('surnom_unique', 'unique(surnom)', 'Le surnom de la ligne doit être unique !')
    ]