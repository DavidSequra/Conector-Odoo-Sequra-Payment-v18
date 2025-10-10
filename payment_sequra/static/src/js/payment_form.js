// SeQura Payment Form Handler - Plain JavaScript/jQuery Version
(function() {
    'use strict';
    
    // Wait for DOM and jQuery to be ready
    function initializeSequraPayment() {
        if (typeof $ === 'undefined') {
            setTimeout(initializeSequraPayment, 100);
            return;
        }
        
        console.log('SeQura Payment: Initializing payment form handler +4');
        
        // Handle SeQura payment form submission
        $(document).on('submit', '.oe_sequra_payment_form', function(ev) {
            ev.preventDefault();
            var $form = $(this);
            
            console.log('SeQura Payment: Form submitted');
            
            // Show loading indicator
            showLoadingIndicator($form);
            
            // Collect form data
            var formData = new FormData($form[0]);
            
            // Make API call to SeQura endpoint
            $.ajax({
                url: '/payment/sequra/process',
                type: 'POST',
                dataType: 'json',
                data: formData,
                cache: false,
                contentType: false,
                processData: false,
                timeout: 30000
            }).done(function(response) {
                console.log('SeQura Payment: API response received', response);
                handleApiResponse(response);
            }).fail(function(xhr, status, error) {
                console.error('SeQura Payment: API error', status, error);
                handleApiError(xhr, status, error);
            }).always(function() {
                hideLoadingIndicator($form);
            });
        });
        
        /**
         * Handle successful API response from SeQura
         */
        function handleApiResponse(response) {
            if (response.success && response.redirect_url) {
                console.log('SeQura Payment: Redirecting to', response.redirect_url);
                // Redirect to SeQura payment page
                window.location.href = response.redirect_url;
            } else if (response.success && response.payment_form_html) {
                console.log('SeQura Payment: Displaying inline form');
                // Display inline payment form from SeQura
                displayPaymentForm(response.payment_form_html);
            } else {
                // Handle error
                var errorMsg = response.error || 'Payment processing failed. Please try again.';
                console.error('SeQura Payment: Response error', errorMsg);
                showError(errorMsg);
            }
        }
        
        /**
         * Handle API errors
         */
        function handleApiError(xhr, status, error) {
            console.error('SeQura API error:', status, error);
            var errorMessage = 'Unable to process payment. Please try again or contact support.';
            
            if (xhr.responseJSON && xhr.responseJSON.error) {
                errorMessage = xhr.responseJSON.error;
            }
            
            showError(errorMessage);
        }
        
        /**
         * Display payment form from SeQura
         */
        function displayPaymentForm(formHtml) {
            // Create a container for the SeQura form
            var $container = $('<div class="sequra-payment-container">').html(formHtml);
            
            // Find the payment form
            var $paymentForm = $('.oe_sequra_payment_form').first();
            
            // Replace the current form with SeQura's form
            $paymentForm.parent().append($container);
            $paymentForm.hide();
        }
        
        /**
         * Show loading indicator
         */
        function showLoadingIndicator($form) {
            var $submitBtn = $form.find('button[type="submit"], input[type="submit"]');
            $submitBtn.prop('disabled', true);
            
            // Change icon to spinner
            var $icon = $submitBtn.find('.fa');
            if ($icon.length) {
                $icon.removeClass('fa-lock').addClass('fa-spinner fa-spin');
            }
            
            // Add loading text
            var originalText = $submitBtn.data('original-text') || $submitBtn.text();
            if (!$submitBtn.data('original-text')) {
                $submitBtn.data('original-text', originalText);
            }
            $submitBtn.html('<i class="fa fa-spinner fa-spin"></i> Processing...');
            
            // Add loading overlay
            if (!$form.find('.payment-loading-overlay').length) {
                $form.append('<div class="payment-loading-overlay"><i class="fa fa-spinner fa-spin fa-2x"></i></div>');
            }
        }
        
        /**
         * Hide loading indicator
         */
        function hideLoadingIndicator($form) {
            var $submitBtn = $form.find('button[type="submit"], input[type="submit"]');
            $submitBtn.prop('disabled', false);
            
            // Restore original text
            var originalText = $submitBtn.data('original-text');
            if (originalText) {
                $submitBtn.html(originalText);
            }
            
            $form.find('.payment-loading-overlay').remove();
        }
        
        /**
         * Show error message
         */
        function showError(message) {
            // Remove existing alerts
            $('.sequra-payment-alert').remove();
            
            // Create error alert
            var $alert = $('<div class="alert alert-danger sequra-payment-alert" role="alert">')
                .html('<i class="fa fa-exclamation-triangle"></i> ' + message);
            
            // Insert before the first payment form
            var $paymentForm = $('.oe_sequra_payment_form').first();
            if ($paymentForm.length) {
                $paymentForm.before($alert);
            } else {
                $('body').prepend($alert);
            }
            
            // Auto-hide after 10 seconds
            setTimeout(function() {
                $alert.fadeOut();
            }, 10000);
        }
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeSequraPayment);
    } else {
        initializeSequraPayment();
    }
    
})();