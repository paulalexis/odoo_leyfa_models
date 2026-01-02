{
    'name': 'Test Process',
    'version': '1.0',
    'author': 'Your Name',
    'depends': ['base', 'web', 'web_widget_mermaid_field'],
    'data': [
        'security/ir.model.access.csv',
        'views/test_process_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
