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

    def _get_supported_operations(self):
        """ Override to return supported operations for SeQura provider. """
        self.ensure_one()
        if self.code != 'sequra':
            return super()._get_supported_operations()
        return ['online_redirect']  # SeQura uses API-driven redirect flow

    def _get_redirect_form_view(self, is_validation=False):
        """ Return the view to render the API-driven payment form for SeQura. """
        if self.code != 'sequra':
            return super()._get_redirect_form_view(is_validation)
        return self.env.ref('payment_sequra.sequra_redirect_form', raise_if_not_found=False)

    def _get_sequra_api_url(self):
        """ Return the appropriate SeQura API URL based on provider state. """
        self.ensure_one()
        if self.state == 'test':
            return 'https://sandbox.sequrapi.com'
        return 'https://live.sequrapi.com'

    def _sequra_make_request(self, payload):
        """Send a payment request to the SeQura API."""
        self.ensure_one()
        url = f"{self._get_sequra_api_url()}/orders"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # SeQura uses HTTP Basic Auth with accountKey:accountSecret
        auth = (self.sequra_api_key, self.sequra_secret_key)
        
        # Log authentication details (without exposing secrets)
        _logger.info("SeQura API Request Details:")
        _logger.info("- URL: %s", url)
        _logger.info("- API Key configured: %s", bool(self.sequra_api_key))
        _logger.info("- Secret Key configured: %s", bool(self.sequra_secret_key))
        _logger.info("- API Key length: %s", len(self.sequra_api_key) if self.sequra_api_key else 0)
        _logger.info("- Secret Key length: %s", len(self.sequra_secret_key) if self.sequra_secret_key else 0)
        _logger.info("- Provider state: %s", self.state)
        _logger.info("- Merchant ID: %s", self.sequra_merchant_id)
        _logger.info("- Merchant ID in payload: %s", payload.get('merchant', {}).get('id'))

        _logger.info("SeQura request to %s with payload %s", url, payload)
        response = requests.post(url, json=payload, headers=headers, auth=auth, timeout=30)
        
        _logger.info("SeQura response status: %s", response.status_code)
        _logger.info("SeQura response headers: %s", dict(response.headers))

        if response.status_code not in (200, 201, 204):
            _logger.error("SeQura API error: %s - %s", response.status_code, response.text)
            raise Exception(f"SeQura API error: {response.text}")

        # SeQura returns 204 No Content with Location header
        if response.status_code == 204:
            location = response.headers.get('Location')
            if location:
                return {'location': location, 'order_url': location}
            else:
                raise Exception("SeQura API error: No Location header in response")

        return response.json()


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def create(self, vals):
        """ Override create to set proper operation for SeQura transactions. """
        # If this is a SeQura transaction, ensure it uses redirect flow
        if vals.get('provider_code') == 'sequra':
            vals['operation'] = 'online_redirect'
        return super().create(vals)

    def _get_specific_rendering_values(self, processing_values):
        """ Override to provide SeQura-specific rendering values. """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'sequra':
            return res

        # For SeQura redirect flow - provide data for the redirect form template
        api_url = self.provider_id._get_sequra_api_url() if hasattr(self.provider_id, '_get_sequra_api_url') else 'https://sandbox.sequrapi.com'
        
        rendering_values = {
            'api_url': f"{api_url}/orders",
            'merchant_id': self.provider_id.sequra_merchant_id or 'test_merchant',
            'reference': self.reference,
            'amount': int(self.amount * 100),  # Convert to cents
            'currency': self.currency_id.name,
            'return_url': processing_values.get('return_url', '/payment/sequra/return'),
            'order_id': self.id,
        }
        
        # Update with parent rendering values
        res.update(rendering_values)
        return res

    def _get_processing_values(self):
        """ Override to ensure SeQura uses API-driven redirect processing. """
        res = super()._get_processing_values()
        if self.provider_code == 'sequra':
            # Ensure the transaction uses redirect processing
            _logger.info("SeQura: Setting operation to online_redirect for API-driven transaction %s", self.reference)
            self.operation = 'online_redirect'
        return res

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

