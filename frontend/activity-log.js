/* Operational telemetry only: no input values, text, query strings or keys. */
(() => {
  'use strict';
  const endpoint = 'https://voice.quantareon.com/api/activity';
  let visitor;
  try {
    visitor = sessionStorage.getItem('qa_visit');
    if (!/^[a-f0-9]{32}$/.test(visitor || '')) {
      visitor = crypto.randomUUID().replace(/-/g, '');
      sessionStorage.setItem('qa_visit', visitor);
    }
  } catch (_) { return; }
  const originalFetch = window.fetch.bind(window);
  // Correlate actual engine requests with the same anonymous browser session.
  window.fetch = function(input, init) {
    try {
      const url = new URL(input instanceof Request ? input.url : input, location.href);
      if (url.origin === 'https://voice.quantareon.com') {
        const options = {...init};
        const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
        headers.set('X-Visit-ID', visitor);
        options.headers = headers;
        return originalFetch(input, options);
      }
    } catch (_) { /* Keep the original request's behaviour. */ }
    return originalFetch(input, init);
  };
  let sent = 0;
  const names = {kChatSend:'birth_details_send', kConfirmPlace:'location_confirm',
    kChatMic:'microphone_toggle', rPay:'payment_start', kOpen:'report_open',
    kChatRedo:'birth_details_restart', sDl:'report_download', tCancel:'payment_cancel'};
  const report = (action, control = 0, name = '') => {
    if (++sent > 120) return;
    let page = location.pathname;
    if (!/^\/[a-z0-9_-]{0,50}(?:\.html)?$/.test(page)) page = '/';
    originalFetch(endpoint, {
      method: 'POST', keepalive: true,
      headers: {'Content-Type': 'text/plain', 'X-Visit-ID': visitor},
      body: JSON.stringify({visitor, page, action, control, name})
    }).catch(() => {});
  };
  report('page_open');
  document.addEventListener('click', e => {
    const control = e.target instanceof Element ? e.target.closest('button,a,[role="button"],input[type="submit"]') : null;
    if (!control) return;
    const controls = Array.from(document.querySelectorAll('button,a,[role="button"],input[type="submit"]'));
    report(control.tagName === 'A' ? 'link_click' : 'button_click', controls.indexOf(control) + 1, names[control.id] || '');
  }, true);
  document.addEventListener('submit', () => report('form_submit'), true);
  window.addEventListener('pagehide', () => report('page_leave'));
  window.addEventListener('error', () => report('browser_error'));
  window.addEventListener('unhandledrejection', () => report('promise_rejection'));
})();
