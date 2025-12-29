{
    'name': 'Test Process',
    'version': '1.0',
    'depends': ['base', 'web', 'web_widget_mermaid_field'],
    'data': [
        'security/ir.model.access.csv',
        'views/test_process_views.xml',
    ],
    'installable': True,
    'application': True,
}
