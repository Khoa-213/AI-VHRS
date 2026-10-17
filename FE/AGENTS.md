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
- Customer data comes from the API. Staff and technician screens still use the localStorage mock in `src/store/store.ts`.
  The GHN client in `src/services/ghn.ts` talks to a backend proxy, never directly to GHN with a token.

## Customer orders come from the API

The customer flow (create, submit, privacy, quotation, deposit) talks to the backend through `src/services/orders.ts`
(contract in `BE/docs/FE_API_GUIDE.md`, Swagger at `/docs`). Build the UI from what the API accepts and returns: when the
backend gains a field, add it to the UI; do not keep fields the backend does not have.

- A draft is a real order with `order_status = DRAFT`. `CreateOrder.tsx` creates it on the first thing worth saving and
  autosaves every change through `hooks/useSaveQueue.ts`. Drafts list under **Account > Drafts** (`GET /orders?status=DRAFT`).
- Catalog (paper, pen, ink, templates) and the price estimate come from the API. Do not hard-code them.
- `/orders/:id/review` is the order page: it renders by `order_status` and polls while the status moves on its own.
- Deposit uses the **mock** gateway. Keep the "simulated payment" notice while the backend returns `mode = MOCK`.
- Result, final payment and tracking have no API yet (backend phase 4), so they have no pages. Add them when they do.
- Staff and technician screens still read the local mock in `src/store/store.ts`. Wire them one by one and delete their mock data as you go.

## Account area

Everything that belongs to the signed-in user lives under `/account` (`src/pages/account/`): profile, preferences
(theme, language), order history, drafts, payment methods. The top bar and the landing page are for browsing only:
no order history, drafts or cart there. A new user-owned feature gets a section in `Account.tsx`, not a new top bar item.
The avatar in the top bar opens `/account`; sign out lives in the account navigation.
