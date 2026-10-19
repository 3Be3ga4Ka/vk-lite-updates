# VK Lite — reference update 0.25

Reference: five screenshots supplied by the owner in this conversation (chats, feed, menu, profile, notifications). No remote website assets or personal content copied into the APK.

## Shared structure

- VK dark surface #191919, between-card background #0A0A0A, secondary text #939393; system sans typeface assets already in the client.
- Header 56 dp; monochrome 28 dp toolbar icons; 48 dp touch targets.
- Persistent six-item navigation, 52 dp content height plus system navigation inset. No visible labels, accessible labels retained. Active icon uses primary text, unread badge retains real cached chat count.
- VK navigation instance retained during ordinary page changes. Other screens still replace content; no claim of retaining every view or suppressing necessary rendering.

## Screen differences

Chats: 60 dp avatars (44 compact), 80 dp row minimum; existing online dots preserved, optional preview settings preserved. Search/filter controls initially collapsed for the unfiltered list; header search expands them. Title opens tools, floating button starts a chat.

Menu: four color-coded tiles per row; three at narrow widths or large fonts/scales. 56 dp icons, wrapping labels. Reference's large empty region is omitted: useful controls start under the header. Less-used libraries and accounts live in More.

Feed: 80 dp story ring / 70 dp photo, 20 dp card corners, edge-to-edge cards separated by 8 dp. No made-up posts/stories/business notifications.

Profile: 100 dp centered avatar, 24 sp centered title, 40 dp main action, rounded friends and media blocks. Media fetch is independently guarded by screen generation and local selection; no stale result replaces a later tab. Own profile starts with music, others with photos. Albums/video open existing full sections.

Notifications: one header, settings/actions behind the gear. Existing notification rows, routing, and API behavior remain.

## Validation

Release build + static Android lint. No emulator or real-device/account run in this iteration, consistent with the owner's earlier preference. Reference screenshot font overrides and all server-driven layouts are not reproduced exactly.

## Additional scope

Navigation editor stores a validated unique whitelist of 4–6 destinations; Menu is mandatory. Profile and session data are not touched. A changed navigation signature rebuilds Activity once on return from the editor; ordinary tab changes reuse the navigation object.

Community admin uses the existing session, generation/account/epoch guards, explicit write confirmations and server acknowledgements. Role is rechecked before each write. Lists paginate by 50. Core native actions cover metadata, status, avatar, content sections, comment filters, links, membership, join requests and bans. Publications reuse the existing owner-bound composer and media upload path. Changing manager roles and business/financial/advanced admin tools remain in the clearly labelled official web management link; this is not feature parity with the entire VK admin console.

Reference for parameters: official VKCOM/vk-api-schema groups/methods.json (published schema 5.199; client requests 5.289). Official dev.vk.com wall.post page reported maintenance during retrieval; metadata confirms creation and scheduled publishing. Runtime method availability is not assumed from schema alone. No live administrative changes were made during development.
