# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    sequra_txn_id = fields.Char('Sequra Transaction ID')

    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return Sequra-specific rendering values.

        Note: self.ensure_one() from inherited method
        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'sequra':
            return res

        payload = self._sequra_prepare_payment_request_payload()
        response = self.provider_id._sequra_make_request(payload=payload)
        
        # Extract the payment link from the response
        rendering_values = {
            'api_url': self.provider_id._get_sequra_api_url(),
            'sequra_txn_id': response.get('id'),
            'merchant_id': self.provider_id.sequra_merchant_id,
        }
        return rendering_values

    def _sequra_prepare_payment_request_payload(self):
        """ Create the payload for the payment request based on the transaction values.

        :return: The request payload
        :rtype: dict
        """
        base_url = self.provider_id.get_base_url()
        return {
            'order': {
                'merchant_reference': self.reference,
                'cart': {
                    'currency': self.currency_id.name,
                    'total_with_tax': self.amount,
                },
                'delivery_address': {
                    'given_names': self.partner_name,
                    'surnames': self.partner_name,
                    'address_line_1': self.partner_address,
                    'postal_code': self.partner_zip,
                    'city': self.partner_city,
                    'country_code': self.partner_country_id.code,
                },
            },
            'merchant': {
                'id': self.provider_id.sequra_merchant_id,
                'return_url': f'{base_url}/payment/sequra/return',
                'notification_url': f'{base_url}/payment/sequra/webhook',
            },
        }

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Override of payment to find the transaction based on Sequra data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if inconsistent data were received
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'sequra' or len(tx) == 1:
            return tx

        reference = notification_data.get('merchant_reference')
        txn_id = notification_data.get('id')
        if not reference or not txn_id:
            raise ValidationError(
                "Sequra: " + _(
                    "Received data with missing merchant reference (%(ref)s) or transaction id "
                    "(%(txn_id)s)",
                    ref=reference, txn_id=txn_id
                )
            )

        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'sequra')])
        if not tx:
            raise ValidationError(
                "Sequra: " + _("No transaction found matching reference %s.", reference)
            )

        return tx

    def _process_notification_data(self, notification_data):
        """ Override of payment to process the transaction based on Sequra data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'sequra':
            return

        self.sequra_txn_id = notification_data.get('id')

        status = notification_data.get('status')
        if status == 'approved':
            self._set_done()
        elif status == 'cancelled':
            self._set_canceled()
        elif status == 'error':
            self._set_error("Sequra: " + _("An error occurred during the processing of your payment."))
        else:
            _logger.warning(
                "received unrecognized payment state %s for transaction with reference %s",
                status, self.reference
            )
