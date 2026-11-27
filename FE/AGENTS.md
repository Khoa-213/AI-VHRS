# AGENTS.md

Rules for any agent or developer changing this front end (`AI-VHRS/FE`, React + Vite + TypeScript).

## Languages are mandatory: English, Japanese, Vietnamese

The app ships in three languages: `en`, `ja`, `vi`. The user switches with the language button next to the theme button.
**Every visible string must exist in all three languages.** A screen or function is not done until it is translated.

Applies to every new or changed screen, component, message, error, tooltip, aria-label, placeholder, empty state,
confirmation, status label and document title.

### Exceptions (leave in the original language)

- The hero slogan in `src/pages/landing/components/Hero.tsx` (`lp-h1`, "make your own style").
- Brand, product and partner names: AI-VHRS, FR3, Fairino, GHN, VNPay, MoMo, ZaloPay, VietQR, Vietcombank.
- Content the user typed or drew, and people's names.
- Sample content that is meant to look like customer content (the Vietnamese sample texts in the catalog).
- Technical identifiers: order ids, GHN status codes (`delivering`), file names.

## How to add text

1. Add the key to **all three** dictionaries in `src/i18n/`: `en.ts` (source), `vi.ts`, `ja.ts`.
   `vi.ts` and `ja.ts` are typed `Record<Key, string>`, so a missing key fails `tsc -b`.
2. Use it in a component:

```tsx
import { useT, useTn, useLocale } from '../../i18n'

const t = useT()          // t('co.back'), t('tk.sub.pack', { n: 2, total: 3 })
const tn = useTn()        // translate catalog names: tn(order.spec.paper), tn(order.title)
const locale = useLocale() // dates and numbers: date.toLocaleDateString(locale, ...)
```

- Variables use `{name}` placeholders. Do not build sentences by concatenating translated pieces; one key per sentence,
  because word order differs between English, Japanese and Vietnamese.
- Keys are `<area>.<name>`: `nav.`, `co.` (create order), `or.`/`ov.` (order page), `os.`/`ot.`/`ps.` (status, type and production labels), `dp.` (deposit), `err.` (API errors), `sp.` (shipping desk), `sc.`/`as.`/`sd.` (staff),
  `td.`/`po.`/`qc.`/`rp.` (technician), `lp.` (landing).
- Catalog and domain names (paper, ink, pens, roster skills, check names, reject reasons) are stored in English in
  data and orders. Keep the stored value English and translate at display time with `tn()`; add an `n.<English text>`
  key to the three dictionaries. Composite strings split on ` · ` and ` × ` are handled by `tn()`.
- Customer order statuses are backend codes (`QUOTED`). Display them with `t(\`os.${order.status}\`)`. Names that come from the catalog (paper, pen, ink, templates) are data and are shown as received.
- Functions outside React (utils, services) take `t` / `tn` / `locale` as parameters, see `utils/pricing.ts`.
  Do not import the dictionaries directly.
- Never hard-code a locale such as `'en-GB'`. Use `useLocale()`.
- Errors thrown from non-React code carry a translation key (`new Error('qc.err.process')`) and the component
  translates it. Technical network errors may stay as they are.

## New screens

