# -*- coding: utf-8 -*-

{
    'name': 'SeQura Payment Provider',
    'summary': 'SeQura Provider: SeQura Payment Integration for Odoo 18',
    'version': '18.0.1.0.0',
    'description': """SeQura Payment Provider for Odoo 18""",
    'author': 'Raul Fidel Rodríguez Trasanco',
    'website': 'https://github.com/sequra/Conector-Odoo-Sequra-Payment',
    'license': 'LGPL-3',
    'category': 'Accounting/Payment Providers',
    'depends': [
        'product',
        'delivery',
        'payment',
        'website',
        'website_sale'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sequra.xml',
        'views/payment_provider.xml',
        'views/website_template.xml',
        'views/sale_view.xml',
        'views/product.xml',
        'data/sequra.xml'
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_sequra/static/src/js/template.js',
        ],
    },
    'images': [
        'static/description/icon.png'
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
