// Affiche un loader lors de la soumission d'un formulaire
window.addEventListener('DOMContentLoaded', function() {
    var forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function() {
            var loader = document.getElementById('loader');
            if (loader) loader.style.display = 'flex';
        });
    });
});
// Exemple : confirmation avant action destructive
function confirmAction(message) {
    return window.confirm(message || 'Êtes-vous sûr ?');
} 
