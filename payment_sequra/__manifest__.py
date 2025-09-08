# -*- coding: utf-8 -*-

{
    'name': 'SeQura Payment Acquirer',
    'summary': 'SeQura Acquirer: SeQura Implementation',
    'version': '18.0.1.0.0',
    'description': """SeQura Payment Acquirer""",
    'author': 'Raul Fidel Rodríguez Trasanco',
    'website': 'https://github.com/sequra/Conector-Odoo-Sequra-Payment',
    'license': 'LGPL-3',
    'category': 'Accounting/Payment Acquirers',
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
        'views/payment_acquirer.xml',
        'views/res_config_view.xml',
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
