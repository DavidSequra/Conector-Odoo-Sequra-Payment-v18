/** @odoo-module */

import { PaymentInterface } from "@payment/js/payment_interface";

export class SequraPaymentInterface extends PaymentInterface {
    
    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Redirect the customer to SeQura.
     *
     * @override method from PaymentInterface
     * @private
     * @param {string} provider - The provider of the payment option's provider.
     * @param {number} paymentOptionId - The id of the payment option handling the transaction.
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    async _processRedirectPayment(provider, paymentOptionId, processingValues) {
        if (provider !== 'sequra') {
            return super._processRedirectPayment(...arguments);
        }
        
        // For SeQura, we typically redirect to their payment page
        // The processingValues should contain the redirect URL from the backend
        if (processingValues.api_url && processingValues.reference) {
            // Create a simple redirect form
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = `${processingValues.api_url}/orders`;
            
            // Add necessary fields for SeQura
            const fields = {
                'merchant_id': processingValues.merchant_id,
                'reference': processingValues.reference,
                'amount': processingValues.amount,
                'currency': processingValues.currency,
            };
            
            for (const [key, value] of Object.entries(fields)) {
                if (value) {
                    const input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = key;
                    input.value = value;
                    form.appendChild(input);
                }
            }
            
            document.body.appendChild(form);
            form.submit();
        } else {
            console.error('SeQura: Missing processing values for payment redirect');
        }
    }
}

// Register the payment interface
PaymentInterface.register('sequra', SequraPaymentInterface);

