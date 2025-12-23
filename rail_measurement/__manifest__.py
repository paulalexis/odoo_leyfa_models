{
    'name': 'Rail Measurement Management',
    'version': '1.0',
    'category': 'Services',
    'summary': 'Gestion des prestations de mesure de voie ferrée',
    'description': """
Rail Measurement Management
============================

Ce module permet de gérer les prestations de mesure de voie ferrée avec :
* Création de produits spécifiques pour les mesures
* Intégration directe dans les devis/commandes
* Gestion des chariots de mesure
* Suivi des équipes et des prestations
* Calcul automatique des prix au kilomètre
* Wizard de configuration lors de l'ajout au devis

Le système permet d'ajouter des prestations de mesure directement comme des produits
dans les devis, puis de les configurer avec tous les détails techniques nécessaires.
    """,
    'author': 'Votre Société',
    'website': 'https://www.votresite.com',
    'depends': [
        'base',
        'sale_management',
        'product',
        'hr',
        'uom',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/measurement.xml',
        'views/affaires.xml',
        'data/rail_measurement_data.xml',
        'data/codes_affaires_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rail_measurement/static/src/js/rail_measurement_button.js',
            'rail_measurement/static/src/css/style.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}