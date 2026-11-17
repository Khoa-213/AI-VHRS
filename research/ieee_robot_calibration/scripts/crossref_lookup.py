"""Look up bibliographic metadata on Crossref (public API, no personal data sent). Usage: python scripts/crossref_lookup.py"""
import json, sys, urllib.parse, urllib.request
Q = sys.argv[1:] 
def q(text):
    u = "https://api.crossref.org/works?rows=3&query.bibliographic=" + urllib.parse.quote(text)
    req = urllib.request.Request(u, headers={"User-Agent": "research-bib-check/1.0"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    for it in d["message"]["items"]:
        au = ", ".join((a.get("given", "") + " " + a.get("family", "")).strip() for a in it.get("author", [])[:6])
        yr = (it.get("issued", {}).get("date-parts") or [[None]])[0][0]
        print(f"  [{yr}] {it.get('title', [''])[0][:110]} | {au} | {it.get('container-title', [''])[0] if it.get('container-title') else ''} | "
              f"vol {it.get('volume','')} iss {it.get('issue','')} pp {it.get('page','')} art {it.get('article-number','')} | doi {it.get('DOI')}")
for t in Q:
    print(t); q(t)
