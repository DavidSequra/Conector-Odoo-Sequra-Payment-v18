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
        return ['online_redirect']

    def _get_redirect_form_view(self, is_validation=False):
        """ Return the view to render the redirect form for SeQura. """
        if self.code != 'sequra':
            return super()._get_redirect_form_view(is_validation)
        return 'payment_sequra.sequra_redirect_form'

    def _sequra_make_request_from_transaction(self, transaction):
        """ Create SeQura order and return response object. """
        # Prepare the data like the original controller did
        post_data = {'merchant_id': self.sequra_merchant_id}
        
        # Get the order
        order = transaction.sale_order_ids and transaction.sale_order_ids[0]
        if not order:
            # Try to get order from invoice if no sale order
            if hasattr(transaction, 'invoice_ids') and transaction.invoice_ids:
                order = transaction.invoice_ids[0].invoice_line_ids.mapped('sale_line_ids.order_id')[:1]
        
        if not order:
            raise Exception("No order found for transaction")
        
        # Generate the data JSON like the original controller
        data = self._get_data_json_for_order(post_data, order)
        
        # Make the API call and return the response object
        endpoint = '/orders'
        return self._sequra_request(endpoint, data=data)

    def _fetch_sequra_form(self, location, payment_method=None):
        """ Fetch SeQura payment form. """
        headers = {'Accept': 'text/html'}
        endpoint = f'{location}/form_v2'
        if payment_method:
            endpoint += f'?product={payment_method}'
        return self._sequra_request(endpoint, method='GET', headers=headers)

    def _sequra_request(self, endpoint, method='POST', data='{}', headers=None):
        """ Make authenticated request to SeQura API. """
        if not headers:
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        
        # Build full URL
        url = endpoint if endpoint.startswith('http') else self._get_sequra_api_url() + endpoint
        
        # Prepare authentication
        auth = (self.sequra_api_key, self.sequra_secret_key)
        
        if method == 'POST':
            return requests.post(url, auth=auth, data=data, headers=headers, timeout=30)
        elif method == 'GET':
            return requests.get(url, auth=auth, headers=headers, timeout=30)
        elif method == 'PUT':
            return requests.put(url, auth=auth, data=data, headers=headers, timeout=30)

    def _get_data_json_for_order(self, post_data, order, state=''):
        """ Generate SeQura API payload for order - from original controller. """
        import json
        import os
        from odoo import release
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        notify_url = f'{base_url}/checkout/sequra-ipn'
        return_url = f'{base_url}/sequra/shop/confirmation?payment_method=sq-SQ_PRODUCT_CODE'
        
        partner_id = order.partner_id
        partner_invoice_id = order.partner_invoice_id
        partner_shipping_id = order.partner_shipping_id
        
        company_id = self.env.company
        currency = company_id.currency_id.name
        merchant_id = post_data.get('merchant_id')
        
        merchant_values = {
            "id": merchant_id,
            "notify_url": notify_url,
            "return_url": return_url,
            "notification_parameters": {"test": 'test'}
        }
        
        payload = {
            "order": {
                "state": state,
                "merchant": merchant_values,
                "merchant_reference": {"order_ref_1": order.name},
                "cart": {
                    "cart_ref": order.name,
                    "currency": currency or "EUR",
                    "gift": False,
                    "items": self._get_items_for_order(order, ''),
                    "order_total_with_tax": int(round(order.amount_total * 100, 2))
                },
                "delivery_address": self._get_address_for_partner(partner_shipping_id),
                "invoice_address": self._get_address_for_partner(partner_invoice_id),
                "customer": self._get_customer_data_for_partner(partner_id, order.id),
                "delivery_method": {"name": "no shipping"},
                "gui": {"layout": "desktop"},
                "platform": {
                    "name": "Odoo",
                    "version": release.version,
                    "uname": " ".join(os.uname()),
                    "db_name": "postgresql",
                    "db_version": "15.0"
                }
            }
        }
        
        return json.dumps(payload)

    def _get_customer_data_for_partner(self, partner_id, order_id):
        """ Get customer data for SeQura API. """
        import pytz
        from odoo import fields
        
        # Get previous orders
        previous_orders_records = self.env['sale.order'].sudo().search([
            ('partner_id', '=', partner_id.id),
            ('id', '!=', order_id)
        ], limit=10, order='create_date desc')
        
        previous_orders = [{
            'created_at': fields.Datetime.from_string(o.create_date).replace(
                tzinfo=pytz.timezone(o.partner_id.tz or 'Europe/Madrid'), 
                microsecond=0
            ).isoformat(),
            'amount': int(round(o.amount_total * 100, 2)),
            'currency': o.currency_id.name
        } for o in previous_orders_records]
        
        customer = self._get_address_for_partner(partner_id)
        
        # Get IP address - since we're in provider context, we can't access request
        # We'll use a default or try to get it from transaction context
        ip = "127.0.0.1"  # Default IP
        
        customer.update({
            'email': partner_id.email or "",
            'language_code': "es-ES",
            'ref': partner_id.id,
            'company': partner_id.company_id.name or "",
            'logged_in': 'unknown',
            'ip_number': ip,
            'user_agent': "",
            'vat_number': partner_id.company_id.vat or "",
            'previous_orders': previous_orders
        })
        
        return customer

    def _get_address_for_partner(self, partner_id):
        """ Get address data for SeQura API. """
        def _partner_split_name(partner_name):
            name_parts = partner_name.split()
            return [' '.join(name_parts[:-1]), ' '.join(name_parts[-1:])]
        
        return {
            "given_names": _partner_split_name(partner_id.name)[1],
            "surnames": _partner_split_name(partner_id.name)[0],
            "company": partner_id.company_id.name or "",
            "address_line_1": partner_id.street or "",
            "address_line_2": partner_id.street2 or "",
            "postal_code": partner_id.zip or "",
            "city": partner_id.city or "",
            "country_code": partner_id.country_id.code or "",
            "phone": partner_id.phone or "",
            "mobile_phone": partner_id.mobile or "",
            "nin": partner_id.vat[2:] if partner_id.vat else ""
        }

    def _get_items_for_order(self, order, shipping_name):
        """ Get order items for SeQura API. """
        items = []
        for line in order.order_line:
            price_subtotal = line.price_subtotal
            total_without_tax = int(round(price_subtotal * 100, 2))
            price_without_tax = int(round((price_subtotal / line.product_uom_qty) * 100, 2))
            
            # Calculate tax
            tax = sum(line.tax_id.mapped('amount')) * price_subtotal / 100
            total_with_tax = int(round((price_subtotal + tax) * 100, 2))
            price_with_tax = int(round(((price_subtotal + tax) / line.product_uom_qty) * 100, 2))
            
            if order.carrier_id.name != line.name:
                item = {
                    "reference": str(line.product_id.id),
                    "name": line.name,
                    "quantity": int(line.product_uom_qty),
                    "price_with_tax": price_with_tax,
                    "total_with_tax": total_with_tax,
                    "downloadable": False,
                    "product_id": line.product_id.id,
                }
                
                if line.product_id.type == 'service':
                    item['type'] = 'service'
                    item['ends_in'] = getattr(line.product_id, 'ends_in', 'P6M')
            else:
                item = {
                    "type": "handling",
                    "reference": "Costes de envío",
                    "name": shipping_name,
                    "tax_rate": 0,
                    "total_with_tax": total_with_tax,
                    "total_without_tax": total_without_tax,
                }
            
            items.append(item)
        
        return items

    def _get_sequra_api_url(self):
        """ Return the appropriate SeQura API URL based on provider state. """
        self.ensure_one()
        if self.state == 'test':
            return 'https://sandbox.sequrapi.com'
        return 'https://live.sequrapi.com'

    # Method to render payment form - restored from original
    def _get_redirect_form_view(self, is_validation=False):
        """ Return the view to render the payment form for SeQura. """
        if self.code != 'sequra':
            return super()._get_redirect_form_view(is_validation)
        return self.env.ref('payment_sequra.sequra_redirect_form', raise_if_not_found=False)

    def _sequra_make_request(self, endpoint, method='POST', data=None, headers=None):
        """ Make authenticated request to SeQura API. """
        self.ensure_one()
        if not headers:
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        
        url = endpoint if endpoint.startswith('http') else self._get_sequra_api_url() + endpoint
        auth = (self.sequra_api_key, self.sequra_secret_key)
        
        if method == 'POST':
            response = requests.post(url, auth=auth, data=data, headers=headers, timeout=30)
        elif method == 'GET':
            response = requests.get(url, auth=auth, headers=headers, timeout=30)
        elif method == 'PUT':
            response = requests.put(url, auth=auth, data=data, headers=headers, timeout=30)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        _logger.info("SeQura API %s %s - Status: %s", method, url, response.status_code)
        return response
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

