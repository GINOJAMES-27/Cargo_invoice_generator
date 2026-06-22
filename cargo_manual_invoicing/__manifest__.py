{
    'name': 'Cargo Manual Invoicing & PDF Generator',
    'version': '18.0.1.0.0',
    'category': 'Operations',
    'summary': 'Manual cargo invoice entry with dual-language PDF receipts',
    'description': """
        Standalone module for a Saudi-based courier agency.
        - Manual data-entry form for shipment details
        - Dual-language (Arabic/English) QWeb PDF report
        - Reporting with Graph and Pivot views
        - Independent of Odoo native Accounting/Invoicing
    """,
    'author': 'Brightness of Hope Air Cargo Est',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/cargo_manual_invoice_views.xml',
        'views/cargo_report_actions.xml',
        'views/cargo_manual_invoice_menus.xml',
        'report/cargo_manual_invoice_report.xml',
        'report/cargo_manual_invoice_template.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}