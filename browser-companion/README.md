# Career Agent Browser Companion

This Chrome/Chromium extension is the execution layer for authenticated application portals.

It does **not** store employer passwords or session cookies in Career Agent. You sign in to Amazon, Google, Microsoft, Workday, etc. in your normal browser. After you approve an exact packet in Career Agent, the application page opens with a short-lived capability in the URL fragment. The extension removes that fragment immediately, fetches the approved packet, fills the live form, and submits only after the backend policy gate authorizes that packet.

It deliberately stops for login, MFA, CAPTCHA, unknown required fields, or an unrecognized form step. It never tries to bypass those controls.

## Demo setup

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked** and select this `browser-companion` directory.
4. Sign in to the employer account in the same Chrome profile.
5. In Career Agent, prepare and approve a live application, then click **Apply in signed-in browser**.

The backend records a write boundary immediately before the extension clicks the final submit control. A confirmed employer page is recorded as `Submitted`; an ambiguous post-click result becomes `OutcomeUnknown` so the agent will not blindly retry.
