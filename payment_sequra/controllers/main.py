# -*- coding: utf-8 -*-

import logging
import pprint

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SequraController(http.Controller):
    _return_url = '/payment/sequra/return'
    _webhook_url = '/payment/sequra/webhook'

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
