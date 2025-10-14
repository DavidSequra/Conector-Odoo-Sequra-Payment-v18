# -*- coding: utf-8 -*-

import json
import logging
import pprint
import requests
import os
import pytz
from datetime import datetime

from odoo import http, release, fields, SUPERUSER_ID
from odoo.http import request
from odoo.tools.translate import _
from werkzeug.wrappers import Response

_logger = logging.getLogger(__name__)


class SequraController(http.Controller):
    
    @http.route(['/sequra/shop/confirmation'], type='http', auth="public", website=True)
    def sequra_payment_confirmation(self, **post):
        """ Return page after successful SeQura payment. """
        # Clean context and session, then redirect to confirmation page
        request.website.sale_reset()
        return request.redirect('/shop/confirmation')

    @http.route('/payment/sequra/redirect', type='http', auth='public', methods=['POST', 'GET'], website=True, csrf=False)
    def sequra_redirect(self, reference=None, **post):
        """ Handle redirect for SeQura payment - supports both GET and POST. """
        _logger.info("SeQura redirect called with reference: %s, method: %s", reference, request.httprequest.method)
        _logger.info("Post data: %s", pprint.pformat(post))
        
        # Get reference from POST data if not in URL
        if not reference:
            reference = post.get('reference')
        
        if not reference:
            return Response(
                '<html><body><h1>Error: Missing transaction reference</h1><a href="/shop">Back to shop</a></body></html>',
                mimetype='text/html'
            )
        
        try:
            # Find the transaction
            transaction = request.env['payment.transaction'].sudo().search([
                ('reference', '=', reference)
            ], limit=1)
            
            if not transaction:
                return Response(
                    '<html><body><h1>Error: Transaction not found</h1><a href="/shop">Back to shop</a></body></html>',
                    mimetype='text/html'
                )
            
            if transaction.provider_code != 'sequra':
                return Response(
                    '<html><body><h1>Error: Invalid provider</h1><a href="/shop">Back to shop</a></body></html>',
                    mimetype='text/html'
                )
            
            # Get the provider
            provider = transaction.provider_id
            
            # Start SeQura solicitation
            response = self._start_solicitation(provider, {
                'merchant_id': provider.sequra_merchant_id,
                'reference': reference
            }, transaction)
            
            if response.status_code == 204:
                # Success - get location and redirect
                location = response.headers.get('Location')
                if location:
                    # Save location to order
                    if transaction.sale_order_ids:
                        transaction.sale_order_ids[0].write({'sequra_location': location})
                    
                    # Redirect directly to SeQura form
                    sequra_form_url = f"{location}/form_v2"
                    return request.redirect(sequra_form_url)
                else:
                    return request.render("payment_sequra.sequra_error", {'error': 'No redirect URL from SeQura'})
            else:
                _logger.error("SeQura API error: %s - %s", response.status_code, response.text)
                return request.render("payment_sequra.sequra_error", {'error': f'SeQura API error: {response.status_code}'})
                
        except Exception as e:
            _logger.exception("SeQura redirect error: %s", str(e))
            return request.render("payment_sequra.sequra_error", {'error': f'Payment processing error: {str(e)}'})

    def _start_solicitation(self, provider, post, transaction):
        """ Start SeQura payment solicitation using transaction data. """
        # Get the order from transaction
        order = transaction.sale_order_ids and transaction.sale_order_ids[0]
        if not order:
            raise Exception("No order found for transaction")
        
        # Prepare post data
        post.update({'merchant_id': provider.sequra_merchant_id})
        data = self._get_data_json(provider, post, order)
        endpoint = '/orders'
        return self._sequra_request(provider, endpoint, data=data)

    @http.route('/payment/sequra', type='http', auth='public', methods=['POST'], website=True, csrf=False)
    def payment_sequra(self, **post):
        """ Main payment processing endpoint - restored from original. """
        _logger.info("SeQura: Processing payment with data: %s", pprint.pformat(post))
        
        try:
            # Get the provider
            provider_id = int(post.get('provider_id', -1))
            provider = request.env['payment.provider'].sudo().browse(provider_id)
            
            if not provider.exists() or provider.code != 'sequra':
                _logger.error("SeQura: Invalid provider ID: %s", provider_id)
                return self._render_error("Invalid payment provider")
            
            # Start SeQura solicitation
            response = self._start_solicitation(provider, post)
            
            if response.status_code == 204:
                # Success - get location and fetch form
                location = response.headers.get('Location')
                payment_method = post.get('payment_method')
                
                form_response = self._fetch_id_form(provider, location, payment_method)
                
                if form_response.status_code == 200:
                    # Save location to order and render payment form
                    order = request.website.sale_get_order()
                    order.write({'sequra_location': location})
                    
                    values = {
                        'partner': order.partner_id.id,
                        'order': order,
                        'errors': [],
                        'iframe': form_response.content.decode('utf-8')
                    }
                    
                    return request.render("payment_sequra.payment", values)
                else:
                    _logger.error("SeQura: Failed to fetch form. Status: %s", form_response.status_code)
                    return self._render_error("Unable to load payment form")
            else:
                _logger.error("SeQura: Solicitation failed. Status: %s", response.status_code)
                return self._render_error("Payment initialization failed")
                
        except Exception as e:
            _logger.exception("SeQura: Payment processing error: %s", str(e))
            return self._render_error("Payment processing error")

    def _start_solicitation(self, provider, post):
        """ Start SeQura payment solicitation - restored from original. """
        post.update({'merchant_id': provider.sequra_merchant_id})
        data = self._get_data_json(provider, post)
        endpoint = '/orders'
        return self._sequra_request(provider, endpoint, data=data)

    def _fetch_id_form(self, provider, location, payment_method=None):
        """ Fetch SeQura payment form - restored from original. """
        headers = {'Accept': 'text/html'}
        endpoint = f'{location}/form_v2'
        if payment_method:
            endpoint += f'?product={payment_method}'
        return self._sequra_request(provider, endpoint, method='GET', headers=headers)

    def _sequra_request(self, provider, endpoint, method='POST', data='{}', headers=None):
        """ Make authenticated request to SeQura API - restored from original. """
        if not headers:
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        
        # Build full URL
        url = endpoint if endpoint.startswith('http') else provider._get_sequra_api_url() + endpoint
        
        # Prepare authentication
        auth = (provider.sequra_api_key, provider.sequra_secret_key)
        
        if method == 'POST':
            return requests.post(url, auth=auth, data=data, headers=headers)
        elif method == 'GET':
            return requests.get(url, auth=auth, headers=headers)
        elif method == 'PUT':
            return requests.put(url, auth=auth, data=data, headers=headers)

    def _get_data_json(self, provider, post, order=None, state=''):
        """ Generate SeQura API payload - restored from original. """
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        notify_url = f'{base_url}/checkout/sequra-ipn'
        return_url = f'{base_url}/sequra/shop/confirmation?payment_method=sq-SQ_PRODUCT_CODE'
        
        if not order:
            order = request.website.sale_get_order()
        
        partner_id = order.partner_id
        partner_invoice_id = order.partner_invoice_id
        partner_shipping_id = order.partner_shipping_id
        
        company_id = request.env.company
        currency = company_id.currency_id.name
        merchant_id = post.get('merchant_id')
        
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
                    "items": self._get_items(order, ''),
                    "order_total_with_tax": int(round(order.amount_total * 100, 2))
                },
                "delivery_address": self._get_address(partner_shipping_id),
                "invoice_address": self._get_address(partner_invoice_id),
                "customer": self._get_customer_data(partner_id, order.id),
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

    def _get_customer_data(self, partner_id, order_id):
        """ Get customer data for SeQura API - restored from original. """
        # Get previous orders
        previous_orders_records = request.env['sale.order'].sudo().search([
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
        
        customer = self._get_address(partner_id)
        
        # Get IP address
        ip = request.httprequest.environ.get("HTTP_X_FORWARDED_FOR") or \
            request.httprequest.environ.get("REMOTE_ADDR", "127.0.0.1")
        
        customer.update({
            'email': partner_id.email or "",
            'language_code': "es-ES",
            'ref': partner_id.id,
            'company': partner_id.company_id.name or "",
            'logged_in': 'unknown',
            'ip_number': ip,
            'user_agent': request.httprequest.environ.get("HTTP_USER_AGENT", ""),
            'vat_number': partner_id.company_id.vat or "",
            'previous_orders': previous_orders
        })
        
        return customer

    def _get_address(self, partner_id):
        """ Get address data for SeQura API - restored from original. """
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

    def _get_items(self, order, shipping_name):
        """ Get order items for SeQura API - restored from original. """
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

    def _render_error(self, error_msg):
        """ Render error page. """
        return request.render("payment_sequra.sequra_error", {'error': error_msg})

    @http.route('/checkout/sequra-ipn', type='http', auth='none', methods=['POST'])
    def checkout_sequra_ipn(self, **post):
        """ Handle SeQura IPN notifications - restored from original. """
        _logger.info("SeQura IPN received: %s", pprint.pformat(post))
        
        order_ref = post.get('order_ref')  # SeQura reference
        order_ref_1 = post.get('order_ref_1')  # Odoo reference
        
        if not order_ref or not order_ref_1:
            _logger.error("SeQura IPN: Missing order references")
            return Response('Bad Request', status=400)
        
        try:
            # Find order
            order = request.env['sale.order'].sudo().search([
                ('sequra_location', 'like', f'%{order_ref}')
            ], limit=1)
            
            if not order or order.name != order_ref_1:
                _logger.error("SeQura IPN: Order not found or reference mismatch")
                return Response('Not Found', status=404)
            
            # Find transaction
            transaction = request.env['payment.transaction'].sudo().search([
                ('reference', '=', order_ref_1)
            ], limit=1)
            
            if not transaction:
                _logger.error("SeQura IPN: Transaction not found")
                return Response('Not Found', status=404)
            
            # Confirm order with SeQura
            post_data = {'merchant_id': transaction.provider_id.sequra_merchant_id}
            data = self._get_data_json(transaction.provider_id, post_data, order, 'confirmed')
            endpoint = order.sequra_location
            response = self._sequra_request(transaction.provider_id, endpoint, method='PUT', data=data)
            
            # Update transaction
            values = {
                'sequra_conf_resp_status_code': response.status_code,
                'sequra_conf_resp_reason': response.reason
            }
            
            if 200 <= response.status_code <= 299:
                values.update({
                    'state': 'done',
                    'order_sequra_ref': order_ref,
                })
                transaction.write(values)
                
                # Send quotation if enabled
                if transaction.provider_id.send_quotation:
                    transaction._send_mail()
                
                return Response('OK', status=200)
            else:
                values['state'] = 'error'
                transaction.write(values)
                return Response(response.reason, status=response.status_code)
                
        except Exception as e:
            _logger.exception("SeQura IPN processing error: %s", str(e))
            return Response('Internal Server Error', status=500)