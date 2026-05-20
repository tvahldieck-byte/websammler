// WebSammler – Globales JavaScript

// Initialisierung nach DOM-Load
document.addEventListener('DOMContentLoaded', () => {

  // Bootstrap Tooltips aktivieren
  const tooltips = document.querySelectorAll('[title]');
  tooltips.forEach(el => {
    new bootstrap.Tooltip(el, { trigger: 'hover' });
  });

  // Auto-Dismiss für Alerts nach 4 Sekunden
  document.querySelectorAll('.alert.alert-success, .alert.alert-info').forEach(el => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      if (bsAlert) bsAlert.close();
    }, 4000);
  });

});
