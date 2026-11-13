// Pocket FM adapter: discover the user's supplied route in the current DOM.
// No private APIs, purchased offers, or fixed screen coordinates are used.
(() => {
  const enabled = () => location.hostname === 'pocketfm.com' || location.hostname.endsWith('.pocketfm.com');
  const text = node => (node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
  const visible = node => {
    if (!node || node.closest('[hidden], [aria-hidden="true"], #shadow-assistant-frame')) return false;
    const box = node.getBoundingClientRect(), style = getComputedStyle(node);
    return box.width > 1 && box.height > 1 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  function clickable(node) {
    for (let current = node, depth = 0; current && depth < 5; current = current.parentElement, depth++) {
      if (current.matches('button, a[href], [role="button"], [role="menuitem"], [tabindex="0"]') ||
          getComputedStyle(current).cursor === 'pointer') return current;
    }
    return null;
  }
  function controls() {
    if (!enabled()) return [];
    const found = [], seen = new Set();
    function add(node, kind, label) {
      if (!node || !visible(node) || seen.has(node) || node.closest('form')) return;
      seen.add(node); found.push({node, kind, label});
    }
    const bodyText = text(document.body);
    const nodes = [...document.querySelectorAll('button,a,[role="button"],[role="menuitem"],div,span,p')];
    for (const node of nodes) {
      if (!visible(node)) continue;
      const label = text(node);
      if (label.length > 160 || [...node.children].some(child => text(child) === label)) continue;
      // Pocket FM uses delegated handlers on plain div/span elements. Exact
      // verified route labels remain clickable through event bubbling even
      // when the site provides neither a role nor a pointer cursor.
      const target = clickable(node) || node;
      if (/^manage subscriptions$/i.test(label)) add(target, 'manage_subscriptions', 'Manage Subscriptions');
      if (/^cancel subscription$/i.test(label)) add(target, 'cancel_subscription', 'Cancel Subscription');
      if (/^(?:confirm cancellation|confirm cancel|yes,? cancel(?: subscription)?)$/i.test(label))
        add(target, 'confirm_cancel', label);
      if (/active subscriptions/i.test(bodyText) && /^\d+\s*mins?(?:\s+daily)?$/i.test(label))
        add(target, 'active_plan', label);
    }
    for (const node of document.querySelectorAll('img,[aria-label],[title],[data-testid],[class*="avatar" i],[class*="profile" i]')) {
      const label = [node.getAttribute('alt'),node.getAttribute('aria-label'),node.getAttribute('title'),
        node.getAttribute('data-testid'),node.getAttribute('class')].join(' ');
      const box = node.getBoundingClientRect();
      const named = /profile|avatar|anonymous|account/i.test(label) && box.width <= 150 && box.height <= 150;
      const headerAvatar = node.tagName === 'IMG' && box.top >= 0 && box.top < 100 &&
        box.left > innerWidth * 0.75 && box.width >= 20 && box.width <= 90 &&
        Math.abs(box.width - box.height) < 15;
      if (named || headerAvatar) add(clickable(node) || node, 'profile', 'Profile');
    }
    return found;
  }
  function state() {
    if (!enabled()) return null;
    const bodyText = text(document.body);
    if (/subscription (?:has been |is )?cancelled|cancellation (?:is )?(?:confirmed|successful)/i.test(bodyText)) return 'cancelled';
    if (/confirm cancellation|confirm cancel|yes,? cancel/i.test(bodyText)) return 'confirmation';
    if (/current plan details/i.test(bodyText)) return 'plan_details';
    if (/active subscriptions/i.test(bodyText)) return 'active_subscriptions';
    if (/manage subscriptions/i.test(bodyText)) return 'profile_menu';
    return 'home';
  }
  function contextText() {
    if (!enabled()) return '';
    // Drawers on the real site need not have role=dialog. Keep their actual
    // headings ahead of the long home feed in the bounded page snapshot.
    return [...document.querySelectorAll('h1,h2,h3,h4,div,span,p,[role="status"],[role="alert"]')]
      .filter(node => visible(node) && /^(?:active subscriptions|current plan details|(?:your )?subscription (?:has been |is )?cancelled[.!]?|cancellation (?:is )?(?:confirmed|successful)[.!]?)$/i.test(text(node)))
      .map(node => node.innerText || node.textContent || '').join('\n').slice(0, 1000);
  }
  globalThis.ShadowPocketFM = {enabled, controls, state, contextText};
})();
