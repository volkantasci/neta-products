# -*- coding: utf-8 -*-
"""PIM JSON -> Odoo (attribute_set / product_attribute_set) yukleyici.

Dizindeki TUM kategori JSON'larini isler. odoo shell icinde calisir:

    docker cp pim test-odoo-web-1:/tmp/
    docker exec -i test-odoo-web-1 odoo shell -c /etc/odoo/odoo.conf \
        -d odoo --stop-after-init < pim/load_pim_json.py

- /tmp/pim/*_pim.json varsa hepsini (alfabetik) isler; yoksa /tmp/pim.json.
- Fiyat standardi: JSON'da native.prices = [{"currency": "EUR", "price": ...},
  ...] seklinde doviz bazli fiyat listesi; sirket para birimi EUR'a ayarlanir
  (list_price EUR cinsindendir) ve her doviz icin bir fiyatlama listesi
  (product.pricelist) olusturulup urun bazli sabit kalem yazilir.
- Idempotentdir: kayitlari key/isim ile arar, yoksa olusturur, varsa
  gunceller. Kategoriden cikmis (bayat) urunleri raporlar ve siler.
"""

import glob
import json
import os

MODEL = "product.template"
report_total = {"sets": 0, "groups": 0, "attributes": 0, "options": 0,
                "products": 0, "updated": 0, "stale_deleted": 0,
                "pricelist_items": 0}

_pl_cache = {}  # currency adi -> product.pricelist kaydi


def bootstrap_currency(specs):
    """Fiyat dovizlerini aktiflestirir; sirket PB'sini EUR yapar."""
    currencies = {pp["currency"]
                  for sp in specs
                  for pv in sp["product_values"].values()
                  for pp in (pv["native"].get("prices") or [])}
    currencies.add("EUR")  # sirket PB + list_price dovizi
    for name in sorted(currencies):
        cur = env["res.currency"].with_context(
            active_test=False).search([("name", "=", name)], limit=1)
        if not cur:
            print(f"!! {name} para birimi kaydi bulunamadi")
            continue
        if not cur.active:
            cur.write({"active": True})
            print(f"{name} para birimi aktiflestirildi")
    company = env["res.company"].search([], limit=1)
    eur = env["res.currency"].search([("name", "=", "EUR")], limit=1)
    if eur and company.currency_id.id != eur.id:
        company.write({"currency_id": eur.id})
        print(f"Sirket para birimi -> EUR (id {company.id})")
    else:
        print("Sirket para birimi zaten EUR")


def ensure_pricelist(currency_name):
    """Doviz basina bir 'Neta Katalog' fiyat listesi olusturur/dondurur."""
    if currency_name in _pl_cache:
        return _pl_cache[currency_name]
    cur = env["res.currency"].with_context(active_test=False).search(
        [("name", "=", currency_name)], limit=1)
    pl = env["product.pricelist"].search(
        [("currency_id", "=", cur.id), ("name", "=", "Neta Katalog")],
        limit=1)
    if not pl:
        pl = env["product.pricelist"].create({
            "name": "Neta Katalog",
            "currency_id": cur.id,
        })
        print(f"Fiyat listesi olusturuldu: {pl.name} ({currency_name})")
    _pl_cache[currency_name] = pl
    return pl


def sync_prices(tmpl, prices):
    """Urunun doviz bazli fiyatlama listesi kalemlerini gunceller."""
    for pp in prices or []:
        pl = ensure_pricelist(pp["currency"])
        item = env["product.pricelist.item"].search(
            [("pricelist_id", "=", pl.id),
             ("product_tmpl_id", "=", tmpl.id)], limit=1)
        if item:
            item.write({"fixed_price": pp["price"],
                        "compute_price": "fixed"})
        else:
            env["product.pricelist.item"].create({
                "pricelist_id": pl.id,
                "product_tmpl_id": tmpl.id,
                "applied_on": "1_product",
                "compute_price": "fixed",
                "fixed_price": pp["price"],
            })
        report_total["pricelist_items"] += 1


