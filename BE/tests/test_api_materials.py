"""Material choice: the public suggestion list (paper -> compatible pens -> inks) and 'let the workshop choose' that
keeps whatever the customer already picked. Real database; compatibility rows are the test catalog's own."""
from tests.conftest import auth
from tests.test_api_orders import API, _sql
from tests.test_api_workshop import (W, _err, _ot3, cust, manager, policy, staff, store, wcat)  # noqa: F401


def _suggest_order(client, cust, staff_h, wcat, **fixed):
    """Customer chose 'workshop suggests' and (optionally) some materials; the order is accepted with a final sketch."""
    oid = _ot3(client, cust, wcat, suggest=True, submit=False)
    if fixed:
        r = client.patch(f"{API}/orders/{oid}", headers=cust, json=fixed)
        assert r.status_code == 200, r.text
    assert client.post(f"{API}/orders/{oid}/submit", headers=cust, json={"terms_accepted": True}).status_code == 200
    assert client.post(f"{W}/orders/{oid}/accept", headers=staff_h, json={}).status_code == 200
    v = client.post(f"{W}/orders/{oid}/sketches/generate", headers=staff_h, json={"paper_size": "A5"}).json()["version"]
    assert client.post(f"{W}/orders/{oid}/sketches/{v}/finalize", headers=staff_h).status_code == 200
    return oid


def _quote(client, sh, oid, options=None):
    return client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={"options": options} if options is not None else {})


# ---- GET /catalog/suggest-materials -------------------------------------------------------------------
def test_suggestions_list_compatible_pens_with_their_inks(client, wcat):
    r = client.get(f"{API}/catalog/suggest-materials", params={"paper_type_id": wcat["paper"]})   # no login needed
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["paper"]["id"] == wcat["paper"]
    pens = {p["id"]: p for p in d["pens"]}
    assert {wcat["gel"], wcat["fountain"]} <= set(pens)                      # both are compatible with this paper
    assert [i["id"] for i in pens[wcat["gel"]]["inks"]] == [wcat["gel_ink"]]
    assert all(i["pen_type_id"] == p["id"] for p in d["pens"] for i in p["inks"])    # inks belong to their pen (BR-05)
    glossy = client.get(f"{API}/catalog/suggest-materials", params={"paper_type_id": wcat["gloss"]}).json()
    ids = {p["id"] for p in glossy["pens"]}
    assert wcat["gel"] in ids and wcat["fountain"] not in ids                # fountain ink does not hold on glossy paper


def test_suggestions_skip_pens_without_ink_and_inactive_papers(client, wcat):
    _sql("update ink_colors set is_active=false where id=:i returning 1", i=wcat["fountain_ink"])
    try:
        ids = {p["id"] for p in client.get(f"{API}/catalog/suggest-materials", params={"paper_type_id": wcat["paper"]}).json()["pens"]}
        assert wcat["fountain"] not in ids and wcat["gel"] in ids
    finally:
        _sql("update ink_colors set is_active=true where id=:i returning 1", i=wcat["fountain_ink"])
    _sql("update paper_types set is_active=false where id=:i returning 1", i=wcat["gloss"])
    try:
        r = client.get(f"{API}/catalog/suggest-materials", params={"paper_type_id": wcat["gloss"]})
        assert r.status_code == 404 and _err(r) == "PAPER_NOT_FOUND"
    finally:
        _sql("update paper_types set is_active=true where id=:i returning 1", i=wcat["gloss"])
    assert client.get(f"{API}/catalog/suggest-materials", params={"paper_type_id": 999999999}).status_code == 404
    assert client.get(f"{API}/catalog/suggest-materials").status_code == 422
    assert client.get(f"{API}/catalog/suggest-materials", params={"paper_type_id": 0}).status_code == 422


