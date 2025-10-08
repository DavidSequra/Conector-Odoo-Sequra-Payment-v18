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

    sequra_merchant_id = fields.Char('Merchant ID', required_if_provider='sequra', groups='base.group_system')
    sequra_api_key = fields.Char('API Key', required_if_provider='sequra', groups='base.group_system')
    sequra_secret_key = fields.Char('Secret Key', required_if_provider='sequra', groups='base.group_system')
    send_quotation = fields.Boolean('Send quotation', default=True)

    def _get_default_payment_method_codes(self):
        """ Return the default payment method codes to enable when the provider is activated. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'sequra':
            return default_codes
        return ['sequra']

    def _get_compatible_payment_methods(self):
        """ Return the compatible payment methods. """
        compatible_payment_methods = super()._get_compatible_payment_methods()
        if self.code == 'sequra':
            sequra_method = self.env.ref('payment_sequra.payment_method_sequra', raise_if_not_found=False)
            if sequra_method and sequra_method not in compatible_payment_methods:
                compatible_payment_methods |= sequra_method
        return compatible_payment_methods

    def _is_available_for_order(self, order, **kwargs):
        """ Check if the provider is available for the given order. """
        if self.code != 'sequra':
            return super()._is_available_for_order(order, **kwargs)
        
        # Basic availability checks
        res = super()._is_available_for_order(order, **kwargs)
        if not res:
            return False
            
        # SeQura specific checks
        if order.currency_id.name != 'EUR':
            return False
            
        if (order.partner_id.country_id and 
            order.partner_id.country_id.code not in ['ES', 'IT', 'FR', 'PT']):
            return False
        
        return True

    def _compute_available_payment_method_ids(self):
        """ Compute which payment methods are available for this provider. """
        super()._compute_available_payment_method_ids()
        for provider in self.filtered(lambda p: p.code == 'sequra'):
            # Ensure SeQura method is always available for SeQura provider
            sequra_method = self.env.ref('payment_sequra.payment_method_sequra', raise_if_not_found=False)
            if sequra_method:
                if sequra_method not in provider.available_payment_method_ids:
                    provider.available_payment_method_ids = [(4, sequra_method.id)]
                # Also ensure the method is active
                if not sequra_method.active:
                    sequra_method.active = True

    def _get_supported_currencies(self):
        """ Return supported currencies for SeQura. """
        supported_currencies = super()._get_supported_currencies()
        if self.code != 'sequra':
            return supported_currencies
        return supported_currencies.filtered(lambda c: c.name in ['EUR'])

    def _get_supported_countries(self):
        """ Return supported countries for SeQura. """
        supported_countries = super()._get_supported_countries()
        if self.code != 'sequra':
            return supported_countries
        return self.env['res.country'].search([('code', 'in', ['ES', 'IT', 'FR', 'PT'])])

    def _should_build_inline_form(self, is_validation=False):
        """ Return whether the inline form should be instantiated if possible.
        
        For SeQura, we typically want to redirect to their platform.
        """
        if self.code != 'sequra':
            return super()._should_build_inline_form(is_validation)
        return False

    def _is_tokenization_required(self, **kwargs):
        """ Return whether tokenizing the payment method is required given its provider.
        
        SeQura doesn't require tokenization.
        """
        if self.code != 'sequra':
            return super()._is_tokenization_required(**kwargs)
        return False

    def _get_validation_amount(self):
        """ Return the amount to be paid to validate the payment method.
        
        SeQura doesn't require validation payments.
        """
        if self.code != 'sequra':
            return super()._get_validation_amount()
        return 0

    def _get_validation_currency(self):
        """ Return the currency to be used for the validation payment.
        
        SeQura uses EUR.
        """
        if self.code != 'sequra':
            return super()._get_validation_currency()
        return self.env['res.currency'].search([('name', '=', 'EUR')], limit=1)

    def _is_payment_method_available(self, payment_method, **kwargs):
        """ Return whether the payment method is available for the current payment.
        
        :param recordset payment_method: The payment method to check
        :return: Whether the payment method is available
        :rtype: bool
        """
        res = super()._is_payment_method_available(payment_method, **kwargs)
        if self.code != 'sequra' or payment_method.code != 'sequra':
            return res
        
        # SeQura is available for EUR currency and supported countries
        currency = kwargs.get('currency')
        partner = kwargs.get('partner')
        
        if currency and currency.name != 'EUR':
            return False
            
        if partner and partner.country_id and partner.country_id.code not in ['ES', 'IT', 'FR', 'PT']:
            return False
            
        return True

    def _get_sequra_api_url(self):
        """ Sequra URLS """
        self.ensure_one()
        if self.state == 'test':
            return 'https://sandbox.sequrapi.com'
        return 'https://live.sequrapi.com'

    def _sequra_make_request(self, endpoint=None, method='POST', payload=None, headers=None):
        """ Make a request to Sequra API.
        
        :param str endpoint: The endpoint to be reached by the request
        :param str method: The HTTP method of the request
        :param dict payload: The data to send in the request body
        :param dict headers: The headers to add to the request
        :return: The JSON-formatted content of the response
        :rtype: dict
        :raise ValidationError: if an HTTP error occurs
        """
        self.ensure_one()

        base_url = self._get_sequra_api_url()
        endpoint = endpoint or '/orders'
        url = endpoint if endpoint.startswith('http') else base_url + endpoint

        headers = headers or {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.request(
                method,
                url,
                auth=(self.sequra_secret_key, self.sequra_api_key),  # Using secret_key as username and api_key as password
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as error:
            _logger.exception("Error when communicating with Sequra: %s", error)
            raise ValidationError(
                _("Could not establish the connection to the API.") if isinstance(
                    error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
                ) else _("The communication with the API failed.")
            )


class TxSequra(models.Model):
    _inherit = 'payment.transaction'

    order_sequra_ref = fields.Char('Sequra order reference')
    sequra_conf_resp_status_code = fields.Char('Confirmation Response Status Code')
    sequra_conf_resp_reason = fields.Text('Confirmation Response Reason')

    def send_mail(self, email_ctx):
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

