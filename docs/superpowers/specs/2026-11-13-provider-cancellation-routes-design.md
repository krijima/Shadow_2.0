# Provider Cancellation Route Design

## Intent

One Observe Start should follow provider-documented, reversible account navigation and stop before cancellation, renewal changes, or other account changes. Apple Music menu state must be re-read after it opens, including delayed same-URL updates. Guide advances after the user clicks the displayed box or website control.

## Scope and constraints

- Providers: Apple Music web, Spotify, and Amazon Prime India.
- Official support instructions are route hints. Only visible DOM controls with verified same-origin destinations or explicit menu/disclosure semantics are eligible for automatic clicks.
- Consequential actions remain highlighted with “Review cancellation.”; SHADOW never clicks them in Observe or Guide.
- If no meaningful state change follows a menu-opening action, stop with specific guidance such as “Open Settings to continue.” Do not repeat toggling controls.
- If billing is handled by a partner, show the handoff. Cross-origin provider steps require the user’s origin permission where the extension does not already have it.
- StreamCove Demo and its approval/Reject behavior remain unchanged.

## Approaches considered

1. Let the general planner infer every step from the page. Rejected because it repeated Apple’s account-menu toggle after the menu was open.
2. Route hints from official help pages, deterministically matched to the current DOM and revalidated by the existing navigation policy. Chosen because it fixes Apple’s state ambiguity while keeping website controls and destinations as the execution authority.
3. Hard-code provider URLs and click them directly. Rejected because provider UI changes, account region and billing partner state vary.

## Implementation notes

- Curate source URLs and route labels from official Apple Support, Spotify Support, Amazon India’s official forum response, and Prime Video Help.
- Detect visible menu/dialog state, prefer a visible Settings item over its My Account opener, and require structural evidence for menu openers.
- Stabilize same-page DOM changes before taking the next route snapshot.
- Stop at cancellation, end-membership, auto-renewal, delete, submit, or ambiguous controls.
- Verify with local browser routes for Apple menu-already-open, delayed menu rendering, Spotify and Amazon entry points, and existing StreamCove Demo Accept/Reject tests.

## Out of scope

- Performing final cancellation or changing renewal/account settings.
- Reading or changing account secrets, payment details, or credentials.
- Treating provider documentation or model output as authorization to click.
