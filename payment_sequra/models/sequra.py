# -*- coding: utf-8 -*-

import logging
import requests

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ProviderSequra(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('sequra', 'SeQura')],
        ondelete={'sequra': 'set default'}
    )

    sequra_merchant_id = fields.Char(
        string='Merchant ID', 
        required_if_provider='sequra', 
        groups='base.group_system'
    )
    sequra_api_key = fields.Char(
        string='API Key', 
        required_if_provider='sequra', 
        groups='base.group_system'
    )
    sequra_secret_key = fields.Char(
        string='Secret Key', 
        required_if_provider='sequra', 
        groups='base.group_system'
    )
    send_quotation = fields.Boolean(
        string='Send quotation', 
        default=True
    )

    def _get_default_payment_method_codes(self):
        """ Return the default payment method codes to enable when the provider is activated. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'sequra':
            return default_codes
        return ['sequra']

    def _get_sequra_api_url(self):
        """ Return the appropriate SeQura API URL based on provider state. """
        self.ensure_one()
        if self.state == 'test':
            return 'https://sandbox.sequrapi.com'
        return 'https://live.sequrapi.com'


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_rendering_values(self, processing_values):
        """ Override to provide SeQura-specific rendering values. """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'sequra':
            return res

        # Get the proper API URL
        api_url = self.provider_id._get_sequra_api_url() if hasattr(self.provider_id, '_get_sequra_api_url') else 'https://sandbox.sequrapi.com'
        
        # Create a proper HTML form for SeQura payment
        # This form will be automatically submitted by Odoo's redirect flow
        form_action = f"{api_url}/orders"
        return_url = processing_values.get('return_url', '/payment/sequra/return')
        
        redirect_form_html = f'''
        <form id="sequra_payment_form" action="{form_action}" method="post">
            <input type="hidden" name="merchant_id" value="{self.provider_id.sequra_merchant_id or 'test_merchant'}" />
            <input type="hidden" name="reference" value="{self.reference}" />
            <input type="hidden" name="amount" value="{int(self.amount * 100)}" />
            <input type="hidden" name="currency" value="{self.currency_id.name}" />
            <input type="hidden" name="return_url" value="{return_url}" />
            <input type="hidden" name="order_id" value="{self.id}" />
        </form>
        <script>
            document.getElementById('sequra_payment_form').submit();
        </script>
        '''
        
        rendering_values = {
            'redirect_form_html': redirect_form_html,
            'api_url': api_url,
            'merchant_id': self.provider_id.sequra_merchant_id,
            'reference': self.reference,
            'amount': int(self.amount * 100),  # Convert to cents
            'currency': self.currency_id.name,
        }
        
        return rendering_values

    # SeQura-specific fields
    order_sequra_ref = fields.Char('Sequra order reference')
    sequra_conf_resp_status_code = fields.Char('Confirmation Response Status Code')
    sequra_conf_resp_reason = fields.Text('Confirmation Response Reason')

    def send_mail(self, email_ctx):
        """ Send quotation email after successful payment """
        composer_values = {}
        template = self.env.ref('sale.email_template_edi_sale', False)
        if not template:
            return True
        email_ctx['default_template_id'] = template.id
        composer_id = self.env['mail.compose.message'].with_context(
            email_ctx).create(composer_values)
        composer_id.with_context(email_ctx).send_mail()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sequra_location = fields.Text('Sequra Location')
    order_sequra_ref = fields.Char('Sequra order reference', compute='_compute_sequra_ref')
    shipping_method = fields.Char('Sequra Shipping Method')

    @api.depends('sequra_location')
    def _compute_sequra_ref(self):
        for record in self:
            s_location = record.sequra_location and record.sequra_location.split('/') or None
            record.order_sequra_ref = s_location and s_location[len(s_location) - 1] or ''

