const HELP_HINT_STORAGE_KEY = 'checklist_reviewer_help_hint_dismissed_v1';
const HELP_ATTRACTION_DISABLED_KEY = 'checklist_reviewer_help_attraction_disabled_v1';

document.addEventListener('DOMContentLoaded', () => {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach((alert) => {
    setTimeout(() => {
      const alertInstance = bootstrap.Alert.getInstance(alert) || new bootstrap.Alert(alert);
      if (alertInstance) alertInstance.close();
    }, 4000);
  });

  initGettingStartedAccordions(document);
  initHelpHint();
});

/**
 * Expandable steps inside .modal.app-onboarding (scoped so two modals on one page do not cross-close).
 */
function initGettingStartedAccordions(root) {
  root.querySelectorAll('[data-gs-step]').forEach((step) => {
    const toggle = step.querySelector('[data-gs-toggle]');
    if (!toggle || toggle.dataset.gsBound === '1') return;
    toggle.dataset.gsBound = '1';
    toggle.addEventListener('click', () => {
      const willOpen = !step.classList.contains('is-open');
      step.classList.toggle('is-open', willOpen);
      toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      if (willOpen) {
        const modal = step.closest('.modal');
        const scope = modal || document;
        scope.querySelectorAll('[data-gs-step].is-open').forEach((other) => {
          if (other !== step) {
            other.classList.remove('is-open');
            const t = other.querySelector('[data-gs-toggle]');
            if (t) t.setAttribute('aria-expanded', 'false');
          }
        });
      }
    });
  });
}

function dismissHelpHint() {
  try {
    localStorage.setItem(HELP_HINT_STORAGE_KEY, '1');
  } catch (_) {
    /* ignore */
  }
  const hint = document.getElementById('appHelpHint');
  const btn = document.getElementById('appHelpButton');
  if (hint) hint.classList.remove('is-visible');
  // Attention animation is controlled separately via HELP_ATTRACTION_DISABLED_KEY
}

function initHelpHint() {
  const btn = document.getElementById('appHelpButton');
  const hint = document.getElementById('appHelpHint');
  const dismiss = document.getElementById('appHelpHintDismiss');
  const disableAttraction = document.getElementById('disableHelpAttraction');
  if (!btn || !hint) return;

  let dismissed = false;
  try {
    dismissed = localStorage.getItem(HELP_HINT_STORAGE_KEY) === '1';
  } catch (_) {
    dismissed = false;
  }

  let attractionDisabled = false;
  try {
    attractionDisabled = localStorage.getItem(HELP_ATTRACTION_DISABLED_KEY) === '1';
  } catch (_) {
    attractionDisabled = false;
  }

  // Hint bubble is first-time only (dismissable), but the attention animation should play every time
  // unless the user explicitly disables it.
  if (!dismissed) hint.classList.add('is-visible');
  btn.classList.toggle('is-pulse', !attractionDisabled);

  if (disableAttraction) {
    disableAttraction.checked = attractionDisabled;
    disableAttraction.addEventListener('change', () => {
      const disabled = !!disableAttraction.checked;
      try {
        localStorage.setItem(HELP_ATTRACTION_DISABLED_KEY, disabled ? '1' : '0');
      } catch (_) {
        /* ignore */
      }
      btn.classList.toggle('is-pulse', !disabled);
    });
  }

  if (dismiss) {
    dismiss.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dismissHelpHint();
    });
  }

  const helpModal = document.getElementById('appHelpModal');
  if (helpModal) {
    helpModal.addEventListener('show.bs.modal', () => {
      // Hide the one-time hint bubble once the modal is opened, but keep the attention animation
      // (unless the user disabled it via the checkbox).
      dismissHelpHint();
    });
  }
}
