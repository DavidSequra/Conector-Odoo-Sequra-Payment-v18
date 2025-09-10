from odoo import api, fields, models

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    ends_in = fields.Char(
        string='Service end date',
        default='P6M',
        required=True,
        index=True
    )