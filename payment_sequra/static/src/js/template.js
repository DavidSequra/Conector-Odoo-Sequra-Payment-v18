/** @odoo-module **/

// SeQura Payment Interface - Simplified version for frontend
// Uses Odoo's standard redirect flow without complex dependencies

if (typeof odoo !== 'undefined' && odoo.define) {
    odoo.define('payment_sequra.template', function (require) {
        'use strict';
        
        // For SeQura, we rely on the redirect_form_html from the backend
        // No additional JavaScript processing needed
        console.log('SeQura payment module loaded successfully');
        
        return {};
    });
} else {
    console.log('SeQura payment module loaded (no odoo.define available)');
}

