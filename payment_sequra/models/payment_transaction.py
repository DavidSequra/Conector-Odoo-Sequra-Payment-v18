# -*- coding: utf-8 -*-

import logging
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    sequra_txn_id = fields.Char('Sequra Transaction ID')
    order_sequra_ref = fields.Char('Sequra order reference')
    sequra_conf_resp_status_code = fields.Char('Confirmation Response Status Code')
    sequra_conf_resp_reason = fields.Text('Confirmation Response Reason')

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

        # For SeQura, we call the API immediately and return redirect URL
        try:
            # Make the call to SeQura API
            response = self.provider_id._sequra_make_request_from_transaction(self)
            
            if response.status_code == 204:
                # Success - get location and create redirect URL
                location = response.headers.get('Location')
                if location:
                    # Save location to order for future reference
                    if self.sale_order_ids:
                        self.sale_order_ids[0].write({'sequra_location': location})
                    
                    # Return the SeQura form URL for auto-redirect
                    sequra_form_url = f"{location}/form_v2"
                    rendering_values = {
                        'sequra_redirect_url': sequra_form_url,  # Will be used by JavaScript for auto-redirect
                        'auto_redirect_script': f"""
                        <script type="text/javascript">
                            console.log('SeQura: Auto-redirecting to {sequra_form_url}');
                            setTimeout(function() {{
                                window.location.href = '{sequra_form_url}';
                            }}, 1000);
                        </script>
                        """,
                    }
                    res.update(rendering_values)
                    return res
                else:
                    raise ValidationError("SeQura did not return a redirect URL")
            else:
                raise ValidationError(f"SeQura API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            # Log the error and fallback to error handling
            _logger.exception("SeQura API call failed: %s", str(e))
            # Instead of failing, let's redirect to our error endpoint
            base_url = self.provider_id.get_base_url()
            rendering_values = {
                'api_url': f"{base_url}/payment/sequra/redirect",
                'reference': self.reference,
                'amount': self.amount,
                'currency': self.currency_id.name,
            }
            res.update(rendering_values)
            return res

    def _sequra_prepare_payment_request_payload(self):
        """ Create the payload for the payment request based on the transaction values.

        :return: The request payload
        :rtype: dict
        """
        base_url = self.provider_id.get_base_url()
        
        # Get sale order data
        sale_order = self.sale_order_ids and self.sale_order_ids[0] or None
        if not sale_order and hasattr(self, 'invoice_ids') and self.invoice_ids:
            sale_order = self.invoice_ids[0].invoice_line_ids.mapped('sale_line_ids.order_id')[:1]
        
        # Get cart items matching SeQura's real example structure
        cart_items = []
        if sale_order:
            for line in sale_order.order_line:
                if line.display_type in ('line_section', 'line_note'):
                    continue
                    
                item = {
                    "id_product_attribute": "0",
                    "cart_quantity": str(int(line.product_uom_qty)),
                    "id_shop": "1",
                    "name": line.product_id.name,
                    "is_virtual": "0",
                    "available_now": "",
                    "available_later": "",
                    "id_category_default": "1",
                    "manufacturer_name": "",
                    "on_sale": "0",
                    "ecotax": "0.000000",
                    "additional_shipping_cost": 0,
                    "available_for_order": "1",
                    "show_price": "1",
                    "active": "1",
                    "unity": "",
                    "unit_price_ratio": "0.000000",
                    "quantity_available": "0",
                    "width": "0.000000",
                    "height": "0.000000",
                    "depth": "0.000000",
                    "out_of_stock": "1",
                    "weight": 0,
                    "available_date": "0000-00-00",
                    "date_add": line.product_id.create_date.strftime('%Y-%m-%d %H:%M:%S') if line.product_id.create_date else "",
                    "date_upd": line.product_id.write_date.strftime('%Y-%m-%d %H:%M:%S') if line.product_id.write_date else "",
                    "quantity": int(line.product_uom_qty),
                    "link_rewrite": "",
                    "category": line.product_id.categ_id.name if line.product_id.categ_id else "",
                    "unique_id": f"{str(line.product_id.id).zfill(10)}000000000000",
                    "id_address_delivery": "0",
                    "advanced_stock_management": "0",
                    "supplier_reference": line.product_id.default_code or "",
                    "price_attribute": 0,
                    "reference": line.product_id.default_code or str(line.product_id.id),
                    "ean13": line.product_id.barcode or "",
                    "minimal_quantity": "1",
                    "reduction_type": "percentage",
                    "is_gift": False,
                    "reduction": 0,
                    "price_without_reduction": float(line.price_unit),
                    "price_with_reduction": float(line.price_unit),
                    "reduction_applies": False,
                    "quantity_discount_applies": False,
                    "allow_oosp": 1,
                    "features": [],
                    "tax_name": line.tax_id[0].name if line.tax_id else "",
                    "type": "product",
                    "total_without_tax": int(line.price_subtotal * 100),
                    "total_with_tax": int(line.price_total * 100),
                    "price_without_tax": int(line.price_unit * 100),
                    "price_with_tax": int(line.price_unit * 100),
                    "tax_rate": line.tax_id[0].amount if line.tax_id else 0,
                    "description": line.product_id.description or line.name,
                    "product_id": str(line.product_id.id),
                    "downloadable": False
                }
                cart_items.append(item)
        
        # Cart data matching real example
        cart_data = {
            "id_cart": sale_order.id if sale_order else self.id,
            "id_shop_group": 1,
            "id_shop": 1,
            "id_address_delivery": self.partner_id.id,
            "id_address_invoice": self.partner_id.id,
            "id_carrier": sale_order.carrier_id.id if sale_order and sale_order.carrier_id else 1,
            "id_currency": self.currency_id.id,
            "id_customer": self.partner_id.id,
            "id_guest": 0,
            "id_lang": 1,
            "recyclable": 0,
            "gift": False,
            "gift_message": "",
            "mobile_theme": 0,
            "delivery_option": "",
            "allow_seperated_package": 0,
            "created_at": sale_order.create_date.strftime('%Y-%m-%d %H:%M:%S') if sale_order and sale_order.create_date else "",
            "updated_at": sale_order.write_date.strftime('%Y-%m-%d %H:%M:%S') if sale_order and sale_order.write_date else "",
            "cart_ref": sale_order.id if sale_order else self.id,
            "currency": self.currency_id.name,
            "delivery_method": {
                "name": sale_order.carrier_id.name if sale_order and sale_order.carrier_id else "Standard delivery",
                "days": "1-3"
            },
            "order_total_with_tax": int(self.amount * 100),
            "order_total_without_tax": int(self.amount * 100),
            "items": cart_items
        }
        
        # Customer data matching real example
        customer_data = {
            "id_customer": self.partner_id.id,
            "id_gender": 0,
            "newsletter": 1,
            "newsletter_date_add": self.partner_id.create_date.strftime('%Y-%m-%d %H:%M:%S') if self.partner_id.create_date else "",
            "ip_registration_newsletter": "",
            "optin": 0,
            "website": "",
            "company": self.partner_id.commercial_company_name or "",
            "siret": "",
            "ape": "",
            "outstanding_allow_amount": 0,
            "show_public_prices": 0,
            "id_risk": 0,
            "max_payment_days": 0,
            "active": 1,
            "deleted": 0,
            "note": "",
            "is_guest": 0,
            "id_shop": 1,
            "id_shop_group": 1,
            "id_default_group": 3,
            "id_lang": 1,
            "reset_password_token": "",
            "reset_password_validity": "0000-00-00 00:00:00",
            "given_names": self.partner_id.name.split(' ')[0] if self.partner_id.name else '',
            "surnames": ' '.join(self.partner_id.name.split(' ')[1:]) if self.partner_id.name and len(self.partner_id.name.split(' ')) > 1 else '',
            "email": self.partner_id.email or '',
            "created_at": self.partner_id.create_date.strftime('%Y-%m-%d %H:%M:%S') if self.partner_id.create_date else '',
            "updated_at": self.partner_id.write_date.strftime('%Y-%m-%d %H:%M:%S') if self.partner_id.write_date else '',
            "ref": str(self.partner_id.id),
            "language_code": self.partner_id.lang or 'es',
            "ip_number": "",
            "user_agent": "",
            "request_uri": "",
            "referrer": "",
            "logged_in": not self.partner_id.is_public if hasattr(self.partner_id, 'is_public') else True,
            "previous_orders": []
        }
        
        # Address data matching real example
        delivery_partner = sale_order.partner_shipping_id if sale_order else self.partner_id
        delivery_address = {
            "id_address": delivery_partner.id,
            "id_customer": self.partner_id.id,
            "id_manufacturer": 0,
            "id_supplier": 0,
            "id_warehouse": 0,
            "id_country": delivery_partner.country_id.id if delivery_partner.country_id else 0,
            "id_state": delivery_partner.state_id.id if delivery_partner.state_id else 0,
            "alias": "Default Address",
            "dni": "",
            "deleted": 0,
            "date_add": delivery_partner.create_date.strftime('%Y-%m-%d %H:%M:%S') if delivery_partner.create_date else "",
            "date_upd": delivery_partner.write_date.strftime('%Y-%m-%d %H:%M:%S') if delivery_partner.write_date else "",
            "given_names": delivery_partner.name.split(' ')[0] if delivery_partner.name else '',
            "surnames": ' '.join(delivery_partner.name.split(' ')[1:]) if delivery_partner.name and len(delivery_partner.name.split(' ')) > 1 else '',
            "company": delivery_partner.commercial_company_name or delivery_partner.parent_id.name or '',
            "address_line_1": delivery_partner.street or '',
            "address_line_2": delivery_partner.street2 or '',
            "postal_code": delivery_partner.zip or '',
            "city": delivery_partner.city or '',
            "phone": delivery_partner.phone or delivery_partner.mobile or '',
            "mobile_phone": delivery_partner.mobile or '',
            "extra": "",
            "vat_number": delivery_partner.vat or '',
            "country_code": delivery_partner.country_id.code if delivery_partner.country_id else ''
        }
        
        # Invoice address (copy of delivery for simplicity)
        invoice_partner = sale_order.partner_invoice_id if sale_order else self.partner_id
        invoice_address = delivery_address.copy()
        invoice_address.update({
            "id_address": invoice_partner.id,
            "given_names": invoice_partner.name.split(' ')[0] if invoice_partner.name else '',
            "surnames": ' '.join(invoice_partner.name.split(' ')[1:]) if invoice_partner.name and len(invoice_partner.name.split(' ')) > 1 else '',
            "company": invoice_partner.commercial_company_name or invoice_partner.parent_id.name or '',
            "address_line_1": invoice_partner.street or '',
            "address_line_2": invoice_partner.street2 or '',
            "postal_code": invoice_partner.zip or '',
            "city": invoice_partner.city or '',
            "phone": invoice_partner.phone or invoice_partner.mobile or '',
            "mobile_phone": invoice_partner.mobile or '',
            "vat_number": invoice_partner.vat or '',
            "country_code": invoice_partner.country_id.code if invoice_partner.country_id else ''
        })
        
        # Platform data matching real example
        platform_data = {
            "name": "Odoo",
            "version": "18.0",
            "plugin_version": "1.0.0",
            "php_version": "Python 3.12",
            "php_os": "Linux",
            "uname": "Linux",
            "db_name": "postgresql",
            "db_version": "15"
        }
        
        # Complete payload matching real example structure
        payload = {
            "order": {
                "state": "",
                "merchant": {
                    "id": self.provider_id.sequra_merchant_id,
                    "edit_url": f"{base_url}/shop/cart",
                    "abort_url": f"{base_url}/shop/cart?sequra_error=1",
                    "return_url": f"{base_url}/payment/sequra/return?reference={self.reference}",
                    "notify_url": f"{base_url}/payment/sequra/webhook",
                    "notification_parameters": {
                        "cart_id": str(sale_order.id if sale_order else self.id),
                        "signed": "",
                        "id_shop": "1",
                        "id_lang": "1",
                        "method": "sequra"
                    }
                },
                "merchant_reference": {
                    "order_ref_1": self.reference
                },
                "cart": cart_data,
                "delivery_address": delivery_address,
                "invoice_address": invoice_address,
                "customer": customer_data,
                "platform": platform_data,
                "gui": {
                    "layout": "desktop"
                }
            }
        }
        
        return payload

    def _send_mail(self):
        """ Send quotation email - restored from original. """
        if not self.sale_order_ids:
            return True
        
        order = self.sale_order_ids[0]
        template = self.env.ref('sale.email_template_edi_sale', raise_if_not_found=False)
        if not template:
            return True
        
        email_ctx = {
            'default_model': 'sale.order',
            'default_res_id': order.id,
            'default_use_template': bool(template),
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'default_email_layout_xmlid': "mail.mail_notification_paynow",
        }
        
        composer = self.env['mail.compose.message'].with_context(email_ctx).create({})
        composer.send_mail()
        return True

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
