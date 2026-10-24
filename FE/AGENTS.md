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

- Put `<LanguageToggle className="..." />` right after every `<ThemeToggle ... />` (any header or top bar).
- Staff and technician pages must render their rail (`StaffRail` / `TechRail`).
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

- Customer, workshop (Staff, Manager) and technician data all come from the API. The localStorage store in `src/store/store.ts` only keeps the signed-in user and profile.


## Customer orders come from the API

The customer flow (create, submit, privacy, quotation, deposit) talks to the backend through `src/services/orders.ts`
(contract in `BE/docs/FE_API_GUIDE.md`, Swagger at `/docs`). Build the UI from what the API accepts and returns: when the
backend gains a field, add it to the UI; do not keep fields the backend does not have.

- A draft is a real order with `order_status = DRAFT`. `CreateOrder.tsx` creates it on the first thing worth saving and
  autosaves every change through `hooks/useSaveQueue.ts`. Drafts list under **Account > Drafts** (`GET /orders?status=DRAFT`).
- Catalog (paper, pen, ink, templates) and the price estimate come from the API. Do not hard-code them.
- `/orders/:id/review` is the order page: it renders by `order_status` and polls while the status moves on its own.
- Deposit (`pages/order/Deposit.tsx`) offers the gateways `GET /payments/gateways` marks `enabled` (VNPay, MoMo, payOS).
  `mode = MOCK` settles with the simulated buttons and keeps the "simulated payment" notice; `SANDBOX` / `LIVE` send the
  customer to `pay_url`, and the gateway brings them back to `/payment/result` (`PaymentResult.tsx`), which polls the order
  and never trusts the gateway's query parameters. `vercel.json` rewrites deep links to `index.html` so that page loads.
- Result, final payment, tracking and shipping have no API yet (backend phase 4), so they have no pages. Add them when they do.
- The workshop side lives in `src/pages/staff/` and `src/services/workshop.ts`: dashboard, `Workbench` (intake, sketch, quotation, chat),
  `Approvals`, `Schedule` and `Catalog` (Manager only; materials, ink colors, stock, compatibility, templates, robots, price list via `services/manage.ts`). Role gate is `RequireStaff` (Staff or Manager; Admin has no access to orders).
- Errors from the API go through `orderErrorKey` / `errText` (`services/orders.ts`): known codes have translated text, any other code shows the backend's own message. Add a code to `ERROR_KEYS` and `err.*` when you want it translated.
- Workshop screens (Staff, Manager, Technician) all render inside `components/ws/Shell.tsx`: the icon pill, the header and a language button. Their look is `components/ws/ws.css` (generated from the Figma-based design, everything under `.ws`, light only, no theme toggle) and `workshop.css`; the accent is the `--acc` variable. Use the shared pieces in `components/ws/parts.tsx` and `charts.tsx` before adding new markup.
- The order chat (`components/ui/Chat.tsx`) is shared by the customer and the workshop, and is reached only through the floating
  `components/ui/ChatDock.tsx`: `side="customer"` in `App.tsx`, `side="workshop"` in `Shell.tsx` (Staff, Manager). The list and badge come from
  `services/chat.ts` (`/me/conversations`, `/workshop/conversations`, `.../unread-count`). Opening the customer chat from an order sends
  an `ORDER_CARD` message (the backend returns the same card within 10 minutes); both sides render it from `order_card`.
  Read only only when the order is `REJECTED` or `CANCELLED` (a `COMPLETED` order stays open for complaints), or for a Staff who has not
  claimed the order. Contract: `BE/docs/FE_API_GUIDE.md` section 5.4.
- The technician screens (`src/pages/tech/`) run on the API (`services/technician.ts`): jobs, the job screen (`JobDetail` and its workflow, preparation, events and photo parts, also reached at `/tech/preview/:id` and `/tech/qc/:id`). Details in `docs/TECHNICAL_STAFF_INTEGRATION.md`. `sim.ts` and `SimCanvas.tsx` are the old text-based arm simulation, not used by any screen.


## Account area

Everything that belongs to the signed-in user lives under `/account` (`src/pages/account/`): profile, preferences
(theme, language), order history, drafts, payment methods. The top bar and the landing page are for browsing only:
no order history, drafts or cart there. A new user-owned feature gets a section in `Account.tsx`, not a new top bar item.
The avatar in the top bar opens `/account`; sign out lives in the account navigation.
