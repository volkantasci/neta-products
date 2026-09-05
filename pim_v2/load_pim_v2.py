# -*- coding: utf-8 -*-
"""pim_v2 yukleyici (yeni mimari: BASE_00 -> BASE_10 -> <Kategori>).
Odoo shell icinde calisir:

    docker cp pim_v2 <web>:/tmp/pim_v2
    docker exec -i <web> odoo shell -c /etc/odoo/odoo.conf -d odoo < pim_v2/load_pim_v2.py

Idempotent: kayit varsa atlar/guncellemez, ayni kod tekrar yuklenmez.
"""
import glob
import json

SRC = "/tmp/pim_v2/*_pim_v2.json"
MODEL = "product.template"

BASE = [("BASE_00_MECHANICAL", None), ("BASE_10_ELECTRICAL", "BASE_00_MECHANICAL")]


def groups(env):
    out = {}
    for g in env["attribute.group"].search([]):
        try:
            nm = g.with_context(lang="tr_TR").name or g.name
        except Exception:
            nm = g.name
        out[nm] = g
    return out


def ensure_sets(env):
    model = env.ref("product.model_product_template")
    made = {}
    for name, parent in BASE:
        s = env["attribute.set"].search(
            [("name", "=", name), ("model_id", "=", model.id)], limit=1)
        if not s:
            vals = {"name": name, "model_id": model.id}
            if parent:
                vals["parent_id"] = made[parent].id
            s = env["attribute.set"].create(vals)
            print("SET", name)
        made[name] = s
    return model, made


def ensure_attrs(env, model, grps, defs, set_rec):
    A = env["attribute.attribute"]
    OPT = env["attribute.option"]
    for d in defs:
        rec = A.search([]).filtered(lambda a, n=d["name"]: a.name == n)[:1]
        if not rec:
            rec = A.create({
                "nature": "custom", "name": d["name"],
                "field_description": d["label"],
                "attribute_type": d["type"], "model_id": model.id,
                "attribute_group_id": grps[d["group"]].id,
                "sequence": 10, "serialized": False})
            print("ATTR", d["name"])
        for opt in d.get("options") or []:
            if not OPT.search([("attribute_id", "=", rec.id),
                               ("name", "=", opt)], limit=1):
                OPT.create({"attribute_id": rec.id, "name": opt})
        if set_rec.id not in rec.attribute_set_ids.ids:
            rec.attribute_set_ids = [(4, set_rec.id)]


def main(env):
    model, base = ensure_sets(env)
    grps = groups(env)
    PT = env["product.template"]
    PC = env["product.category"]
    OPT = env["attribute.option"]
    A = env["attribute.attribute"]
    n_p = 0
    for path in sorted(glob.glob(SRC)):
        d = json.load(open(path, encoding="utf-8"))
        cn = d["meta"]["category"]
        sd = d["attribute_sets"][0]
        parent = base.get(sd["parent"]) if sd.get("parent") else None
        s = env["attribute.set"].search(
            [("name", "=", cn), ("model_id", "=", model.id)], limit=1)
        if not s:
            s = env["attribute.set"].create(
                {"name": cn, "model_id": model.id,
                 "parent_id": parent.id if parent else False})
            print("SET", cn)
        elif parent and s.parent_id != parent:
            s.parent_id = parent.id
        ensure_attrs(env, model, grps, d["attributes"], s)
        cat = PC.search([("name", "=", cn)], limit=1)
        if not cat:
            cat = PC.create({"name": cn, "attribute_set_id": s.id})
        for p in d["products"]:
            if PT.search([("default_code", "=", p["code"])], limit=1):
                continue
            tmpl = PT.create({"name": p["name"], "default_code": p["code"],
                              "categ_id": cat.id, "attribute_set_id": s.id,
                              "list_price": p["list_price"] or 0.0,
                              "weight": p["weight"] or 0.0, "type": "consu"})
            vals = {}
            for tech, (typ, val) in p["values"].items():
                a = A.search([]).filtered(
                    lambda x, n=tech: x.name == n)[:1]
                if not a or tech not in tmpl._fields or val in (None, ""):
                    continue
                if typ in ("float", "integer", "char", "text"):
                    vals[tech] = val
                elif typ == "select":
                    o = OPT.search([("attribute_id", "=", a.id),
                                    ("name", "=", val)], limit=1) or OPT.create(
                        {"attribute_id": a.id, "name": val})
                    vals[tech] = o.id
                elif typ == "multiselect":
                    ids = []
                    for nm in val or []:
                        o = OPT.search([("attribute_id", "=", a.id),
                                        ("name", "=", nm)], limit=1) or OPT.create(
                            {"attribute_id": a.id, "name": nm})
                        ids.append(o.id)
                    if ids:
                        vals[tech] = [(6, 0, ids)]
            if vals:
                tmpl.write(vals)
            for pr in p.get("extra_prices") or []:
                cur = env["res.currency"].with_context(active_test=False).search(
                    [("name", "=", pr["currency"])], limit=1)
                if not cur:
                    continue
                pl = env["product.pricelist"].search(
                    [("currency_id", "=", cur.id),
                     ("name", "=", "Neta Katalog")], limit=1) or \
                    env["product.pricelist"].create(
                        {"name": "Neta Katalog", "currency_id": cur.id})
                env["product.pricelist.item"].create(
                    {"pricelist_id": pl.id, "applied_on": "1_product",
                     "product_tmpl_id": tmpl.id, "compute_price": "fixed",
                     "fixed_price": pr["price"]})
            n_p += 1
        env.cr.commit()
        print(path, "ok")
    print("PRODUCTS_CREATED=", n_p)


main(env)  # noqa: F821
