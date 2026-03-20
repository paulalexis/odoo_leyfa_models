# -*- coding: utf-8 -*-
{
    'name': 'Sale Cancel Reason',
    'version': '19.0.1.0.0',
    'summary': 'Force a cancellation reason when cancelling a sale order',
    'category': 'Sales',
    'author': 'LEYFA MEASUREMENT',
    'depends': ['sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'data/sale_cancel_reason_data.xml',
        'wizard/sale_cancel_reason_wizard_views.xml',
        'views/sale_cancel_reason_views.xml',
        'views/sale_cancel_log_views.xml',
        'views/sale_menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
