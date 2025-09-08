odoo.define('payment_sequra.payment_form', function (require) {
    'use strict';

    const checkoutForm = require('payment.checkout_form');
    const manageForm = require('payment.manage_form');

    const sequraForm = {
        init: function () {
            this._super.apply(this, arguments);
        },

        _processPayment: function (provider, paymentOptionId, flow) {
            if (provider !== 'sequra') {
                return this._super(...arguments);
            }
            // Handle Sequra payment flow
            return this._rpc({
                route: '/payment/sequra/create_payment',
                params: {
                    'payment_option_id': paymentOptionId,
                    'access_token': this.options.accessToken,
                    'reference': this.options.txContext.reference,
                    'partner_id': this.options.txContext.partner_id,
                    'amount': this.options.txContext.amount,
                    'currency_id': this.options.txContext.currency_id,
                }
            }).then(response => {
                if (response.success) {
                    window.location = response.url;
                }
            });
        },
    };

    checkoutForm.include(sequraForm);
    manageForm.include(sequraForm);

    return sequraForm;
});

