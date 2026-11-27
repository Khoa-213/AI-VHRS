# Font registry (writing templates built from outline fonts)

Every outline font used by `outline:` templates is stored in Supabase Storage under `fonts/<slug>/` (font file, `LICENSE.txt`,
`<font>.glyphs.json`, `preview.png`) by `scripts/add_outline_font.py`, which refuses a font whose licence file is not an allowed open
licence or that lacks any Vietnamese letter. Edit this table by hand when a font is added. "Checked" means the full Vietnamese
character set thinned to strokes and the preview was inspected by a person; it does NOT mean the font was written on paper.

| Template code | Font | Licence | Source | Added | Checked |
|---|---|---|---|---|---|
| PLAYPEN_SANS | Playpen Sans (variable, default weight) | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/playpensans | 2026-10-23 | preview only |
| PANGOLIN | Pangolin Regular | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/pangolin | 2026-10-23 | preview only |
| PATRICK_HAND | Patrick Hand Regular | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/patrickhand | 2026-10-23 | preview only |
| MALI_LIGHT | Mali Light | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/mali | 2026-10-23 | preview only |
| ITIM | Itim Regular | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/itim | 2026-11-27 | preview only |
| MERIENDA | Merienda Regular (static) | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/merienda | 2026-11-27 | preview only |
| DANCING_SCRIPT | Dancing Script Regular (static) | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/dancingscript | 2026-11-27 | preview only |
| PACIFICO | Pacifico Regular | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/pacifico | 2026-11-27 | preview only |
| ALLURA | Allura Regular | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/allura | 2026-11-27 | preview only; all-capitals text is hard to read (script capitals) |
| GREAT_VIBES | Great Vibes Regular | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/greatvibes | 2026-11-27 | preview only; small lower case (marks sit close), all-capitals hard to read |
| MS_MADI | Ms Madi Regular | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/msmadi | 2026-11-27 | preview only; all-capitals text is hard to read (script capitals) |
| HERSHEY_* (4) | Hershey single-line fonts via `Hershey-Fonts` 2.1.0 | public domain | PyPI Hershey-Fonts | earlier | in use |

Evaluated and NOT added: Playwrite VN (OFL, cursive joined letters designed for Vietnamese schools): the loops are too small to
thin cleanly at 7 mm letter height. It may be worth a retest at larger sizes.
The backend's own DejaVu Sans (`DejaVu-LICENSE.txt`) is used only by the PDF generator and the tests.
