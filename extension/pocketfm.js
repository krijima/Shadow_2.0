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
    let pointerTarget = null;
    for (let current = node, depth = 0; current && depth < 5; current = current.parentElement, depth++) {
      if (current.matches('button, a[href], [role="button"], [role="menuitem"], [tabindex="0"]')) return current;
      // Cursor is inherited: the heading and chevron share the row's pointer
      // cursor. Highlight the actual row so either manual click is recognized.
      if (!pointerTarget && getComputedStyle(current).cursor === 'pointer' &&
          (!current.parentElement || getComputedStyle(current.parentElement).cursor !== 'pointer')) pointerTarget = current;
    }
    return pointerTarget;
  }
  function candidateNodes(hint) {
    const nodes = new Set();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    // Inspect each text leaf once, then only a bounded number of nearby
    // containers. Avoid extracting innerText recursively for the whole feed.
    for (let leaf = walker.nextNode(); leaf; leaf = walker.nextNode()) {
      const value = (leaf.nodeValue || '').trim().replace(/^[\p{Symbol}\p{Punctuation}\s]+/u, '');
      if (value.length > 160 || !hint.test(value)) continue;
      let node = leaf.parentElement;
      for (let depth = 0; node && node !== document.body && depth < 4; depth++, node = node.parentElement) {
        nodes.add(node);
      }
    }
    return [...nodes];
  }
  function controls() {
    if (!enabled()) return [];
    const found = [], seen = new Set();
    function add(node, kind, label) {
      if (!node || !visible(node) || seen.has(node) || node.closest('form')) return;
      seen.add(node); found.push({node, kind, label});
    }
    const bodyText = text(document.body);
    const nodes = candidateNodes(/^(?:manage|cancel|confirm|yes|\d+)\b/i);
    for (const node of nodes) {
      if (!visible(node)) continue;
      const rawLabel = text(node);
      const label = rawLabel.replace(/^[\p{Symbol}\p{Punctuation}\s]+/u, '');
      if (label.length > 160 || [...node.children].some(child => text(child) === rawLabel)) continue;
      // Pocket FM uses delegated handlers on plain div/span elements. Exact
      // verified route labels remain clickable through event bubbling even
      // when the site provides neither a role nor a pointer cursor.
      const target = clickable(node) || node;
      if (/^manage subscriptions$/i.test(label)) add(target, 'manage_subscriptions', 'Manage Subscriptions');
      if (/^cancel subscription$/i.test(label)) add(target, 'cancel_subscription', 'Cancel Subscription');
      if (/^(?:confirm cancellation|confirm cancel|yes,? cancel(?: subscription)?)$/i.test(label))
        add(target, 'confirm_cancel', label);
      if (/active subscriptions/i.test(bodyText) && !/current plan details/i.test(bodyText) && /^\d+\s*mins?(?:\s+daily)?$/i.test(label))
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
    return candidateNodes(/^(?:active|current|subscription|cancellation|your)\b/i)
      .filter(node => visible(node) && /^(?:active subscriptions|current plan details|(?:your )?subscription (?:has been |is )?cancelled[.!]?|cancellation (?:is )?(?:confirmed|successful)[.!]?)$/i.test(text(node)))
      .map(node => node.innerText || node.textContent || '').join('\n').slice(0, 1000);
  }
  async function openProfile(node, click, active = () => true) {
    node.scrollIntoView({block: 'nearest', inline: 'nearest'});
    const box = node.getBoundingClientRect();
    const options = {bubbles: true, cancelable: true, view: window,
      clientX: box.left + box.width / 2, clientY: box.top + box.height / 2, relatedTarget: null};
    // React-style menus listen for mouseover; native menus may listen for
    // mouseenter. Stop as soon as the menu opens rather than toggling it shut.
    for (const type of ['pointerover', 'mouseover', 'mouseenter']) {
      if (!active() || !node.isConnected) return {result: 'cancelled'};
      node.dispatchEvent(type.startsWith('pointer')
        ? new PointerEvent(type, {...options, pointerType: 'mouse', pointerId: 1})
        : new MouseEvent(type, options));
      await new Promise(resolve => setTimeout(resolve, 100));
      if (controls().some(control => control.kind === 'manage_subscriptions')) return {result: 'opened_profile_menu'};
    }
    return active() && node.isConnected ? click() : {result: 'cancelled'};
  }
  globalThis.ShadowPocketFM = {enabled, controls, state, contextText, openProfile};
})();