def import_file(spec, owners):
    """Tek bir kategori JSON'unu import eder."""
    report = {"sets": 0, "groups": 0, "attributes": 0, "options": 0,
              "products": 0, "updated": 0, "conflicts": 0}
    meta = spec["meta"]
    model_id = env["ir.model"].search([("model", "=", MODEL)]).id
    Template = env[MODEL]

    # 1) Nitelik gruplari
    group_ids = {}
    for g in spec["attribute_groups"]:
        rec = env["attribute.group"].search(
            [("name", "=", g["name"]), ("model_id", "=", model_id)])
        vals = {"name": g["name"], "sequence": g["sequence"],
                "model_id": model_id}
        if rec:
            rec.write(vals)
        else:
            rec = env["attribute.group"].create(vals)
            report["groups"] += 1
        group_ids[g["key"]] = rec.id

    # 2) Nitelik setleri (JSON ustten alta sirali)
    set_ids = {}
    for s in spec["attribute_sets"]:
        rec = env["attribute.set"].search(
            [("name", "=", s["name"]), ("model_id", "=", model_id)])
        if not rec:
            rec = env["attribute.set"].create({
                "name": s["name"],
                "model_id": model_id,
                "parent_id": set_ids.get(s["parent_key"]),
            })
            report["sets"] += 1
        set_ids[s["key"]] = rec.id

    # 3) Nitelikler + secenekler
    option_ids = {}
    for a in spec["attributes"]:
        if a["nature"] == "native":
            fld = env["ir.model.fields"].search(
                [("model", "=", MODEL), ("name", "=", a["native_field"])])
            vals = {
                "nature": "native",
                "field_id": fld.id,
                "attribute_type": {"int": "integer"}.get(
                    a["attribute_type"], a["attribute_type"]),
                "attribute_group_id": group_ids[a["group_key"]],
                "attribute_set_ids": [
                    (6, 0, [set_ids[k] for k in a["set_keys"]])],
            }
            rec = env["attribute.attribute"].search(
                [("nature", "=", "native"), ("field_id", "=", fld.id)])
        else:
            vals = {
                "nature": "custom",
                "name": a["name"],
                "field_description": a["field_description"],
                "attribute_type": {"int": "integer"}.get(
                    a["attribute_type"], a["attribute_type"]),
                "attribute_group_id": group_ids[a["group_key"]],
                "attribute_set_ids": [
                    (6, 0, [set_ids[k] for k in a["set_keys"]])],
                "model_id": model_id,
                "serialized": a["serialized"],
            }
            if a.get("widget"):
                vals["widget"] = a["widget"]
            rec = env["attribute.attribute"].search([("name", "=", a["name"])])
        if rec:
            rec.write({k: v for k, v in vals.items() if k != "attribute_type"})
        else:
            rec = env["attribute.attribute"].create(vals)
            report["attributes"] += 1

        for seq, opt_name in enumerate(a.get("options") or [], start=1):
            opt = env["attribute.option"].search(
                [("name", "=", opt_name), ("attribute_id", "=", rec.id)])
            if not opt:
                opt = env["attribute.option"].create(
                    {"name": opt_name, "attribute_id": rec.id,
                     "sequence": seq})
                report["options"] += 1
            option_ids[(a["key"], opt_name)] = opt.id

    # 4) Urun kategorisi: kok seviyede (Goods vb. altina baglanmaz)
    pc = spec["product_category"]
    categ = env["product.category"].search([("name", "=", pc["name"])])
    vals = {"parent_id": False}  # kok seviye kategori zorunlulugu
    if not categ:
        categ = env["product.category"].create({
            "name": pc["name"],
            "parent_id": False,
            "attribute_set_id": set_ids[pc["default_attribute_set_key"]],
        })
    elif categ.parent_id or not categ.attribute_set_id:
        if not categ.attribute_set_id:
            vals["attribute_set_id"] = set_ids[
                pc["default_attribute_set_key"]]
        categ.write(vals)

    # 5) Urunler + nitelik degerleri
    def convert(key, value):
        a = next(x for x in spec["attributes"] if x["key"] == key)
        if a["attribute_type"] == "select":
            return option_ids[(key, value)]
        if a["attribute_type"] == "multiselect":
            return [(6, 0, [option_ids[(key, o)] for o in value])]
        return value

    family_values = spec["family_values"]
    conflicts = []
    for code, pv in spec["product_values"].items():
        # Ayni kod birden fazla kategoride listelenmis ise ilk dosya
        # (alfabetik) sahiplenir; diger dosyalar atlar.
        if code in owners and owners[code] != meta["category_no"]:
            conflicts.append(code)
            continue
        tmpl = Template.search([("default_code", "=", code)])
        native = pv["native"]
        prices = native.get("prices") or []
        eur_price = next((pp["price"] for pp in prices
                          if pp["currency"] == "EUR"), None)
        vals = {
            "name": native["name"],
            "default_code": code,
            "categ_id": categ.id,
            "attribute_set_id": set_ids[pv["attribute_set_key"]],
        }
        if eur_price is not None:
            vals["list_price"] = eur_price
        else:
            vals["list_price"] = 0.0  # EUR fiyatsiz; Odoo varsayilani 1.0 yerine

        merged = dict(family_values.get(pv["attribute_set_key"], {}))
        merged.update(pv["values"])
        for key, value in merged.items():
            if key == "weight":
                vals["weight"] = value  # native alan
            else:
                vals[next(x["name"] for x in spec["attributes"]
                          if x["key"] == key)] = convert(key, value)

        if tmpl:
            tmpl.write(vals)
            report["updated"] += 1
        else:
            tmpl = Template.create(vals)
            report["products"] += 1
        sync_prices(tmpl, prices)

    print(f"[{meta['category_no']}] {meta['category_tr']}: "
          f"set+{report['sets']} grup+{report['groups']} "
          f"nitelik+{report['attributes']} secenek+{report['options']} "
          f"urun+{report['products']} guncellenen={report['updated']}")
    if conflicts:
        for code in conflicts:
            print(f"    Atlandi: {code} (sahip kategori: "
                  f"{owners[code]})")
    return report


