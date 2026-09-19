# Career Agent Browser Companion

This Chrome/Chromium extension is the execution layer for authenticated application portals. Version 1.1.0 adds a paired browser runner, resilient multi-step form handling, and reload-safe submission reconciliation.

It does **not** store employer passwords or session cookies in Career Agent. You sign in to Amazon, Google, Microsoft, Workday, etc. in your normal browser. After you approve an exact packet in Career Agent, the application page opens with a short-lived capability in the URL fragment. The extension removes that fragment immediately, fetches the approved packet, fills the live form, and submits only after the backend policy gate authorizes that packet.

It waits for login, MFA, CAPTCHA, unknown required fields, or an unrecognized form step. The on-page message identifies what needs attention and continues when the form changes. It never guesses unsupported screening answers or bypasses employer controls. A Pause button stops the current run.

## Demo setup

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked** and select this `browser-companion` directory.
4. Sign in to the employer account in the same Chrome profile.
5. Reload the extension after updating this directory, then refresh the Career Agent dashboard. An already-loaded unpacked extension does not update when the backend deploys.
6. In **Settings**, connect the browser once and enable the desired automation mandate. While Chrome is running, the extension checks for the next eligible application every minute and opens its employer form in a background tab. The backend decides eligibility and enforces the mandate, approval, cap, and submission policy.
7. For an individual reviewed application, **Apply in signed-in browser** remains available.

The backend records a write boundary immediately before the extension clicks the final submit control. A confirmed employer page is recorded as `Submitted`; an ambiguous post-click result becomes `OutcomeUnknown` so the agent will not blindly retry.

The runner connection lasts at most seven days. It stores a scoped runner capability in extension-local storage, never an employer password, employer cookie, or Career Agent login token. Individual employer sessions remain short-lived and tab-bound. Same-employer popups may inherit their opener's application; unrelated tabs and other Workday tenants cannot claim it.

## Form behavior and verification

The companion reads semantic labels rather than generated input IDs, supports native and custom choice widgets, waits for delayed option menus, uploads through hidden resume inputs, and preserves fields already filled by the user. Repeated work/education rows use explicit section and record indices. It expands **Add** controls only for history records present in the approved packet.

Run the companion regression suite from the repository root after installing the worker dependencies and Chromium:

```text
npm --prefix worker-browser ci
npx --prefix worker-browser playwright-core install chromium
node --test browser-companion/test/*.test.mjs
```

The suite runs real Chromium against local employer-shaped fixtures and tests the extension service worker with mocked Chrome APIs. It covers custom menus, native selects, hidden resume upload, repeated records, unknown required answers, delayed navigation, dispatch reconciliation, tab isolation, and runner pairing. These tests do not claim that every live employer form is supported or submit a real job application.


## Why the extension requests access to HTTPS employer pages

Career Agent discovers jobs across different ATS products and many employers wrap
the same ATS in their own careers domain (for example a Greenhouse form embedded
inside an employer site). The extension therefore has HTTPS host access broadly,
but `content.js` exits unless the tab carries a current Career Agent browser
session. It does not crawl ordinary browsing tabs. The short-lived session is
bound to one approved application packet and expires after ten minutes.
