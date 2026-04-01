# -*- coding: utf-8 -*-
{
    'name': 'RASCI Matrix',
    'version': '19.0.1.0.0',
    'category': 'Project',
    'summary': 'RASCI responsibility matrix with project tracking and help requests',
    'description': """
        Custom RASCI Matrix Module
        ==========================
        - Define projects with tasks and team members
        - Assign RASCI roles (Responsible, Accountable, Supportive, Consulted, Informed)
        - Interactive matrix view: click cells to assign/change roles
        - Track task progress per project
        - Help requests: anyone can ask for help on a task
        - Volunteers can sign up to help
        - One-click calendar meeting scheduling for help sessions
        - Department grouping with employee ordering
    """,
    'author': 'Custom',
    'depends': ['base', 'hr', 'calendar', 'mail', 'web',],
    'data': [
        'security/rasci_groups.xml',
        'security/ir.model.access.csv',
        'security/rasci_record_rules.xml',
        'views/rasci_project_views.xml',
        'views/rasci_task_views.xml',
        'views/rasci_help_request_views.xml',
        'views/rasci_matrix_view.xml',
        'views/menu.xml',
        'wizards/schedule_meeting_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rasci_matrix/static/src/css/rasci_matrix.css',
            'rasci_matrix/static/src/js/rasci_matrix_widget.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