def cleanup_stale(specs):
    """Kategori JSON'larinda artik bulunmayan urunleri siler."""
    all_codes = {code for sp in specs for code in sp["product_values"]}
    categ_names = [sp["product_category"]["name"] for sp in specs]
    categs = env["product.category"].search([("name", "in", categ_names)])
    stale = env[MODEL].search([
        ("categ_id", "in", categs.ids),
        ("default_code", "not in", list(all_codes)),
    ])
    if stale:
        print("Bayat urunler siliniyor:", stale.mapped("default_code"))
        stale.unlink()
        report_total["stale_deleted"] += len(stale)


def main():
    paths = sorted(glob.glob("/tmp/pim/*_pim.json"))
    if not paths and os.path.exists("/tmp/pim.json"):
        paths = ["/tmp/pim.json"]
    if not paths:
        print("!! Yuklenecek JSON bulunamadi")
        return
    print("Isleme alinan dosyalar:", [os.path.basename(p) for p in paths])

    specs = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            specs.append(json.load(f))

    # kod -> sahip kategori (ilk dosya kazanir)
    owners = {}
    for sp in specs:
        for code in sp["product_values"]:
            owners.setdefault(code, sp["meta"]["category_no"])

    bootstrap_currency(specs)

    for spec in specs:
        try:
            rep = import_file(spec, owners)
            for k in ("sets", "groups", "attributes", "options",
                      "products", "updated"):
                report_total[k] += rep[k]
            env.cr.commit()
        except Exception as e:  # noqa: BLE001
            env.cr.rollback()
            print(f"!! HATA ({spec['meta']['category_no']}): "
                  f"{type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    cleanup_stale(specs)
    env.cr.commit()

    print("\n=== GENEL RAPOR ===")
    print(json.dumps(report_total, indent=1))
    print("\nUYARI: Yeni x_ alanlari yalnizca bu shell surecinin registry'ine "
          "yuklenir. Calisan web sunucusuna islemesi icin sunu calistirin:")
    print("    docker restart test-odoo-web-1")


main()
