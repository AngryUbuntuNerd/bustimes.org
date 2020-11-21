/*jslint browser: true*/
/*global accessibleAutocomplete*/

(function () {
    'use strict';

    // vehicle type
    accessibleAutocomplete.enhanceSelectElement({
        selectElement: document.getElementById('id_vehicle_type')
    });

    // withdrawn
    var withdrawnElement = document.getElementById('id_withdrawn');
    function handleWithdrawn() {
        var display = withdrawnElement.checked ? 'none' : '';
        document.querySelectorAll('.edit-vehicle > *').forEach(function(element) {
            if ((element.querySelector('input, label')) && !element.querySelector('#id_withdrawn, #id_url, #id_user')) {
                element.style.display = display;
            }
        });
        if (display === '') {
            toggleOtherColour();
        }
    }
    withdrawnElement.addEventListener('change', handleWithdrawn);
    handleWithdrawn();

    // other colour
    function toggleOtherColour() {
        var otherCheckbox = document.querySelector('#id_colours [value="Other"]');
        var display = otherCheckbox.checked ? '' : 'none';
        document.getElementById('id_other_colour').parentNode.style.display = display;
    }
    document.querySelectorAll('#id_colours [type="radio"]').forEach(function(radio) {
        radio.addEventListener('change', toggleOtherColour);
    });
    toggleOtherColour();
})();
