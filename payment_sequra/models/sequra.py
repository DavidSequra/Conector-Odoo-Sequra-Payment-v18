# -*- coding: utf-8 -*-

import logging
import requests

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AcquirerSequra(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('sequra', 'SeQura')],
        ondelete={'sequra': 'set default'}
    )

    sequra_merchant_id = fields.Char('Merchant ID', required_if_provider='sequra', groups='base.group_system')
    sequra_api_key = fields.Char('API Key', required_if_provider='sequra', groups='base.group_system')
    sequra_secret_key = fields.Char('Secret Key', required_if_provider='sequra', groups='base.group_system')

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
                auth=(self.sequra_merchant_id, self.sequra_api_key),
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
            return requests.put(
                url,
                auth=(self.sequra_user, self.sequra_pass),
                data=data,
                headers=headers
            )

    sequra_user = fields.Char('Sequra User')
    sequra_pass = fields.Char('Sequra Password')
    sequra_merchant = fields.Char('Sequra Merchant')
    send_quotation = fields.Boolean('Send quotation', default=True)


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
    # order_id_sha1 = fields.Char('Order Id Sha1', compute='_compute_order_id_sha1', store=True)

    @api.depends('sequra_location')
    def _compute_sequra_ref(self):
        for record in self:
            s_location = record.sequra_location and record.sequra_location.split('/') or None
            record.order_sequra_ref = s_location and s_location[len(s_location) - 1] or ''

