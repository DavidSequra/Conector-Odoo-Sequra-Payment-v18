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

    @http.route('/payment/sequra', type='http', auth='public', methods=['POST'], website=True)
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
            transaction = request.env['payment.transaction'].sudo().search([
                ('reference', '=', tx_reference),
                ('provider_code', '=', 'sequra')
            ], limit=1)
            
            if not transaction:
                return self._json_response({'success': False, 'error': 'Transaction not found'})
            
            # Call SeQura API to get payment form/URL
            sequra_response = self._call_sequra_api(transaction, data)
            
            if sequra_response.get('success'):
                return self._json_response({
                    'success': True,
                    'redirect_url': sequra_response.get('redirect_url'),
                    'payment_form_html': sequra_response.get('payment_form_html')
                })
            else:
                return self._json_response({
                    'success': False, 
                    'error': sequra_response.get('error', 'SeQura API error')
                })
                
        except Exception as e:
            _logger.error("SeQura: Error processing payment: %s", str(e))
            return self._json_response({'success': False, 'error': 'Internal server error'})

    def _call_sequra_api(self, transaction, form_data):
        """ Make API call to SeQura to initiate payment. """
        try:
            api_url = transaction.provider_id._get_sequra_api_url()
            
            # Prepare payload for SeQura API
            payload = {
                'merchant_id': transaction.provider_id.sequra_merchant_id,
                'amount': int(transaction.amount * 100),  # Convert to cents
                'currency': transaction.currency_id.name,
                'reference': transaction.reference,
                'return_url': f"{request.httprequest.url_root.rstrip('/')}/payment/sequra/return",
                'webhook_url': f"{request.httprequest.url_root.rstrip('/')}/payment/sequra/webhook",
                'order_id': transaction.id
            }
            
            # Make API call to SeQura
            response = requests.post(
                f"{api_url}/orders",
                json=payload,
                headers={
                    'Authorization': f"Bearer {transaction.provider_id.sequra_api_key}",
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                response_data = response.json()
                return {
                    'success': True,
                    'redirect_url': response_data.get('redirect_url'),
                    'payment_form_html': response_data.get('payment_form_html')
                }
            else:
                _logger.error("SeQura API error: %s - %s", response.status_code, response.text)
                return {'success': False, 'error': f'SeQura API error: {response.status_code}'}
                
        except requests.RequestException as e:
            _logger.error("SeQura API request failed: %s", str(e))
            return {'success': False, 'error': 'Failed to connect to SeQura'}
        except Exception as e:
            _logger.error("SeQura API call error: %s", str(e))
            return {'success': False, 'error': 'SeQura API error'}

    def _json_response(self, data):
        """ Return JSON response. """
        return request.make_response(
            json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )

    @http.route(_return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False, save_session=False)
    def sequra_return(self, **data):
        """ Handle the return from SeQura after payment processing. """
        _logger.info("SeQura: handling return from payment with data: %s", pprint.pformat(data))
        
        if data:
            request.env['payment.transaction'].sudo()._handle_notification_data('sequra', data)
        
        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def sequra_webhook(self, **data):
        """ Handle webhook notifications from SeQura. """
        _logger.info("SeQura: handling webhook notification with data: %s", pprint.pformat(data))
        
        if data:
            request.env['payment.transaction'].sudo()._handle_notification_data('sequra', data)
        
        return ''  # Return empty response for webhook
