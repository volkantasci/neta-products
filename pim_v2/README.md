# pim_v2 — yeni mimari katalog

Bu dizin, `pim/` + `categories/` içindeki **eski mimarinin** (346 set,
kategori-önekli `x_pump_*` alanlar) yerine geçen **yeni mimari** yükleme
setidir. Canlı Odoo örneğinin birebir dökümüdür (2026-09-05).

## Mimari

* `BASE_00_MECHANICAL` (16 kanonik) → `BASE_10_ELECTRICAL` (+10 kanonik)
  → 18 kategori seti. Toplam **20 set**.
* Kanonik alanlar `x_base_*`: debi m³/h, güç kW, voltaj/faz select,
  bağlantı, ölçüler, model/ürün adı, ağırlık... Etiketlerde kategori
  öneki yok.
* Kategoriye özgü ~31 yapısal alan korundu (yedek parça no, diş, koli...).
* ~213 zombi alan silindi; seyrek değerler `Ek Teknik Bilgi` metninde.
* Fiyat: EUR → liste fiyatı; USD → "Neta Katalog (USD)" kalemi + USD etiketi.
  Kaynakta çift olan 18 kod temizlendi (ikinci geçen aileden çıkarıldı);
  toplam **1837** benzersiz ürün.

## Dosyalar

* `??_pim_v2.json` (18 adet): `{meta, attribute_sets, attributes, products}`
* `load_pim_v2.py`: idempotent yükleyici (var olan kodu atlar).

## Yükleme

```sh
docker cp pim_v2 <web>:/tmp/pim_v2
docker exec -i <web> odoo shell -c /etc/odoo/odoo.conf -d odoo < pim_v2/load_pim_v2.py
```