# ---- 'let the workshop choose' keeps the customer's picks ---------------------------------------------
def test_workshop_fills_only_what_the_customer_left_empty(client, cust, staff, wcat):
    sh = staff[0]
    oid = _suggest_order(client, cust, sh, wcat, paper_type_id=wcat["paper"])           # the customer fixed the paper only
    # Staff offer two pens on that paper without repeating the paper
    opts = [{"pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]},
            {"pen_type_id": wcat["fountain"], "ink_color_id": wcat["fountain_ink"]}]
    r = _quote(client, sh, oid, opts)
    assert r.status_code == 201, r.text
    q = r.json()
    assert len(q["options"]) == 2 and all(o["paper"] == "Giay test A5" for o in q["options"])
    assert {li["paper_type_id"] for li in q["line_items"]} == {wcat["paper"]}


def test_staff_cannot_override_a_customer_choice_or_break_compatibility(client, cust, staff, wcat):
    sh = staff[0]
    oid = _suggest_order(client, cust, sh, wcat, paper_type_id=wcat["gloss"])
    other_paper = [{"paper_type_id": wcat["paper"], "pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}]
    r = _quote(client, sh, oid, other_paper)
    assert r.status_code == 422 and _err(r) == "MATERIAL_LOCKED_BY_CUSTOMER"
    assert r.json()["error"]["details"] == {"option": 1, "field": "paper_type_id"}
    bad_pen = [{"pen_type_id": wcat["fountain"], "ink_color_id": wcat["fountain_ink"]}]    # glossy + fountain pen: no
    r = _quote(client, sh, oid, bad_pen)
    assert r.status_code == 422 and _err(r) == "INVALID_MATERIALS" and "không tương thích" in r.json()["error"]["message"]
    r = _quote(client, sh, oid, [{"pen_type_id": wcat["gel"]}])                              # ink still missing
    assert r.status_code == 422 and _err(r) == "INVALID_MATERIALS" and "mực" in r.json()["error"]["message"]
    r = _quote(client, sh, oid, [{"ink_color_id": wcat["gel_ink"]}])                         # pen missing
    assert r.status_code == 422 and "bút" in r.json()["error"]["message"]
    assert _err(_quote(client, sh, oid)) == "OPTIONS_REQUIRED"
    assert _err(_quote(client, sh, oid, [{}, {}, {}, {}])) == "OPTIONS_REQUIRED"
    ok = _quote(client, sh, oid, [{"pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]}])
    assert ok.status_code == 201, ok.text


def test_a_pen_chosen_by_the_customer_stays_and_staff_pick_paper_and_ink(client, cust, staff, wcat):
    sh = staff[0]
    oid = _suggest_order(client, cust, sh, wcat, pen_type_id=wcat["gel"])
    r = _quote(client, sh, oid, [{"paper_type_id": wcat["paper"], "ink_color_id": wcat["gel_ink"]},
                                 {"paper_type_id": wcat["gloss"], "ink_color_id": wcat["gel_ink"]}])
    assert r.status_code == 201, r.text
    assert {o["pen"] for o in r.json()["options"]} == {"But gel test"}
    swapped = _quote(client, sh, oid, [{"pen_type_id": wcat["fountain"], "paper_type_id": wcat["paper"],
                                        "ink_color_id": wcat["fountain_ink"]}])
    assert swapped.status_code == 422 and _err(swapped) == "MATERIAL_LOCKED_BY_CUSTOMER"


def test_everything_chosen_by_the_customer_needs_no_options(client, cust, staff, wcat):
    sh = staff[0]
    oid = _suggest_order(client, cust, sh, wcat, paper_type_id=wcat["paper"], pen_type_id=wcat["gel"],
                         ink_color_id=wcat["gel_ink"])
    r = _quote(client, sh, oid)                                                           # nothing left to suggest
    assert r.status_code == 201, r.text
    assert len(r.json()["options"]) == 1 and r.json()["options"][0]["pen"] == "But gel test"


def test_the_customer_approves_one_option_and_the_order_keeps_the_fixed_paper(client, cust, staff, wcat):
    sh = staff[0]
    oid = _suggest_order(client, cust, sh, wcat, paper_type_id=wcat["paper"])
    q = _quote(client, sh, oid, [{"pen_type_id": wcat["gel"], "ink_color_id": wcat["gel_ink"]},
                                 {"pen_type_id": wcat["fountain"], "ink_color_id": wcat["fountain_ink"]}]).json()
    assert client.post(f"{W}/quotations/{q['id']}/send", headers=sh).status_code == 200
    client.post(f"{API}/orders/{oid}/privacy", headers=cust, json={"accept": True})
    r = client.post(f"{API}/orders/{oid}/quotation/approve", headers=cust, json={"option": 2})
    d = r.json()
    assert r.status_code == 200 and d["paper_type_id"] == wcat["paper"] and d["pen_type_id"] == wcat["fountain"]


# ---- what Staff can still offer ----------------------------------------------------------------------
def test_staff_see_the_remaining_combinations(client, cust, staff, manager, wcat):
    sh = staff[0]
    oid = _suggest_order(client, cust, sh, wcat, paper_type_id=wcat["gloss"])
    d = client.get(f"{W}/orders/{oid}/material-suggestions", headers=sh).json()
    assert d["suggest_enabled"] is True and d["fixed"]["paper_type_id"] == wcat["gloss"] and d["fixed"]["paper_type_id_name"]
    assert d["fixed"]["pen_type_id"] is None
    pens = {c["pen_type_id"] for c in d["combos"]}
    assert wcat["gel"] in pens and wcat["fountain"] not in pens                          # only compatible pens, glossy paper kept
    assert {c["paper_type_id"] for c in d["combos"]} == {wcat["gloss"]} and d["total"] == len(d["combos"])
    open_ = _suggest_order(client, cust, sh, wcat)                                       # nothing fixed: every compatible combo
    free = client.get(f"{W}/orders/{open_}/material-suggestions", headers=sh).json()
    assert {wcat["paper"], wcat["gloss"]} <= {c["paper_type_id"] for c in free["combos"]}
    assert client.get(f"{W}/orders/{oid}/material-suggestions", headers=manager[0]).status_code == 200      # read-only for Manager
    assert client.get(f"{W}/orders/{oid}/material-suggestions", headers=auth(client, "CUSTOMER")).status_code == 403
    other_staff = auth(client, "STAFF")
    assert client.get(f"{W}/orders/{oid}/material-suggestions", headers=other_staff).status_code == 404