- Put `<LanguageToggle />` right after every `<ThemeToggle ... />` (any header or top bar). It styles itself
  (`components/ui/language.css`, the landing page's look) so it is the same button everywhere: do not restyle it per page.
- Staff and Manager pages render inside `components/ws/Shell.tsx` (header and labelled sidebar); Admin pages inside `AdminFrame`.
- Keep layout working at the longest language: Vietnamese and Japanese text can be longer or wrap differently.
  Do not give buttons a fixed width that clips them.

## Before finishing

```bash
npx tsc -b            # fails if vi.ts or ja.ts miss a key
npm run i18n:check    # fails on unknown keys and hard-coded English in JSX, aria-label, placeholder, title, alt
npm run build
```

Then switch the language to Japanese and Vietnamese in the browser and open the screens you touched.
Text that stays English is a bug unless it is in the exceptions list above.

## Style notes used in this repo

- No em dash or en dash in user-facing copy. Use a comma, colon or period.
- Icons come from `@phosphor-icons/react`. Colours come from CSS variables in `src/styles/theme.css`.

- Customer and workshop (Staff, Manager) data all come from the API. The localStorage store in `src/store/store.ts` only keeps the signed-in user and profile.


## Customer orders come from the API

The customer flow (create, submit, privacy, quotation, deposit) talks to the backend through `src/services/orders.ts`
(contract in `BE/docs/FE_API_GUIDE.md`, Swagger at `/docs`). Build the UI from what the API accepts and returns: when the
backend gains a field, add it to the UI; do not keep fields the backend does not have.

- A draft is a real order with `order_status = DRAFT`. `CreateOrder.tsx` creates it on the first thing worth saving and
  autosaves every change through `hooks/useSaveQueue.ts`. Drafts list under **Account > Drafts** (`GET /orders?status=DRAFT`).
- Catalog (paper, pen, ink, templates) and the price estimate come from the API. Do not hard-code them.
- The AI assistant is part of Create Order, not a step of its own. Step 1 opens with a pill switch "✦ AI assistant | By myself" (`.co-seg--how`, always opens on "By myself", no localStorage) above the three input modes. Picking "AI assistant" opens `ai/AiPolicyDialog.tsx` with the AI chat data policy from `GET /privacy-policy/ai-chat`; ticking its box records `POST /me/assistant/consent {policy_version}` and only then the chat opens (asked again on every visit, and again when a message comes back `AI_CONSENT_REQUIRED`; messages do not send `ai_consent`). Closing the dialog keeps "By myself". AI moves to the text mode and hides the modes (the assistant writes from text and draws the sketch before the materials are chosen); "By myself" shows the modes. With the assistant (`.co-shell--ai`), `pages/create-order/ai/OrderAssistant.tsx` replaces the estimate box in the right column at **every** step (content, materials, review), and the order's sketch (`.co-sketch`, `ai/SketchView.tsx`) sits under the form in the left column with the estimated price (`.oa-est`, collapsible) in its head. Without the assistant the right column is the usual preview + estimate box. Contract: `BE/docs/FE_API_GUIDE.md` 7s, client `services/orderAi.ts` (stream route, `client_ref`, policy and consent). The backend returns each change as a proposal (migration 0029). **The FE applies it at once only when Undo can bring it back** (owner decision 2026-11-27, audit D02, replacing "always at once" of 2026-11-22): a proposal with `needs_confirmation: false` (words, layout, materials, sketch) is applied right after the turn (`POST .../proposals/{id}/apply`), the order and the sketch are reloaded and the sketch box on the left shows the new sketch. A proposal with `needs_confirmation: true` (it changes quantity, note, authenticity line, restoration mode or the workshop-chooses switch, or it draws over strokes the customer edited: `confirm_reasons`) stays PENDING and its card opens with the reasons and **Apply to the order / Skip**. An applied proposal with `revertible: true` (the order has not changed since) has **Take it back** (`POST .../proposals/{id}/revert`: every field goes back, not only the sketch). Undo / Redo in the chat header (sketch undo / redo, which also restores the form of that drawing) stay as they were. Every message sends `from_order: true`, so a proposal left PENDING (apply refused, e.g. `PROPOSAL_STALE`, shown as `oa.stale.*`) is never built on. In the chat an answer that changes something is a one-line summary (`ProposalCard.tsx`, a `<details>`: status, number of changes, price; it opens to `changes[]` and to the Apply / Skip / Take it back buttons when they apply), with no picture (the picture is the sketch box). Answers are rendered with `RichText.tsx` (paragraphs, `-`/`1.` lists, `**bold**`, React elements only). The composer is one line that grows to 160px (Enter sends, Shift + Enter new line, IME composition respected), with an icon send button; the picked parts of the sketch show as a chip in it. The form (`<fieldset class="co-lock">`) is disabled only while the assistant works (`aiBusy`). `ai/SketchPicker.tsx` (dialog opened from the sketch box) lets the customer pick strokes, words, lines or paragraphs; they go as `selection` with the next message and are cleared after the turn and when the revision changes. No localStorage for proposals. While a message is answered, `ai/ThinkingStage.tsx` is the assistant's row of the conversation (`oa-think`): a ball rises from the send button and opens into a turning sphere of dots (canvas, theme colours) with the current step beside it; when the answer is in it turns green, collapses into a green ball that settles on the avatar's place, and the answer (held back until then, at most 4 s) unfolds there: the bubble opens and `RichText reveal` brings the words in one after the other. The sent message slides up from the message box. With reduced motion: a still sphere and no reveal. The panel also has a switch "AI assistant | Studio staff" (`oa-who`): the staff side (`ai/StaffChat.tsx`) lists the chats of the orders already sent, because a draft has no staff chat (`ORDER_NOT_SUBMITTED`). It is offered only while `GET /studio/assistant/status` says `available`; the backend refuses chat once the order is sent. Check with `node scripts/check-order-ai-browser.mjs` after building.
- Upload mode (`OT1_COPY_RESTORE`) has a "Restored preview" panel under the photos (`.co-restore` in `CreateOrder.tsx`): "Preview restoration" calls `POST /orders/{id}/sketch/generate` with `discard_edits: true` (the workshop's OT-1 engine) and shows the result with `ai/SketchView.tsx`; the right-hand box keeps the original photo for comparison. The engine's `warnings` are shown as received. Rotating, cropping, adding or removing a photo marks it stale (local check, and `inputs_changed` after a reload). A PDF among the photos turns the button off (`PDF_NOT_SUPPORTED_AI`). Check with `node scripts/check-order-restore-browser.mjs` after building.
- `/orders/:id/review` is the order page: it renders by `order_status` and polls while the status moves on its own.
- Deposit (`pages/order/Deposit.tsx`) offers the gateways `GET /payments/gateways` marks `enabled` (VNPay, MoMo, payOS).
  `mode = MOCK` settles with the simulated buttons and keeps the "simulated payment" notice; `SANDBOX` / `LIVE` send the
  customer to `pay_url`, and the gateway brings them back to `/payment/result` (`PaymentResult.tsx`), which polls the order
  and never trusts the gateway's query parameters. `vercel.json` rewrites deep links to `index.html` so that page loads.
- After acceptance (`AWAITING_FINAL_PAYMENT`) the order page links to `/orders/:id/delivery` (`pages/order/Delivery.tsx`):
  delivery with a carrier service priced live for the typed address (`POST /orders/{id}/delivery-quote`), or pick-up at
  the workshop at a booked slot, saved with `PUT /orders/{id}/delivery`. Provinces and wards come from the
  backend (`GET /locations/provinces`, `.../{code}/wards`, GHN two levels, no district; `services/locations.ts`), and the pick-up hours
  copy the backend's `working_hours` seed (`utils/pickupSlots.ts`). Final payment and tracking have no pages yet.
- The workshop side lives in `src/pages/staff/` and `src/services/workshop.ts`: dashboard, `Workbench` (intake, sketch, quotation, chat),
  `Approvals`, `Schedule` and `Catalog` (Manager only, via `services/manage.ts`: templates, robots, price list, and `Materials.tsx`, where paper, pens, ink colors and paper-pen compatibility are one list-and-detail view because the customer only sees the chain paper → compatible active pen → that pen's active inks; a new paper is created with its pens, a new pen with its inks and papers, and anything a customer cannot order is flagged). Role gate is `RequireStaff` (Staff or Manager; Admin has no access to orders).
- Errors from the API go through `orderErrorKey` / `errText` (`services/orders.ts`): known codes have translated text, any other code shows the backend's own message. Add a code to `ERROR_KEYS` and `err.*` when you want it translated.
- Workshop screens (Staff, Manager) render inside `components/ws/Shell.tsx`. Both render the Staff frame (`.ws.ws-staff`, see "Staff presentation"), on top of `components/ws/ws.css` and `workshop.css`; the accent is the `--acc` variable. Use the shared pieces in `components/ws/parts.tsx` and `charts.tsx` before adding new markup.
- The order chat (`components/ui/Chat.tsx`) is shared by the customer and the workshop, and is reached only through the floating
  `components/ui/ChatDock.tsx`: `side="customer"` in `App.tsx`, `side="workshop"` in `Shell.tsx` (Staff, Manager). The list and badge come from
  `services/chat.ts` (`/me/conversations`, `/workshop/conversations`, `.../unread-count`). Opening the customer chat from an order sends
  an `ORDER_CARD` message (the backend returns the same card within 10 minutes); both sides render it from `order_card`.
  Read only only when the order is `REJECTED` or `CANCELLED` (a `COMPLETED` order stays open for complaints), or for a Staff who has not
  claimed the order. Contract: `BE/docs/FE_API_GUIDE.md` section 5.4.
- **Technicians do not use the web** (owner decision 2026-11-26, `BE/docs/FE_TECH_WORKSPACE_HANDOFF.md`): every technician task (jobs, package, choosing the robot, prepare, calibration, REAL switch, robot control and 3D, simulation, photos, QC) is on the **workstation screen served by the Robot Agent** (`robot_agent/vhrs_agent/static/`, `http://<workstation>:8765/`). A technician signed in on the web, and any old `/tech...` link, gets `pages/TechDesktopOnly.tsx`: the workstation address and their jobs read only (`GET /technician/jobs`), no actions, Sign out. Do not add technician screens here. The `td.*`, `rb.*`, `tw.*`, `tq.*`, `nt.*` keys are kept: `DesktopApp/tool/gen_i18n.dart` (the Flutter app) still generates from them.


## Writing styles and where the text sits on the sheet

Rule from the owner (2026-11-27): **what the customer sees must be what the robot writes**. Every picture of letters is drawn by the backend from the strokes the robot follows (no stroke-start dots in customer pictures). Never draw the customer's words with a web font: a browser fills letter shapes the robot does not write.
- **Style cards** (`pages/create-order/TemplateCard.tsx`): `templateCardUrl(id, text)` asks `GET /catalog/templates/{id}/preview?fit=text` for the first line of the customer's words (at most 40 characters), cut to the words; the frame shows it whole (`object-fit: contain`). When that picture fails the template's stored sample (`Template.previewUrl`, from `preview_url`) is shown and the style can still be picked; only a style with nothing to show is disabled.
- **Placement** (step 1, section 3 of `CreateOrder.tsx`, helpers in `pages/create-order/textPlace.ts`): alignment (left / centre / right / justified; nothing picked = centre, as the backend stores it), position on the sheet (top / middle / bottom), the four margins (5 to 80 mm) and the line spacing (0.8 to 2.5). They are keys of the text input's `layout` (`vertical_align`, `margins_mm`, `line_spacing`), saved with `PUT /orders/{id}/inputs/text`. A PUT replaces the whole layout, so the form always sends its whole layout. Settings of single paragraphs (`paragraphs`, made by the assistant or the studio; the form does not edit them) are numbered by paragraph: when the words changed, the text is saved first with `keep_layout: true` and the form's layout goes on top of the layout that comes back.
- **Styles of parts of the text** (`pages/create-order/TextStyleBar.tsx` under the message box, rules in `textSpans.ts`): select words in the box, then italic, underline, double underline, strikethrough, a letter height of their own (4 to 100 mm) or clear. They are the layout's `spans` (`{start, end, size_mm?, italic?, underline?, strike?}`, offsets in code points of the NFC text, never overlapping, at most 200); no bold (owner's decision: the robot would go over each line twice). The box keeps showing plain letters on purpose: only the backend's preview picture shows a style. The formatted parts are listed in words under the buttons (a click selects the part in the box, the cross removes it). The spans follow the typing (`remapSpans`: text typed inside a styled part takes its style, a part whose characters were all removed goes), so the form sends them itself and needs no `keep_layout` for them.
- **Preview** (`hooks/useStyledPreview.ts`): `POST /catalog/templates/{id}/preview {text (up to 2000), alignment, font_size_mm, layout, paper_size}` draws the first page on the sheet of the chosen paper (A5 until one is chosen). The faint frame marks the area inside the margins; the caption says the robot does not write it.
- Text lives under `co.place.`. Check with `node scripts/check-text-layout-browser.mjs` after building (`LAYOUT_REAL_API` + `LAYOUT_REAL_TEMPLATE` draw the screenshots with real strokes from a running backend).

## Forgot password

"Forgot password" stays in the sign-in dialog (`pages/login/ForgotPassword.tsx`, opened from `SignInPanel.tsx`): email, then six boxes for the emailed 6-digit code (typing moves on, a paste fills them, the last digit sends), then the new password, then back to sign in with the email filled in. Calls (`BE/docs/FE_API_GUIDE.md`, 2026-11-26): `POST /auth/password-reset/request {email}` (the mail has a 6-digit code, 15 minutes, 5 tries, 60 s between two codes), then `POST /auth/password-reset/confirm {email, code, new_password}`: the backend checks the code with the new password in one call, so `OTP_INVALID`, `OTP_EXPIRED` and `OTP_TOO_MANY_ATTEMPTS` come after the password step and bring the six boxes back. The first step has a switch "Email | Phone number" (`entry-seg`): by phone the code goes by SMS to the number verified on the account (`POST /auth/phone-reset/request {phone}`, always 202, so the next screen only says "if the number is verified"; the code lasts 5 minutes) and the same confirm call takes `{phone, code, new_password}` (email or phone, never both). There is no reset token and no `/auth/phone-reset/verify` any more. The email flow is code only: the backend dropped the token link (2026-11-26), so nothing reads `?token=`. The page `/reset-password` (`ResetPassword.tsx`), which the email's short link opens, has the same fields on one screen: the email (filled from `?email=`), the six boxes and the new password, with "Send a new code". The boxes are `pages/login/OtpBoxes.tsx`. Check with `node scripts/check-forgot-password-browser.mjs` after building.

## Account area

Everything that belongs to the signed-in user lives under `/account` (`src/pages/account/`): profile, preferences
(theme, language), order history, drafts, payment methods. The top bar and the landing page are for browsing only:
no order history, drafts or cart there. A new user-owned feature gets a section in `Account.tsx`, not a new top bar item.
The avatar in the top bar opens `/account`; sign out lives in the account navigation.

## Phone number: verification and reminders

The account's phone number must be verified before "forgot password by SMS" works (`BE/docs/FE_API_GUIDE.md` 3.2).
- **Account > Profile** (`ProfileSection` in `pages/account/Account.tsx`) is locked until "Edit profile" (in the photo row, right end) is pressed: the fields are `disabled` and dimmed, so they cannot be clicked into; "Update profile" saves and locks it again, "Cancel" puts back what was saved. The photo has its own "Change photo" button. Under the phone field a chip says "Verified" or "Not verified" (icon and word); "Verify" opens `components/account/PhoneVerify.tsx`: `POST /me/phone/otp` (the click sends the SMS), the six boxes (`pages/login/OtpBoxes.tsx`, the sixth digit sends), `POST /me/phone/verify`. It shows the masked number, the 60 s resend wait, the tries left, and says so when the server answers `mode: "MOCK"` (no real SMS). A changed number has to be saved before it can be verified.
- **After sign-in** `POST /auth/login` and `/auth/google` may return `reminders` (`ADD_PHONE` or `VERIFY_PHONE`): `services/auth.ts` passes the first one to the store (`usePhoneReminder`, in memory only) and `components/account/PhoneReminderDialog.tsx` (mounted in `App.tsx`, every role) opens: `ADD_PHONE` asks for the number (`PATCH /me`) and goes on to the verification with the code sent at once; `VERIFY_PHONE` goes straight to the verification and waits for "Send the code". "Later" closes it.
- **Bell**: a notification with `msg_code` `PHONE_ADD` or `PHONE_VER` opens `/account/profile`, for every role.
- Text lives under `ph.`. Check with `node scripts/check-phone-verify-browser.mjs` after building.
- **Firebase phone sign-in (2026-11-27)** sends the real SMS: `services/firebasePhone.ts` (SDK loaded on first use) is on when the four `VITE_FIREBASE_*` values are set (`.env.example`); without them the screens keep the backend's own code flow above (MOCK unless an SMS provider is set), which is what the browser checks cover. `sendPhoneCode(phone, lang)` makes an invisible reCAPTCHA and has Google text the code; `confirm(code)` gives the ID token and signs the Firebase session out. `PhoneVerify` sends the token to `POST /me/phone/verify-firebase`; `ForgotPassword` (by phone) confirms the code at the six boxes and sends `{firebase_id_token, new_password}` (`PHONE_NOT_VERIFIED` when the number has no account, `FIREBASE_TOKEN_*` when the proof is older than 10 minutes or used: both go back to the first step). Firebase's own errors map to keys in `toError` (`auth.err.phone*`). Both screens sit in a modal `<dialog>` at times: the reCAPTCHA container is put inside the dialog and a picture challenge appended to `<body>` is moved into it (outside a modal dialog nothing can be clicked). Not covered by a browser check (needs the real project): try it on the deployed domain with a "Phone numbers for testing" number first.

## Admin area

Admin screens (`src/pages/admin/`) do not use the workshop `Shell`. They use `components/admin/AdminFrame.tsx`, which renders the same workspace as Staff (`.ws.ws-staff` from `components/ws/staff-ui.css`, `staff-theme.css`, `staff-depth.css`): a sticky header (logo, notifications, shared `AppearanceSwitch`, language, profile link), a labelled sidebar (four areas, a count for locked accounts, a drawer on small screens) and the page with its title and back link. Dark and light follow the shared theme. `components/admin/admin-shell.css` only maps the Admin tokens (`--t1`, `--fx-*`, `--accent`) onto the Staff palette and holds the chart colours; `admin-ui.css` holds the blocks (all under `.adm`: white cards, one dark KPI first and one soft KPI last like Staff), `AdminViz.tsx` the tiles and charts (`Kpi`, `Card`, `DayColumns`, `Donut`, `Ring`, `Attention`). Admin logic and routes do not depend on the look.
Admin keeps the calm Staff presentation: no glowing borders, looping motion or marquee numbers; keep brief hover/focus feedback and the mobile drawer transition; respect `prefers-reduced-motion`. Status colours are reserved for state icons and indicators.
The list screens stay simple: accounts (one search box, two filters, one Manage button per person), activity log (kind and record number), settings (label and effect on the left, value on the right, Save appears once the value changed, no reason field). Each block says what it shows; state is never colour alone (icon and word, texture on stacked segments); every chart has a table view and a hover or focus readout; chart colours are the first five slots of the validated palette (`--series-1` to `--series-5`, stepped for dark and light). New admin text goes under `adm.`, `st.`, `ig.`, `sy.`, `au.`.

Admin copy stays concise: no navigation descriptions, greeting, page introductions or explanatory card subtitles. Keep metric units/time windows, chart legends, setting effects, error details and consequences of sensitive actions.

Admin subpages show the shared back-to-overview link in `AdminFrame`. Use `AdminSelect` for dropdowns: translated option labels, keyboard navigation, a viewport-bounded popup and disabled states. Verify navigation and dropdown interactions with `node scripts/check-admin-browser.mjs` after building.

Admin dropdowns, including the audit record-kind filter, remain scrollable with wheel, touch and keyboard. Hide the scrollbar chrome on `.adm-select-menu`; do not replace these dropdowns with wrapping pills.

## Staff presentation

Staff retains the workshop `Shell` and existing workflow components. `components/ws/staff-ui.css` is scoped to `.ws.ws-staff` (`area="staff"` and `"manager"`). Its CRM reference lives in `crm_video_reference/`: a sticky header for the logo, notifications, appearance, language and profile link, plus a labelled workflow sidebar with a mobile drawer, cool white page, white cards, black/deep navy accents and one dark KPI. Use dark text and a navy keyboard focus ring with clear contrast in both themes. Staff and Admin share the saved `AppearanceSwitch` preference. `staff-depth.css` adds gradients, layered surfaces and shadows scoped to Staff. No abstract 3D shapes (spheres, rings) on Staff screens. `staff-theme.css` supplies Staff dark tokens and surfaces; paper previews retain their original colours. `BrandLogo` follows the theme. Manager uses the same frame (see "Manager area").

`/staff/review` shows the existing open-order groups as responsive pipeline columns. Cards open the existing `/staff/review/:id` list/detail route. Stage/scope/search/collapse/pagination rules and action handlers stay unchanged; no drag-and-drop status mutations. For a Manager the same screens render in the Staff frame with the Manager sidebar. Staff filters use `AdminSelect`, portalled into `.ws-staff` for light tokens, with hidden scrollbar chrome. The dashboard's 7/30-day selector affects the received-orders chart only; KPIs keep current totals. No sample data or unsupported CRM actions in production.

Check `node scripts/check-staff-ui-browser.mjs` and existing fulfillment/Admin browser checks after building. See `docs/STAFF_CRM_UI.md` for routes, source files and verification scope.

## Manager area

`Shell area="manager"` renders the Staff frame (`.ws.ws-staff.ws-manager`): the same header (logo, notifications, `AppearanceSwitch`, language, profile), the labelled sidebar with its mobile drawer, Staff tokens and the shared light/dark preference. Only the sidebar items differ: dashboard, reports, order queue, price approvals, delivery, refunds, schedule, robots and alerts (count of open alerts), customer reviews, catalog, price list. Manager-only routes stay behind `RequireStaff manager`; a Staff account keeps its four destinations.
- Manager screens reuse the Staff blocks (`panel`, `Kpi` with `staff-kpis`, `staff-period`, `staff-chart-data`, workshop chips) through `pages/staff/managerKit.tsx` (`Panel`, `Chip`, `StateChip`, `LevelChip`, `Period`, `LineChart`). `components/ws/manager-ui.css` holds the few Manager-only blocks (`mgr-*`) and uses theme tokens only, so dark mode follows `staff-theme.css`. Robot state and alert level are chips with an icon and a word; every chart has its numbers in a table.
- Data: `services/managerOps.ts`: `/manager/dashboard`, `/manager/reports` and its Excel/PDF export (through `apiFile` in `services/api.ts`, Bearer fetch), robot status, health, runs, process compliance, alerts and the alert catalogue, job detail, events, incidents, quality, and review moderation. Pages: `ManagerDashboard.tsx`, `Reports.tsx` (`/staff/reports`), `Robots.tsx` (`/staff/robots`, `?job=<id>` opens a job), `Reviews.tsx` (`/staff/reviews`).
- Alert titles and actions (`title_vi`, `action_vi`, `headline_vi`), process steps and quality advice come from the backend in Vietnamese and are shown as received. A Manager may close a red (level 4) alert only after a confirmation; the E-Stop reminder stays. Red catalogue entries keep e-mail, stay on and keep technicians.
- Check with `node scripts/check-manager-browser.mjs` after building (set `TECH_BROWSER_PATH` outside Windows; `MANAGER_SHOTS=<dir>` saves screenshots).
- Robots are given to technicians for good (migration 0032): `RobotAssignments.tsx` on `/staff/robots` (`PUT` / `DELETE /manager/robots/{id}/technician`; `409 ROBOT_HAS_ACTIVE_JOBS` lists the job ids to move first). The schedule books a **technician** and a time; the robot is optional ("Let the technician choose") and only one of theirs; the technician picks it on the workstation screen. The calendar's columns are technicians, a job without a robot shows "No robot chosen" with a dashed edge, and a technician without a robot in service is locked with a link to Robots. Robot cards show a red "REAL on for job X until hh:mm" from `robot-status` `real_enabled` (switched on only at the workstation). `checkSlot` in `scheduleMath.ts` mirrors the backend (`TECHNICIAN_HAS_NO_ROBOT`, `ROBOT_NOT_ASSIGNED`, no robot of theirs free); the pen fit stays the backend's (`ROBOT_NOT_SUITABLE`).
