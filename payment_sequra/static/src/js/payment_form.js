// SeQura Payment Form Handler - Direct Approach
(function() {
    'use strict';
    
    // Wait for DOM and jQuery to be ready
    function initializeSequraPayment() {
        if (typeof $ === 'undefined') {
            setTimeout(initializeSequraPayment, 100);
            return;
        }
        
        console.log('SeQura Payment: Initializing direct redirect handler v9');
        
        // Function to get SeQura redirect URL directly
        function getSequraRedirectUrl(providerId, callback) {
            console.log('SeQura Payment: Getting redirect URL for provider', providerId);
            
            // Make AJAX call to create transaction and get redirect URL
            $.ajax({
                url: '/shop/payment/transaction/' + providerId,
                method: 'POST',
                data: {
                    'access_token': $('input[name="access_token"]').val() || '',
                    'csrf_token': $('input[name="csrf_token"]').val() || ''
                },
                success: function(data) {
                    console.log('SeQura Payment: Transaction created, checking for redirect URL');
                    
                    // Look for sequra_redirect_url in the response
                    if (data && typeof data === 'string') {
                        var match = data.match(/sequra_redirect_url['"]\s*:\s*['"]([^'"]+)['"]/);
                        if (match && match[1]) {
                            console.log('SeQura Payment: Found redirect URL:', match[1]);
                            callback(match[1]);
                            return;
                        }
                    }
                    
                    console.log('SeQura Payment: No redirect URL found in response');
                    callback(null);
                },
                error: function(xhr, status, error) {
                    console.error('SeQura Payment: Error getting redirect URL:', error);
                    callback(null);
                }
            });
        }
        
        // Intercept "Pay Now" button click for SeQura
        $(document).on('click', 'button[name="o_payment_submit_button"]', function(ev) {
            var selectedProvider = $('input[name="provider_id"]:checked');
            
            if (selectedProvider.length && selectedProvider.data('provider-code') === 'sequra') {
                console.log('SeQura Payment: Intercepting Pay Now button for SeQura');
                ev.preventDefault();
                ev.stopPropagation();
                
                var providerId = selectedProvider.val();
                var $button = $(this);
                var originalText = $button.text();
                
                // Show loading state
                $button.prop('disabled', true).text('Redirecting to SeQura...');
                
                // Get redirect URL and redirect
                getSequraRedirectUrl(providerId, function(redirectUrl) {
                    if (redirectUrl) {
                        console.log('SeQura Payment: Redirecting to:', redirectUrl);
                        window.location.href = redirectUrl;
                    } else {
                        console.log('SeQura Payment: Fallback to normal flow');
                        $button.prop('disabled', false).text(originalText);
                        // Let the normal flow continue by removing our handler and clicking again
                        $button.off('click').trigger('click');
                    }
                });
                
                return false;
            }
        });
        
        // Legacy handlers for other approaches
        $(document).on('submit', '#payment_method', function(ev) {
            var selectedProvider = $('input[name="provider_id"]:checked');
            if (selectedProvider.length && selectedProvider.data('provider-code') === 'sequra') {
                console.log('SeQura Payment: Form submission intercepted, but should be handled by button click');
            }
        });
    }
    
    // Initialize when ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeSequraPayment);
    } else {
        initializeSequraPayment();
    }
})();