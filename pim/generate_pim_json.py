# -*- coding: utf-8 -*-
"""Kaynak kategori JSON'larini Odoo-PIM (OCA odoo-pim) uyumlu nitelik seti
JSON'una donusturur.

Kullanim:
    python3 pim/generate_pim_json.py 01 02

Girdi:
    categories/<no>_<Ad>.json              (urun/variant verisi)
    categories/<no>_<Ad>_attributes.json   (aile seviyesi veri)

Cikti:
    pim/<no>_pim.json

Yeni kategori eklerken:
    1. ATTRS_<KATEGORI> nitelik sozlugunu tanimla
    2. GROUPS_<KATEGORI> grup listesini tanimla
    3. CATEGORY_CONFIG["<no>"] icine prefix, root_set, series, name_overrides,
       attrs, groups ve builder anahtarlarini ekle
    4. Gerekliyse yeni bir value-builder fonksiyonu yaz ve BUILDERS'a ekle
"""

import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CAT_DIR = BASE / "categories"
OUT_DIR = BASE / "pim"

MODEL = "product.template"

# ---------------------------------------------------------------------------
# Nitelik sozlukleri
#   key / desc / desc_en / type / group / sets / level / source (+options)
#   sets: "ROOT" -> kok set; aksi halde ara/aile set key'i
# ---------------------------------------------------------------------------
ATTRS_PUMP = [
    dict(key="max_water_temp_c", desc="Maks. Su Sıcaklığı",
         desc_en="Max. Water Temperature", type="float", group="operating",
         sets=["ROOT"], level="family",
         source="family_specs_quantitative.max_temp_c"),
    dict(key="max_pressure_bar", desc="Maks. Çalışma Basıncı (bar)",
         desc_en="Max. Operating Pressure (bar)", type="float",
         group="operating", sets=["ROOT"], level="family",
         source="family_specs_quantitative.max_pressure_bar"),
    dict(key="power_hp", desc="Güç (HP)", desc_en="Power (HP)", type="float",
         group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_hp_power_hp"),
    dict(key="power_kw", desc="Güç (kW)", desc_en="Power (kW)", type="float",
         group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_kw_power | g_power"),
    dict(key="flow_m3h", desc="Debi (m³/saat)", desc_en="Flow (m³/h)",
         type="float", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.debi_m_h_flow | debi_m_3_h_flow | "
         "debi_m_h_flow_max | debi_l_h_flow_l_h"),
    dict(key="head_m", desc="Basma Yüksekliği (m)", desc_en="Head (m)",
         type="float", group="technical", sets=["dalgic-pompalar"],
         level="variant",
         source="variant_quantitative.basma_y_ksekli_i_head"),
    dict(key="rpm", desc="Devir (devir/dk)", desc_en="Speed (RPM)",
         type="integer", group="technical", sets=["ROOT"], level="family",
         source="family_specs_quantitative.rpm"),
    dict(key="sound_dba", desc="Ses Şiddeti (dB(A))",
         desc_en="Sound Pressure (dB(A))", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.ses_i_ddeti_dp_sound_dp | "
         "ses_i_ddeti_sound"),
    dict(key="efficiency_class", desc="Motor Verim Sınıfı",
         desc_en="Motor Efficiency Class", type="select", group="technical",
         sets=["hcp-serisi"], level="variant",
         source="variant_quantitative.yeterli_li_k_efficiency",
         options=["IE1", "IE3"],
         option_map={"IEI": "IE1"}),
    dict(key="voltage", desc="Voltaj", desc_en="Voltage", type="select",
         group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.voltaj_voltage | amper_amps",
         options=["220V / 50 Hz", "230V / 400V / 50 Hz",
                  "400V / 690V / 50 Hz"],
         option_map={"220V/50Hz": "220V / 50 Hz",
                     "230/400/50 Hz": "230V / 400V / 50 Hz",
                     "400/690/50 Hz": "400V / 690V / 50 Hz"}),
    dict(key="cable_length_m", desc="Kablo Uzunluğu (m)",
         desc_en="Cable Length (m)", type="float", group="electrical",
         sets=["dalgic-pompalar"], level="variant",
         source="variant_quantitative.kablo_cable"),
    dict(key="connection", desc="Bağlantı Giriş/Çıkış",
         desc_en="Inlet/Outlet Connection", type="select",
         group="connection", sets=["ROOT"], level="variant",
         source="variant_quantitative.ba_lanti_gi_ri_iki_inlet_outlet | "
         "ba_lanti_gi_ri_iki_inlet_outlet_d_outside_i_inside",
         options=["50 mm", "63 mm", "75 mm", "90 mm", "110 mm",
                  "50 mm (Dişli)", "Ø50 - Ø60", "50 / 63 mm (Dış/İç)"],
         option_map={"50 mm Dişli Threaded": "50 mm (Dişli)",
                     "50 mm 63 mm": "50 / 63 mm (Dış/İç)"}),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_kg_weight_kg"),
    dict(key="package_dims", desc="Paket Ölçüleri (GxYxD)",
         desc_en="Package Dimensions (WxHxD)", type="char",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.paket_package | "
         "paket_uxgxy_package_lxwxh"),
    dict(key="highlights", desc="Öne Çıkan Özellikler",
         desc_en="Highlights", type="text", group="marketing",
         sets=["ROOT"], level="family", source="qualitative.bullets_tr"),
    dict(key="icons", desc="Ürün İkonları", desc_en="Product Icons",
         type="multiselect", group="marketing", sets=["ROOT"],
         level="family", source="qualitative.icons",
         options=["RESIDENTIAL POOL", "SMALL COMMERCIAL POOL",
                  "COMMERCIAL POOL", "SUPER SILENT", "NO PRE FILTER",
                  "PRE FILTER CAPACITY", "2+2 YEAR WARRANTY", "POOL"]),
    dict(key="variant_description", desc="Ürün Açıklaması",
         desc_en="Variant Description", type="text", group="marketing",
         sets=["dalgic-pompalar", "pompa-setleri"], level="variant",
         source="variant_quantitative.a_iklama_description"),
]

GROUPS_PUMP = [
    {"key": "operating", "name": "Çalışma Koşulları",
     "name_en": "Operating Conditions"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "electrical", "name": "Elektrik", "name_en": "Electrical"},
    {"key": "connection", "name": "Bağlantı ve Montaj",
     "name_en": "Connection & Fitting"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
    {"key": "marketing", "name": "Pazarlama", "name_en": "Marketing"},
]

# ---------------------------------------------------------------------------
ATTRS_FILTER = [
    dict(key="max_water_temp_c", desc="Maks. Su Sıcaklığı",
         desc_en="Max. Water Temperature", type="float", group="operating",
         sets=["ROOT"], level="family",
         source="family_specs_quantitative.max_temp_c"),
    dict(key="max_pressure_bar", desc="Maks. Basınç (bar)",
         desc_en="Max. Pressure (bar)", type="float",
         group="operating", sets=["ROOT"], level="family",
         source="family_specs_quantitative.max_pressure_bar"),
    dict(key="flow_m3h", desc="Debi (m³/saat)", desc_en="Flow (m³/h)",
         type="float", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.debi_m_h_flow | debi_m_3_h_flow"),
    dict(key="connection", desc="Bağlantı Giriş/Çıkış",
         desc_en="Inlet/Outlet Connection", type="select",
         group="connection", sets=["ROOT"], level="variant",
         source="variant_quantitative.ba_lanti_gi_ri_iki_inlet_outlet | "
         "ba_lanti_connection",
         options=["50 mm", "63 mm", "75 mm", "90 mm", "110 mm", "160 mm",
                  "200 mm", '1½"', '2"', '1½" Dişli (Ø)', '2" Dişli (Ø)',
                  '2½" Dişli (Ø)', '1½" Yapıştırma (ø)',
                  '2" Yapıştırma (ø)', '2½" Yapıştırma (ø)',
                  '3" Yapıştırma (ø)', '4" Yapıştırma (ø)',
                  "50 / 63 mm (Yapıştırma)"],
         option_map={
             "1 ½": '1½"', "50": "50 mm", "63": "63 mm", "75": "75 mm",
             "90": "90 mm", "110": "110 mm", "160": "160 mm", "200": "200 mm",
             "1,5' Ø mm": '1½" Dişli (Ø)', "2' Ø mm": '2" Dişli (Ø)',
             "2,5' Ø mm": '2½" Dişli (Ø)', "1,5' ø mm": '1½" Yapıştırma (ø)',
             "2' ø mm": '2" Yapıştırma (ø)', "2,5' ø mm": '2½" Yapıştırma (ø)',
             "3' ø mm": '3" Yapıştırma (ø)', "4' ø mm": '4" Yapıştırma (ø)',
             "50-63 ø mm": "50 / 63 mm (Yapıştırma)",
         }),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_kg_weight_kg | "
         "a_irlik_weight | ambalaj_packing"),
    dict(key="diameter_mm", desc="Filtre Çapı (mm)",
         desc_en="Filter Diameter (mm)", type="float", group="technical",
         sets=["kum-filtreleri"], level="variant",
         source="variant_quantitative.ap_diameter"),
    dict(key="sand_capacity_kg", desc="Kum Kapasitesi (kg)",
         desc_en="Sand Capacity (kg)", type="float", group="technical",
         sets=["kum-filtreleri"], level="variant",
         source="variant_quantitative.kum_kg_sand_kg | kum_sand"),
    dict(key="working_pressure_bar", desc="Çalışma Basıncı (bar)",
         desc_en="Working Pressure (bar)", type="float", group="operating",
         sets=["kum-filtreleri"], level="variant",
         source="variant_quantitative.ali_ma_basinci_working_pressure"),
    dict(key="max_working_pressure_bar", desc="Maks. Çalışma Basıncı (bar)",
         desc_en="Max. Working Pressure (bar)", type="float",
         group="operating", sets=["kum-filtreleri"], level="variant",
         source="variant_quantitative.max_ali_ma_basinci_max_working_pressure"),
    dict(key="test_pressure_bar", desc="Test Basıncı (bar)",
         desc_en="Test Pressure (bar)", type="float", group="operating",
         sets=["kum-filtreleri"], level="variant",
         source="variant_quantitative.test_basinci_test_pressure"),
    dict(key="rating_micron", desc="Filtrasyon Hassasiyeti (mikron)",
         desc_en="Filtration Rating (micron)", type="char",
         group="technical", sets=["25-mikron"], level="variant",
         source="variant_quantitative.micron"),
    dict(key="cartridge_d_mm", desc="Kartuş Çapı D (mm)",
         desc_en="Cartridge Dia. D (mm)", type="float", group="physical",
         sets=["25-mikron"], level="variant",
         source="variant_quantitative.d_mm"),
    dict(key="cartridge_e_mm", desc="Kartuş Boyu E (mm)",
         desc_en="Cartridge Length E (mm)", type="float", group="physical",
         sets=["25-mikron"], level="variant",
         source="variant_quantitative.e_mm"),
    dict(key="grain_size", desc="Tane Boyutu", desc_en="Grain Size",
         type="char", group="technical",
         sets=["25-mikron", "filtre-medyalari"], level="variant",
         source="variant_quantitative.ap_diameter(-) | boyut_mm_size_mm"),
    dict(key="filter_type", desc="Filtre Türü", desc_en="Filter Type",
         type="select", group="bundle", sets=["yedek-kartus"],
         level="variant", source="variant_quantitative.fi_ltre_t_r_filter",
         options=["Kartuş", "Kum"],
         option_map={"Kartuş Cartridge": "Kartuş", "Kum Sand": "Kum"}),
    dict(key="skimmer", desc="Skimfilter", desc_en="Skimfilter",
         type="char", group="bundle", sets=["yedek-kartus"], level="variant",
         source="variant_quantitative.skimfilter_skimfilter"),
    dict(key="pump_hp", desc="Pompa Gücü (HP)", desc_en="Pump Power (HP)",
         type="float", group="bundle", sets=["yedek-kartus"], level="variant",
         source="variant_quantitative.pompa_pump"),
    dict(key="pump_phase", desc="Pompa Fazı", desc_en="Pump Phase",
         type="select", group="bundle", sets=["yedek-kartus"],
         level="variant", source="variant_quantitative.pompa_pump",
         options=["Monofaze", "Trifaze"]),
    dict(key="max_pool_m2", desc="Maks. Havuz Alanı (m²)",
         desc_en="Max. Pool Area (m²)", type="float", group="technical",
         sets=["yedek-kartus"], level="variant",
         source="variant_quantitative.max_havuz_m_max_pool_m"),
    dict(key="machine_room", desc="Makine Dairesi",
         desc_en="Mechanical Room", type="select", group="bundle",
         sets=["yedek-kartus"], level="variant",
         source="variant_quantitative.maki_na_dai_resi_mechanical_room",
         options=["Var", "Opsiyonel"],
         option_map={"✓ Var": "Var", "Opsiyonel Optional": "Opsiyonel"}),
    dict(key="contents", desc="Set İçeriği", desc_en="Set Contents",
         type="text", group="bundle", sets=["yedek-kartus"], level="variant",
         source="variant_quantitative.i_i_ndeki_ler_contents"),
    dict(key="interior_dims", desc="İç Ölçüler", desc_en="Interior Dimensions",
         type="char", group="physical", sets=["zeolit-diger"], level="variant",
         source="variant_quantitative.i_l_ler_interior_dimensions | "
         "i_ten_i_e_interior_sizes"),
    dict(key="outer_sizes", desc="Dış Ölçüler",
         desc_en="Outer Dimensions", type="char", group="physical",
         sets=["zeolit-diger"], level="variant",
         source="variant_quantitative.di_tan_di_a_outher_sizes"),
    dict(key="length_cm", desc="Uzunluk (cm)", desc_en="Length (cm)",
         type="float", group="physical", sets=["zeolit-diger"],
         level="variant",
         source="variant_quantitative.uzunluk_lenght | uzunluk_length"),
    dict(key="width_cm", desc="Genişlik (cm)", desc_en="Width (cm)",
         type="float", group="physical", sets=["zeolit-diger"],
         level="variant", source="variant_quantitative.geni_li_k_width"),
    dict(key="height_cm", desc="Yükseklik (cm)", desc_en="Height (cm)",
         type="float", group="physical", sets=["zeolit-diger"],
         level="variant", source="variant_quantitative.y_ksekli_k_height"),
    dict(key="steps", desc="Basamak Sayısı", desc_en="Number of Steps",
         type="integer", group="physical", sets=["zeolit-diger"],
         level="variant", source="variant_quantitative.basamak_step"),
    dict(key="highlights", desc="Öne Çıkan Özellikler",
         desc_en="Highlights", type="text", group="marketing",
         sets=["ROOT"], level="family", source="qualitative.bullets_tr"),
    dict(key="icons", desc="Ürün İkonları", desc_en="Product Icons",
         type="multiselect", group="marketing", sets=["ROOT"],
         level="family", source="qualitative.icons",
         options=["RESIDENTIAL POOL", "2 YEAR WARRANTY",
                  "2+2 YEAR WARRANTY", "POOL PLUMBING LINES",
                  "POOL CLEANING KIT", "POOL HEATER"]),
]

GROUPS_FILTER = [
    {"key": "operating", "name": "Çalışma Koşulları",
     "name_en": "Operating Conditions"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "connection", "name": "Bağlantı ve Montaj",
     "name_en": "Connection & Fitting"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
    {"key": "bundle", "name": "Set İçeriği", "name_en": "Set Contents"},
    {"key": "marketing", "name": "Pazarlama", "name_en": "Marketing"},
]

# ---------------------------------------------------------------------------
ATTRS_WHITE = [
    dict(key="model", desc="Model", desc_en="Model", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model_model (Liner/Beton haricinde)"),
    dict(key="product_label", desc="Ürün Adı", desc_en="Product Label",
         type="char", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.r_n_adi_product | "
         "r_n_adi_product_name | l_diameter(komple set)"),
    dict(key="pool_type", desc="Havuz Tipi", desc_en="Pool Type",
         type="select", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model_model | havuz_ti_pi_pool_type",
         options=["Beton", "Liner"],
         option_map={"Beton Concrete": "Beton", "Liner": "Liner"}),
    dict(key="color", desc="Renk", desc_en="Color", type="select",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.renk_color",
         options=["Beyaz (White)", "Siyah (Black)", "Mavi (Blue)",
                  "Sıcak Beyaz (Warm White)", "Soğuk Beyaz (Cold White)",
                  "Gün Işığı (Day Light)", "Doğal Beyaz (Natural White)",
                  "RGB", "RGB 2 Damarlı (2 Cores)",
                  "RGB 4 Damarlı (4 Cores)", "Kırmızı (Red)",
                  "Yeşil (Green)"],
         option_map={
             "Mavi Blue": "Mavi (Blue)",
             "Sıcak Beyaz Warm White": "Sıcak Beyaz (Warm White)",
             "Soğuk Beyaz Cold White": "Soğuk Beyaz (Cold White)",
             "Buz Beyaz Cold White": "Soğuk Beyaz (Cold White)",
             "Beyaz White": "Beyaz (White)",
             "Siyah Black": "Siyah (Black)",
             "Siyah Black ★": "Siyah (Black)",
             "★ Siyah Black": "Siyah (Black)",
             "Gün Işığı Day Light": "Gün Işığı (Day Light)",
             "Doğal Beyaz Natural White": "Doğal Beyaz (Natural White)",
             "RGB 4 Damarlı RGB 4 Cores": "RGB 4 Damarlı (4 Cores)",
             "RGB 4 Kablolu RGB 4 Cores": "RGB 4 Damarlı (4 Cores)",
             "RGB 2 Damarlı RGB 2 Cores": "RGB 2 Damarlı (2 Cores)",
             "RGB 2 Kablolu RGB 2 Cores": "RGB 2 Damarlı (2 Cores)",
             "Kırmızı Red": "Kırmızı (Red)",
             "Yeşil Green": "Yeşil (Green)",
         }),
    dict(key="power_w", desc="Güç (W)", desc_en="Power (W)", type="float",
         group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_power"),
    dict(key="voltage_v", desc="Voltaj (V)", desc_en="Voltage (V)",
         type="integer", group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_power"),
    dict(key="connection", desc="Bağlantı Giriş/Çıkış",
         desc_en="Inlet/Outlet Connection", type="select",
         group="connection", sets=["ROOT"], level="variant",
         source="variant_quantitative.ba_lanti_connection",
         options=["50 mm", "50 / 63 mm", "53 mm",
                  'Giriş φ20 mm veya 3/4" BSP, Çıkış φ50 mm'],
         option_map={"50/63 mm": "50 / 63 mm",
                     'Inlet: $\\phi$ 20 mm veya or 3/4"BSP, Outlet: '
                     '$\\phi$ 50mm': 'Giriş φ20 mm veya 3/4" BSP, Çıkış φ50 mm'}),
    dict(key="diameter_mm", desc="Çap (mm)", desc_en="Diameter (mm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.ap_dia"),
    dict(key="length_m", desc="Uzunluk (m)", desc_en="Length (m)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.l_diameter(mt)"),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_weight"),
    dict(key="skimmer_type", desc="Şekil (Tür)", desc_en="Shape (Type)",
         type="select", group="connection", sets=["skimmer-skimmers"],
         level="variant", source="variant_quantitative.eki_l_type",
         options=["Standart", "Geniş (Wide)", "Yapıştırma (Slip)",
                  "Dişli (Threaded)", "Tabandan (Floor) Yapıştırma",
                  "Tabandan (Floor) Dişli", "Yandan (Wall) Dişli",
                  "Yandan (Wall) Yapıştırma", "Vakum (Vacuum) / Yapıştırma",
                  "İnce Geniş Ağız (Liner Thin Wide)", "İnce Ağız (Mirror)",
                  "Konik (Adjustable)", "Uzatma Parçası (Extension)"],
         option_map={
             "Geniş Wide": "Geniş (Wide)",
             "Yapıştırma Slip": "Yapıştırma (Slip)",
             "Dişli Threaded": "Dişli (Threaded)",
             "Tabandan Floor Yapıştırma Slip": "Tabandan (Floor) Yapıştırma",
             "Tabandan Floor Dişli Threaded": "Tabandan (Floor) Dişli",
             "Yandan Wall Dişli Threaded": "Yandan (Wall) Dişli",
             "Yandan Dişli Wall Threaded": "Yandan (Wall) Dişli",
             "Yandan Wall Yapıştırma Slip": "Yandan (Wall) Yapıştırma",
             "Vakum Vacuum / Yapıştırma Slip": "Vakum (Vacuum) / Yapıştırma",
             "İnce Geniş Ağız Liner Thin Wide Liner":
                 "İnce Geniş Ağız (Liner Thin Wide)",
             "İnce Ağız Mirror Skimmer": "İnce Ağız (Mirror)",
             "Konik Adj. Conic": "Konik (Adjustable)",
             "Uzatma Parçası Extension Part": "Uzatma Parçası (Extension)",
         }),
    dict(key="dims", desc="Ölçüler", desc_en="Dimensions", type="char",
         group="physical", sets=["skimmer-skimmers"], level="variant",
         source="variant_quantitative.l_dimension | l_mm_size_mm | boy_size"),
    dict(key="width_cm", desc="Genişlik (cm)", desc_en="Width (cm)",
         type="float", group="physical",
         sets=["par-56-powerled-amp-ller-bulbs-with-power-led-par-56"],
         level="variant", source="variant_quantitative.geni_li_k_width"),
    dict(key="depth_cm", desc="Derinlik (cm)", desc_en="Depth (cm)",
         type="float", group="physical",
         sets=["par-56-powerled-amp-ller-bulbs-with-power-led-par-56"],
         level="variant", source="variant_quantitative.deri_nli_k_l_s_power"),
    dict(key="power_hp", desc="Güç (HP)", desc_en="Power (HP)", type="float",
         group="technical", sets=["stream-equipments"], level="variant",
         source="variant_quantitative.g_hp_power_hp"),
    dict(key="phase", desc="Faz", desc_en="Phase", type="select",
         group="electrical", sets=["stream-equipments"], level="variant",
         source="variant_quantitative.g_hp_power_hp",
         options=["Monofaze", "Trifaze"]),
    dict(key="model_name", desc="Model Adı", desc_en="Model Name",
         type="char", group="general", sets=["stream-equipments"],
         level="variant", source="variant_quantitative.model_adi_model_name"),
    dict(key="flow_lmin", desc="Debi (L/dk)", desc_en="Flow Rate (L/min)",
         type="char", group="technical",
         sets=["su-seviye-reg-lat-r-water-level-regulator"], level="variant",
         source="variant_quantitative.debi_l_dk_flowrate_lt_min"),
]

GROUPS_WHITE = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "electrical", "name": "Elektrik", "name_en": "Electrical"},
    {"key": "connection", "name": "Bağlantı ve Montaj",
     "name_en": "Connection & Fitting"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
]

# ---------------------------------------------------------------------------
ATTRS_OUTDOOR = [
    dict(key="model", desc="Model", desc_en="Model", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model"),
    dict(key="product_label", desc="Ürün Adı", desc_en="Product Label",
         type="char", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.r_n_i_smi_product_name | "
         "tanim_description | r_n_adi_product"),
    dict(key="connection", desc="Bağlantı Giriş/Çıkış",
         desc_en="Inlet/Outlet Connection", type="select",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.ba_lanti_connection",
         options=['1½"', '2"'],
         option_map={'1 ½"': '1½"'}),
    dict(key="steps", desc="Basamak Sayısı", desc_en="Step Number",
         type="select", group="general", sets=["merdivenler-basamaklar"],
         level="variant", source="variant_quantitative.basamak_sayisi_step_number",
         options=["1", "2", "3", "4", "5", "2+2", "3+3", "4+4",
                  "3+3 (Platformlu)", "4+4 (Platformlu)"],
         option_map={"3+3 Platformlu With Platform": "3+3 (Platformlu)",
                     "4+4 Platformlu With Platform": "4+4 (Platformlu)"}),
    dict(key="tank_capacity", desc="Depo Kapasitesi (L)",
         desc_en="Tank Capacity (L)", type="float", group="general",
         sets=["du-lar-showers"], level="variant",
         source="variant_quantitative.kapasi_te_tank_capacity | "
         "tank_kapasi_tesi_tank_capacity"),
    dict(key="tank_material", desc="Depo Malzemesi", desc_en="Tank Material",
         type="char", group="general", sets=["du-lar-showers"],
         level="variant", source="variant_quantitative.tank_ci_nsi_tank_material"),
    dict(key="aisi", desc="Paslanmaz Kalitesi (AISI)",
         desc_en="Stainless Grade (AISI)", type="select", group="physical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.aisi | l_size(AISI...)",
         options=["304", "316"]),
    dict(key="dims", desc="Ölçüler", desc_en="Dimensions", type="char",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.l_size | l_ler_uxgxy_size_lxwxh"),
    dict(key="diameter_mm", desc="Çap (mm)", desc_en="Diameter (mm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.ap_dia | ap_diameter | "
         "boru_api_pipe_diameter"),
    dict(key="edge_size", desc="Kenar Ölçüsü", desc_en="Edge Size",
         type="char", group="physical",
         sets=["ta-ma-izgaralar-overflow-gratings"], level="variant",
         source="variant_quantitative.kenar_l_leri_edge_size | "
         "ap_dia(16x10)"),
    dict(key="width_cm", desc="Genişlik (cm)", desc_en="Width (cm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.geni_li_k_width"),
    dict(key="length_m", desc="Boy/Uzunluk (m)", desc_en="Length (m)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.boy_length | uzunluk_lenght"),
    dict(key="volume_m3", desc="Hacim (m³)", desc_en="Volume (m³)",
         type="float", group="physical", sets=["du-lar-showers"],
         level="variant", source="variant_quantitative.haci_m_volume"),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_weight"),
    dict(key="max_pressure_bar", desc="Maks. Basınç (bar)",
         desc_en="Max. Pressure (bar)", type="float", group="operating",
         sets=["ROOT"], level="family",
         source="family_specs_quantitative.max_pressure_bar | "
         "basin_max_pressure"),
    dict(key="speed", desc="Kaldırma Hızı (m/sn)",
         desc_en="Lift Speed (m/s)", type="float", group="operating",
         sets=["du-lar-showers"], level="variant",
         source="variant_quantitative.hiz_max_velocity_max"),
    dict(key="launch_time", desc="Yüklü İndirme Süresi",
         desc_en="Launch Time with Load", type="char", group="operating",
         sets=["du-lar-showers"], level="variant",
         source="variant_quantitative.y_kl_suya_i_ndi_rme_s_resi_launch_time_with_load"),
    dict(key="load_time", desc="Yüklü Kaldırma Süresi",
         desc_en="Load Time", type="char", group="operating",
         sets=["du-lar-showers"], level="variant",
         source="variant_quantitative.y_kl_kaldirma_s_resi_load_time"),
    dict(key="hose_dia", desc="Hortum Çapı", desc_en="Hose Diameter",
         type="char", group="physical",
         sets=["ta-ma-izgaralar-overflow-gratings"], level="variant",
         source="variant_quantitative.hortum_api_hose_dia",
         option_map={'38 mm - 1/2"': '38 mm - ½"'}),
    dict(key="hose_length", desc="Uzunluk (Parçalı)",
         desc_en="Length (Multi-piece)", type="char", group="physical",
         sets=["ta-ma-izgaralar-overflow-gratings"], level="variant",
         source="variant_quantitative.uzunluk_length"),
    dict(key="filter_model", desc="Filtre", desc_en="Filter", type="char",
         group="bundle", sets=["ta-ma-izgaralar-overflow-gratings"],
         level="variant", source="variant_quantitative.fi_ltre_filter"),
    dict(key="pump_model", desc="Pompa", desc_en="Pump", type="char",
         group="bundle", sets=["ta-ma-izgaralar-overflow-gratings"],
         level="variant", source="variant_quantitative.pompa_pump"),
    dict(key="filtration_flow", desc="Filtrasyon Debi (m³/h)",
         desc_en="Filtration Flow (m³/h)", type="char", group="bundle",
         sets=["ta-ma-izgaralar-overflow-gratings"], level="variant",
         source="variant_quantitative.fi_lrasyon_debi_si_filtration_flow"),
    dict(key="pump_flow", desc="Pompa Debi (m³/h)",
         desc_en="Pump Flow (m³/h)", type="char", group="bundle",
         sets=["ta-ma-izgaralar-overflow-gratings"], level="variant",
         source="variant_quantitative.pompa_debi_si_pump_flow"),
]

GROUPS_OUTDOOR = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
    {"key": "operating", "name": "Çalışma Koşulları",
     "name_en": "Operating Conditions"},
    {"key": "bundle", "name": "Set İçeriği", "name_en": "Set Contents"},
]

# ---------------------------------------------------------------------------
ATTRS_CLEAN = [
    dict(key="model", desc="Model", desc_en="Model", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model"),
    dict(key="compatibility", desc="Uyumluluk", desc_en="Compatibility",
         type="char", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.uyumluluk_compatibility"),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_weight"),
    dict(key="dims", desc="Ölçüler", desc_en="Dimensions", type="char",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.l_ler_size | l_size"),
    dict(key="length_cm", desc="Uzunluk (cm)", desc_en="Length (cm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.uzunluk_length"),
    dict(key="material", desc="Malzeme", desc_en="Material", type="char",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.malzeme_material"),
    dict(key="pole_length", desc="Sap Uzunluğu", desc_en="Pole Length",
         type="char", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.sap_uzunlu_u_pole_length"),
    dict(key="power_w", desc="Güç (W)", desc_en="Power (W)", type="float",
         group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_power"),
    dict(key="power_input", desc="Güç Girişi", desc_en="Power Input",
         type="char", group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_power_input"),
    dict(key="charge_time_h", desc="Şarj Süresi (saat)",
         desc_en="Charging Time (h)", type="float", group="electrical",
         sets=["robotlar"], level="variant",
         source="variant_quantitative.arj_s_resi_charging_time"),
    dict(key="hose_length_m", desc="Hortum Uzunluğu (m)",
         desc_en="Hose Length (m)", type="float", group="technical",
         sets=["robotlar"], level="variant",
         source="variant_quantitative.hortum_uzunlu_u_hose_length"),
    dict(key="max_pool_size", desc="Maks. Havuz Ölçüsü",
         desc_en="Max. Pool Size", type="char", group="technical",
         sets=["robotlar"], level="variant",
         source="variant_quantitative.max_havuz_l_s_pool_max_size"),
    dict(key="recommended_pool_size", desc="Önerilen Havuz Boyutu",
         desc_en="Recommended Pool Size", type="char", group="technical",
         sets=["robotlar"], level="variant",
         source="variant_quantitative.neri_len_havuz_boyutu_recommended_pool_size"),
    dict(key="suction_flow_m3h", desc="Emiş Kapasitesi (m³/h)",
         desc_en="Suction Capacity (m³/h)", type="float", group="technical",
         sets=["robotlar"], level="variant",
         source="variant_quantitative.emi_kapasi_tesi_suction_capacity"),
    dict(key="cleaning_speed", desc="Temizlik Hızı", desc_en="Cleaning Speed",
         type="char", group="technical", sets=["robotlar"], level="variant",
         source="variant_quantitative.temi_zli_k_hizi_cleaning_speed"),
    dict(key="filtration_fineness", desc="Filtrasyon Hassasiyeti",
         desc_en="Filtration Fineness", type="char", group="technical",
         sets=["robotlar"], level="variant",
         source="variant_quantitative.fi_ltasyon_hassasi_yeti_filtration_fineness"),
]

GROUPS_CLEAN = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "electrical", "name": "Elektrik", "name_en": "Electrical"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
]

# ---------------------------------------------------------------------------
ATTRS_DISINF = [
    dict(key="model", desc="Model", desc_en="Model", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model"),
    dict(key="product_label", desc="Ürün Adı", desc_en="Product Label",
         type="char", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.r_n_i_smi_product_name | "
         "tanim_description"),
    dict(key="pool_volume_m3", desc="Havuz Hacmi (m³)",
         desc_en="Pool Volume (m³)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.havuz_hacmi_pool_volume"),
    dict(key="max_pool_volume_m3", desc="Maks. Havuz Hacmi (m³)",
         desc_en="Max. Pool Volume (m³)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.max_havuz_hacmi_max_pool_volume"),
    dict(key="max_flow_m3h", desc="Maks. Debi (m³/h)",
         desc_en="Max. Flow Rate (m³/h)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.max_debi_m_3_h_max_flow_rate_m_3_h | "
         "max_debi_m_h_max_flow_rate_m_h | max_debi_m_h_max_flow_m_h | "
         "max_debi_m_3_h_max_flow_m_3_h"),
    dict(key="connection", desc="Bağlantı", desc_en="Connection",
         type="char", group="connection", sets=["ROOT"], level="variant",
         source="variant_quantitative.ba_lanti_connection | "
         "ba_lanti_mm_connection_mm"),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_weight"),
    dict(key="power_w", desc="Güç (W)", desc_en="Power (W)", type="float",
         group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.watt"),
    dict(key="voltage", desc="Voltaj / Frekans", desc_en="Voltage / Frequency",
         type="char", group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.voltaj_voltage | "
         "voltaj_frekans_voltage_frequency"),
    dict(key="lamp_power", desc="UV Lamba Gücü",
         desc_en="UV Lamp Power", type="char", group="technical",
         sets=["uv-sistemleri"], level="variant",
         source="variant_quantitative.uv_lamba_g_c_uv_lamp_power"),
    dict(key="reactor_length_mm", desc="Reaktör/Uzunluk (mm)",
         desc_en="Reactor Length (mm)", type="float", group="physical",
         sets=["uv-sistemleri"], level="variant",
         source="variant_quantitative.reakt_r_uzunlu_u_reactor_length | "
         "r_n_boyutu_uzunluk_product_size_length"),
    dict(key="tube", desc="Tüp Yapısı", desc_en="Tube Configuration",
         type="char", group="technical", sets=["uv-sistemleri"],
         level="variant", source="variant_quantitative.t_p_tube"),
    dict(key="chlorine_gph", desc="Klor Üretimi (g/saat)",
         desc_en="Chlorine Production (g/h)", type="float",
         group="technical", sets=["klor-ureticileri"], level="variant",
         source="variant_quantitative.klor_reti_mi_chlorine"),
    dict(key="salt_level", desc="Tuz Seviyesi (PPM)",
         desc_en="Salt Level (PPM)", type="char", group="technical",
         sets=["klor-ureticileri"], level="variant",
         source="variant_quantitative.tuz_sevi_yesi_salt_level | "
         "tuz_arali_i_salinity_range"),
    dict(key="pipe", desc="Boru", desc_en="Pipe", type="char",
         group="connection", sets=["klor-ureticileri"], level="variant",
         source="variant_quantitative.boru_pipe"),
    dict(key="orp_level", desc="ORP Seviyesi (mV)",
         desc_en="ORP Level (mV)", type="char", group="technical",
         sets=["klor-ureticileri"], level="variant",
         source="variant_quantitative.orp_sevi_yesi_orp_level"),
    dict(key="water_hardness", desc="Su Sertliği", desc_en="Water Hardness",
         type="char", group="technical", sets=["klor-ureticileri"],
         level="variant", source="variant_quantitative.su_sertli_i_water_hardness"),
    dict(key="water_temp", desc="Su Sıcaklığı", desc_en="Water Temperature",
         type="char", group="technical", sets=["klor-ureticileri"],
         level="variant", source="variant_quantitative.su_sicakli_i_water_temp"),
    dict(key="protection", desc="Koruma Sınıfı", desc_en="Protection",
         type="char", group="technical", sets=["klor-ureticileri"],
         level="variant", source="variant_quantitative.koruma_protection"),
    dict(key="rated_current", desc="Anma Akımı", desc_en="Rated Current",
         type="char", group="electrical", sets=["klor-ureticileri"],
         level="variant", source="variant_quantitative.akim_rated_current"),
    dict(key="rated_voltage", desc="Anma Voltajı", desc_en="Rated Voltage",
         type="char", group="electrical", sets=["klor-ureticileri"],
         level="variant", source="variant_quantitative.geri_li_m_rated_voltage"),
    dict(key="power_input", desc="Güç Girişi", desc_en="Power Input",
         type="char", group="electrical", sets=["klor-ureticileri"],
         level="variant", source="variant_quantitative.g_gi_ri_i_power_input"),
    dict(key="power_output", desc="Güç Çıkışı", desc_en="Power Output",
         type="char", group="electrical", sets=["klor-ureticileri"],
         level="variant", source="variant_quantitative.g_iki_i_power_output"),
    dict(key="ph_valve", desc="pH Valfi", desc_en="pH Valve", type="char",
         group="technical", sets=["klor-ureticileri"], level="variant",
         source="variant_quantitative.ph_valfi_ph_valve"),
    dict(key="flow_lth", desc="Debi (L/h)", desc_en="Flow (L/h)",
         type="float", group="technical", sets=["dozaj-panelleri"],
         level="variant", source="variant_quantitative.debi_lt_h_flow_lt_h"),
    dict(key="pressure_bar", desc="Maks. Basınç (bar)",
         desc_en="Max. Pressure (bar)", type="float", group="technical",
         sets=["dozaj-panelleri"], level="family",
         source="family_specs_quantitative.max_pressure_bar | "
         "basin_power | basin_pressure | basin_bar_pressure"),
    dict(key="pump_capacity", desc="Pompa Kapasitesi",
         desc_en="Pump Capacity", type="char", group="technical",
         sets=["dozaj-panelleri"], level="variant",
         source="variant_quantitative.pompa_kapasi_tesi_pump_capacity"),
    dict(key="capacity", desc="Kapasite", desc_en="Capacity", type="char",
         group="technical", sets=["dozaj-panelleri", "dozaj-aksesuarlari"],
         level="variant", source="variant_quantitative.kapasi_te_capacity"),
    dict(key="measuring_range", desc="Ölçüm Aralığı",
         desc_en="Measuring Range", type="char", group="technical",
         sets=["dozaj-panelleri", "dozaj-aksesuarlari"], level="variant",
         source="variant_quantitative.l_m_arali_i_measuring_range"),
    dict(key="tablet_capacity", desc="Tablet Kapasitesi",
         desc_en="Tablet Carrying Capacity", type="char",
         group="technical", sets=["dozaj-aksesuarlari"], level="variant",
         source="variant_quantitative.tablet_kapasi_te_tablet_carrying_capacity"),
    dict(key="dims", desc="Ölçüler (cm)", desc_en="Dimensions (cm)",
         type="char", group="physical", sets=["hijyen-test"],
         level="variant",
         source="variant_quantitative.r_n_l_leri_cm_product_sizes_cm"),
    dict(key="tupe", desc="Tipe (TUPE)", desc_en="Type (TUPE)",
         type="char", group="technical",
         sets=["max-veri-m-max-efficiency"], level="variant",
         source="variant_quantitative.t_p_tupe"),
    dict(key="gross_kg", desc="Brüt Ağırlık (kg)",
         desc_en="Gross Weight (kg)", type="float", group="physical",
         sets=["max-veri-m-max-efficiency"], level="variant",
         source="variant_quantitative.br_t_kg_gross_kg"),
    dict(key="flow_switch", desc="Akış Anahtarı", desc_en="Flow Switch",
         type="char", group="technical",
         sets=["max-veri-m-max-efficiency"], level="variant",
         source="variant_quantitative.aki_anahtari_flow_switch"),
    dict(key="plug", desc="Priz", desc_en="Plug", type="char",
         group="electrical", sets=["max-veri-m-max-efficiency"],
         level="variant", source="variant_quantitative.pri_z_plug"),
    dict(key="lamp_indicator", desc="Lamba Ömrü Göstergesi",
         desc_en="Lamp Life Indicator", type="char", group="technical",
         sets=["max-veri-m-max-efficiency"], level="variant",
         source="variant_quantitative."
         "analog_lamba_m_r_g_stergeli_digital_lamp_life_indicator"),
    dict(key="vh_mount", desc="Dikey/Yatay Montaj",
         desc_en="Vertical/Horizontal Mounting", type="char",
         group="technical", sets=["max-veri-m-max-efficiency"],
         level="variant",
         source="variant_quantitative."
         "di_key_yatay_montaj_vertical_or_horizontal_mountable"),
    dict(key="lamp_sign", desc="Lamba Göstergesi", desc_en="Lamp Sign",
         type="char", group="technical",
         sets=["max-veri-m-max-efficiency"], level="variant",
         source="variant_quantitative.lamba_g_stergesi_lamp_sign"),
    dict(key="pool_type_mark", desc="Havuz Tipi (İşaret)",
         desc_en="For Pool Type (Mark)", type="char", group="technical",
         sets=["max-veri-m-max-efficiency"], level="variant",
         source="variant_quantitative.havuz_tipi_for_pool_type"),
]

GROUPS_DISINF = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "electrical", "name": "Elektrik", "name_en": "Electrical"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
    {"key": "connection", "name": "Bağlantı ve Montaj",
     "name_en": "Connection & Fitting"},
]

# ---------------------------------------------------------------------------
ATTRS_CHEM = [
    dict(key="packing_kg", desc="Ambalaj (kg)", desc_en="Packing (kg)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.ambalaj_packing"),
    dict(key="packing_type", desc="Ambalaj Tipi", desc_en="Packing Type",
         type="char", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.ambalaj_packing"),
]

GROUPS_CHEM = [
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
]

# ---------------------------------------------------------------------------
ATTRS_HEAT = [
    dict(key="model", desc="Model", desc_en="Model", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model"),
    dict(key="phase", desc="Faz", desc_en="Phase", type="select",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.faz_phase",
         options=["Monofaz (Single Phase)", "Trifaz (Three Phase)",
                  "Mono / Tri"],
         option_map={
             "Monofaz Single phase": "Monofaz (Single Phase)",
             "Monofaz Mono": "Monofaz (Single Phase)",
             "Trifaz Threephase": "Trifaz (Three Phase)",
             "Trifaz Threephase 3 faz/phase 400V": "Trifaz (Three Phase)",
         }),
    dict(key="power_kw", desc="Güç (kW)", desc_en="Power (kW)",
         type="float", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_power"),
    dict(key="required_flow_m3h", desc="Gerekli Debi (m³/h)",
         desc_en="Required Flow (m³/h)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.debi_i_hti_yaci_flow_requirements"),
    dict(key="max_flow_m3h", desc="Maks. Debi (m³/h)",
         desc_en="Max. Flow (m³/h)", type="float", group="technical",
         sets=["ROOT"], level="variant", source="variant_quantitative."),
    dict(key="dims", desc="Ölçüler (UxDxG)", desc_en="Dimensions (LxDxW)",
         type="char", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.l_ler_uxdxg_dimensions_lxdxw"),
    dict(key="frequency", desc="Frekans", desc_en="Frequency", type="char",
         group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.frekans_frequency"),
    dict(key="volume_m3", desc="Hacim (m³)", desc_en="Volume (m³)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.haci_m_volume"),
    dict(key="gross_kg", desc="Brüt Ağırlık (kg)",
         desc_en="Gross Weight (kg)", type="float", group="physical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_gross_weight"),
    dict(key="power_output", desc="Güç Çıkışı", desc_en="Power Output",
         type="char", group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_iki_i_power_output"),
    dict(key="accessories_included", desc="Dahil Aksesuarlar",
         desc_en="Accessories Included", type="char", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative."
         "aksesuarlar_dahi_ldi_r_accessories_included"),
    dict(key="hot_water_flow", desc="Sıcak Su Akışı (L/dk)",
         desc_en="Hot Water Flow (L/min)", type="float",
         group="technical", sets=["isi-pompalari"], level="variant",
         source="variant_quantitative.sicak_su_aki_i_hot_water_flow"),
    dict(key="pool_water_flow", desc="Havuz Suyu Akışı (L/dk)",
         desc_en="Pool Water Flow (L/min)", type="float",
         group="technical", sets=["isi-pompalari"], level="variant",
         source="variant_quantitative.havuzun_suyunun_aki_i_flow_of_pool_water"),
    dict(key="heat_capacity_kcalh", desc="Eşanjör Kapasitesi (kcal/h)",
         desc_en="Exchanger Capacity (kcal/h)", type="float",
         group="technical", sets=["esanjorler"], level="variant",
         source="variant_quantitative.e_anj_r_kapasi_tesi_kcal_h"),
    dict(key="pool_area_m2", desc="Havuz Alanı (m²)",
         desc_en="Pool Area (m²)", type="float", group="technical",
         sets=["esanjorler"], level="variant",
         source="variant_quantitative.havuz_m"),
    dict(key="reji_m", desc="Reji (m)", desc_en="Regime (m)", type="float",
         group="technical", sets=["esanjorler"], level="variant",
         source="variant_quantitative.reji_m"),
    dict(key="exchanger_model", desc="Eşanjör Modeli",
         desc_en="Exchanger Model", type="char", group="technical",
         sets=["esanjorler"], level="variant",
         source="variant_quantitative.e_anj_r_modeli"),
    dict(key="plate_count", desc="Plaka Sayısı", desc_en="Plate Count",
         type="float", group="technical", sets=["esanjorler"],
         level="variant", source="variant_quantitative.plaka_sayisi"),
    dict(key="temp_range", desc="Sıcaklık Aralığı (°C)",
         desc_en="Temperature Range (°C)", type="char", group="technical",
         sets=["esanjorler"], level="variant",
         source="variant_quantitative.sicaklik"),
    dict(key="connection", desc="Bağlantı", desc_en="Connection",
         type="char", group="connection", sets=["esanjorler"],
         level="variant",
         source="variant_quantitative.ba_lanti_connection | iki_ba_lanti"),
    dict(key="length_mm", desc="Uzunluk (mm)", desc_en="Length (mm)",
         type="float", group="physical", sets=["esanjorler"],
         level="variant", source="variant_quantitative.l_mm"),
    dict(key="primer_flow_m3h", desc="Primer Debi (m³/h)",
         desc_en="Primary Flow (m³/h)", type="float", group="technical",
         sets=["esanjorler"], level="variant",
         source="variant_quantitative.primer_debi_primary_flow"),
    dict(key="primer_loss_kpa", desc="Primer Basınç Kaybı (kPa)",
         desc_en="Primary Pressure Loss (kPa)", type="float",
         group="technical", sets=["esanjorler"], level="variant",
         source="variant_quantitative.primer_ba_sin_kaybi_loss_kpa"),
    dict(key="secondary_flow_m3h", desc="Sekonder Debi (m³/h)",
         desc_en="Secondary Flow (m³/h)", type="float", group="technical",
         sets=["esanjorler"], level="variant",
         source="variant_quantitative.sekonder_debi_secondary_flow"),
    dict(key="secondary_loss_kpa", desc="Sekonder Basınç Kaybı (kPa)",
         desc_en="Secondary Pressure Loss (kPa)", type="float",
         group="technical", sets=["esanjorler"], level="variant",
         source="variant_quantitative.sekonder_basin_kaybi_loss_kpa"),
    dict(key="heat_15c_kw", desc="Isıtma Gücü 15°C (kW)",
         desc_en="Heating Power 15°C (kW)", type="float", group="technical",
         sets=["esanjorler"], level="variant",
         source="variant_quantitative.t_15_c_kw"),
    dict(key="heat_30c_kw", desc="Isıtma Gücü 30°C (kW)",
         desc_en="Heating Power 30°C (kW)", type="float", group="technical",
         sets=["esanjorler"], level="variant",
         source="variant_quantitative.t_30_c_kw"),
    dict(key="heat_65c_kw", desc="Isıtma Gücü 65°C (kW)",
         desc_en="Heating Power 65°C (kW)", type="float", group="technical",
         sets=["esanjorler"], level="variant",
         source="variant_quantitative.t_65_c_kw"),
    dict(key="pressure_bar", desc="Maks. Basınç (bar)",
         desc_en="Max. Pressure (bar)", type="float", group="technical",
         sets=["esanjorler"], level="family",
         source="family_specs_quantitative.max_pressure_bar"),
]

GROUPS_HEAT = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "electrical", "name": "Elektrik", "name_en": "Electrical"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
    {"key": "connection", "name": "Bağlantı ve Montaj",
     "name_en": "Connection & Fitting"},
]

# ---------------------------------------------------------------------------
ATTRS_LINING = [
    dict(key="model", desc="Model", desc_en="Model", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model"),
    dict(key="product_label", desc="Desen/Ürün Adı",
         desc_en="Pattern/Product Label", type="char", group="general",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.r_n_i_smi_product_name | "
         "tanim_description"),
    dict(key="alt_code", desc="Alternatif Kod/Ölçü",
         desc_en="Alt. Code/Size", type="char", group="general",
         sets=["ROOT"], level="variant", source="variant_quantitative."),
    dict(key="length_m", desc="Uzunluk (m)", desc_en="Length (m)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.uzunluk_length | uzunl_uk_le_ngth"),
    dict(key="thickness_mm", desc="Kalınlık (mm)", desc_en="Thickness (mm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.kalinlik_thickness"),
    dict(key="width_cm", desc="Genişlik (cm)", desc_en="Width (cm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.geni_li_k_width"),
    dict(key="roll_m2", desc="Rulo (m²)", desc_en="Roll (m²)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.rulo_m_2_roll_m_2"),
    dict(key="dims", desc="Ölçüler", desc_en="Dimensions", type="char",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.l_size"),
    dict(key="package_size", desc="Gramaj/Ambalaj",
         desc_en="Package Size", type="char", group="physical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.gramaj_weight"),
    dict(key="ceramic_bases", desc="Seramik Kodları",
         desc_en="Ceramic Base Codes", type="char", group="technical",
         sets=["havuz-seramikleri-pool-ceramics"], level="variant",
         source="variant_quantitative.serami_k_kodlari_bases"),
]

GROUPS_LINING = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
]

# ---------------------------------------------------------------------------
ATTRS_SPA = [
    dict(key="model", desc="Model", desc_en="Model", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model"),
    dict(key="product_label", desc="Ürün Adı", desc_en="Product Label",
         type="char", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.tanim_description | "
         "r_n_tanimi_description"),
    dict(key="phase", desc="Faz", desc_en="Phase", type="select",
         group="technical", sets=["blowerlar"], level="variant",
         source="variant_quantitative.faz_phase",
         options=["Monofaz (II)", "Trifaz (III)"],
         option_map={"II": "Monofaz (II)", "III": "Trifaz (III)"}),
    dict(key="power_w", desc="Güç (W)", desc_en="Power (W)", type="float",
         group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.watt"),
    dict(key="voltage_v", desc="Voltaj (V)", desc_en="Voltage (V)",
         type="float", group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.watt"),
    dict(key="noise_db", desc="Ses Seviyesi (dB)",
         desc_en="Noise Level (dB)", type="float", group="technical",
         sets=["blowerlar"], level="variant",
         source="variant_quantitative.desi_bel_decibel"),
    dict(key="connection", desc="Bağlantı", desc_en="Connection",
         type="char", group="connection", sets=["ROOT"], level="variant",
         source="variant_quantitative.ba_lanti_connection"),
    dict(key="diameter_mm", desc="Çap (mm)", desc_en="Diameter (mm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.ap_dia"),
]

GROUPS_SPA = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "electrical", "name": "Elektrik", "name_en": "Electrical"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
    {"key": "connection", "name": "Bağlantı ve Montaj",
     "name_en": "Connection & Fitting"},
]

# ---------------------------------------------------------------------------
ATTRS_SAUNA = [
    dict(key="model", desc="Model", desc_en="Model", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model"),
    dict(key="power_kw", desc="Güç (kW)", desc_en="Power (kW)",
         type="float", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_power"),
    dict(key="power_range", desc="Güç Aralığı (kW)",
         desc_en="Power Range (kW)", type="char", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.power_g"),
    dict(key="stone_capacity_kg", desc="Taş Kapasitesi (kg)",
         desc_en="Stone Capacity (kg)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.ta_kapasi_tesi_stone_capacity"),
    dict(key="sauna_volume_m3", desc="Sauna Hacmi (m³)",
         desc_en="Sauna Volume (m³)", type="char", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.sauna_hacmi_sauna_volume"),
    dict(key="max_cabin_volume_m3", desc="Maks. Kabin Hacmi (m³)",
         desc_en="Max. Cabin Volume (m³)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.kabi_n_hacmi_max_cabin_volume_max"),
    dict(key="dims", desc="Ölçüler", desc_en="Dimensions", type="char",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.l_size | "
         "l_ler_uxtxg_dimensions_lxtxw | l_ler_uxdxg_dimensions_lxdxw"),
    dict(key="packing_l", desc="Ambalaj (L)", desc_en="Packing (L)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.ambalaj_packing"),
]

GROUPS_SAUNA = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
]

# ---------------------------------------------------------------------------
ATTRS_FOUNT = [
    dict(key="model", desc="Model", desc_en="Model", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model"),
    dict(key="color", desc="Renk", desc_en="Color", type="select",
         group="general", sets=["lambalar"], level="variant",
         source="variant_quantitative.renk_color",
         options=["Beyaz (White)", "RGB"],
         option_map={"Beyaz White": "Beyaz (White)"}),
    dict(key="lamp_power", desc="Güç/Spec", desc_en="Power/Spec",
         type="char", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_power"),
    dict(key="connection", desc="Bağlantı", desc_en="Connection",
         type="char", group="connection", sets=["ROOT"], level="variant",
         source="variant_quantitative.ba_lanti_connection",
         option_map={'1 1/2"': '1½"', '1 ½"': '1½"'}),
    dict(key="dims", desc="Ölçüler", desc_en="Dimensions", type="char",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.l_size"),
    dict(key="diameter_mm", desc="Çap (mm)", desc_en="Diameter (mm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.ap_dia"),
    dict(key="max_flow_lth", desc="Maks. Debi (L/saat)",
         desc_en="Max. Flow (L/h)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.debi_flow_max"),
    dict(key="head_max_m", desc="Maks. Basma Yüksekliği (m)",
         desc_en="Max. Head (m)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.basma_y_ksekli_i_head_max"),
    dict(key="outlet", desc="Çıkış (Outlet)", desc_en="Outlet",
         type="char", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.iki_outlet"),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_weight"),
]

GROUPS_FOUNT = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
    {"key": "connection", "name": "Bağlantı ve Montaj",
     "name_en": "Connection & Fitting"},
]

# ---------------------------------------------------------------------------
ATTRS_POND = [
    dict(key="model", desc="Ürün Adı", desc_en="Product Name", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model | r_n_adi_name"),
    dict(key="power_w", desc="Güç (W)", desc_en="Power (W)", type="float",
         group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_power"),
    dict(key="rated_power_w", desc="Anma Gücü (W)", desc_en="Rated Power (W)",
         type="float", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.g_de_eri_rated_power"),
    dict(key="max_flow_lth", desc="Maks. Debi (L/saat)",
         desc_en="Max. Flow (L/h)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.debi_max_flow | debi_flow | "
         "debi_flow_max | debi_flow_rate | debi_l_h_flow_l_h"),
    dict(key="head_max_m", desc="Maks. Basma Yüksekliği (m)",
         desc_en="Max. Head (m)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.max_ati_max_head | "
         "basma_y_ksekli_i_head_max | basma_y_ksekli_i_head"),
    dict(key="pond_fish_m3", desc="Balıklı Gölet (m³)",
         desc_en="Pond with Fish (m³)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.balikli_g_let_pond_with_fish"),
    dict(key="pond_normal_m3", desc="Dekoratif Gölet (m³)",
         desc_en="Normal Pond (m³)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.dekorati_f_g_let_normal_pond"),
    dict(key="capacity", desc="Kapasite", desc_en="Capacity", type="char",
         group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.kapasi_te_capacity | "
         "uv_lamba_g_c_uv_lamp_powerfish"),
    dict(key="tank_capacity_l", desc="Tank Kapasitesi (L)",
         desc_en="Tank Capacity (L)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.kapasi_te_tank_capacity | "
         "tank_kapasi_tesi_tank_capacity"),
    dict(key="tank_material", desc="Tank Malzemesi", desc_en="Tank Material",
         type="char", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.tank_ci_nsi_tank_material"),
    dict(key="pressure_bar", desc="Maks. Basınç (bar)",
         desc_en="Max. Pressure (bar)", type="float", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.basin_max_pressure"),
    dict(key="uv_power_w", desc="UV-C Gücü (W)", desc_en="UV-C Power (W)",
         type="float", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.uv_g_c_bulb_power | "
         "uv_c_lamba_uv_c_lamp"),
    dict(key="dims", desc="Ölçüler", desc_en="Dimensions", type="char",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.l_dimensions | "
         "r_n_boyutu_item_size | l_size"),
    dict(key="length_mm", desc="Uzunluk (mm)", desc_en="Length (mm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.uzunluk_production_length"),
    dict(key="lip_length_mm", desc="Dudak Uzunluğu (mm)",
         desc_en="Lip Length (mm)", type="float", group="physical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.a_iz_uzunlu_u_lip_length"),
    dict(key="with_led", desc="LED Durumu", desc_en="With LED",
         type="select", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.ledli_with_led",
         options=["Ledli", "Led'siz"],
         option_map={"+": "Ledli", "x": "Led'siz"}),
    dict(key="cable_m", desc="Kablo (m)", desc_en="Cable (m)",
         type="float", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.kablo_cable"),
    dict(key="voltage", desc="Voltaj", desc_en="Voltage", type="char",
         group="electrical", sets=["ROOT"], level="variant",
         source="variant_quantitative.voltaj_voltage"),
    dict(key="connection", desc="Bağlantı/Adaptör", desc_en="Connection",
         type="char", group="connection", sets=["ROOT"], level="variant",
         source="variant_quantitative.hortum_adapt_r_dimensions | "
         "gi_ri_iki_adapt_r_inlet_outlet_adapter | "
         "uv_c_ba_lanti_connection_uv_c"),
    dict(key="outlet", desc="Çıkış (Outlet)", desc_en="Outlet", type="char",
         group="connection", sets=["ROOT"], level="variant",
         source="variant_quantitative.iki_outlet"),
    dict(key="certificate", desc="Sertifika", desc_en="Certificate",
         type="char", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.serti_fi_ka_certificate"),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_weight"),
]

# ---------------------------------------------------------------------------
ATTRS_OLYMPIC = [
    dict(key="model", desc="Ürün Adı", desc_en="Product Name", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model"),
    dict(key="color", desc="Renk", desc_en="Color", type="select",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.model",
         options=["Kırmızı", "Mavi", "Beyaz"],
         option_map={"kırmızı": "Kırmızı", "mavi": "Mavi",
                     "beyaz": "Beyaz"}),
    dict(key="length_m", desc="Uzunluk (m)", desc_en="Length (m)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.uzunluk_lenght | "
         "uzunluk_mt_length_mt"),
    dict(key="steps", desc="Basamak Sayısı", desc_en="Steps", type="integer",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.basamak_step"),
    dict(key="height_cm", desc="Yükseklik (cm)", desc_en="Height (cm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.y_ksekli_k_cm_height_cm"),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_weight"),
]

GROUPS_OLYMPIC = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
]

# ---------------------------------------------------------------------------
ATTRS_SWIM = [
    dict(key="intensity_levels", desc="Zorluk Seviyesi",
         desc_en="Intensity Levels", type="integer",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.zorluk_sevi_yesi_intensity_levels"),
]

GROUPS_SWIM = [{"key": "general", "name": "Genel", "name_en": "General"}]

# ---------------------------------------------------------------------------
ATTRS_MEMBRANE = [
    dict(key="model", desc="Ürün Adı", desc_en="Product Name", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.r_n_adi_product_name"),
    dict(key="unit", desc="Satış Birimi", desc_en="Sales Unit",
         type="select", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.bi_ri_m_unit",
         options=["m²", "Adet", "MTUL"],
         option_map={"m 2": "m²", "ADET PCS": "Adet", "MTUL": "MTUL"}),
    dict(key="dims", desc="Boyutlar", desc_en="Dimensions", type="char",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.l_ler_dimensions"),
]

GROUPS_MEMBRANE = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
]

# ---------------------------------------------------------------------------
ATTRS_VALVE = [
    dict(key="model", desc="Varyant (Çap/PN/Diş)",
         desc_en="Variant (Dia/PN/Thread)", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.ap_mm_dia_mm | basin_pn | "
         "rp_inch | i_n_inch | tanim_description"),
    dict(key="diameter_mm", desc="Çap (mm)", desc_en="Diameter (mm)",
         type="float", group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.ap_mm_dia_mm"),
    dict(key="pn", desc="Basınç (PN)", desc_en="Pressure (PN)",
         type="float", group="technical", sets=["ROOT"], level="variant",
         source="variant_quantitative.basin_pn"),
    dict(key="threads", desc="Diş Bağlantısı (inç)",
         desc_en="Thread (inch)", type="char", group="technical",
         sets=["ROOT"], level="variant",
         source="variant_quantitative.rp_inch | i_n_inch"),
    dict(key="box_pcs", desc="Koli İçi Adet", desc_en="Box PCS",
         type="integer", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.koli_adet_box_pcs"),
    dict(key="quantity", desc="Miktar", desc_en="Quantity", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.mi_ktar_quantity"),
    dict(key="description", desc="Tanım", desc_en="Description",
         type="char", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.tanim_description"),
    dict(key="weight", nature="native", native_field="weight",
         desc="Ağırlık (kg)", desc_en="Weight (kg)", type="float",
         group="physical", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_irlik_weight"),
]

GROUPS_VALVE = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
]

# ---------------------------------------------------------------------------
ATTRS_SPARE = [
    dict(key="model", desc="Parça Adı", desc_en="Part Name", type="char",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.a_klama_description | "
         "a_klama"),
    dict(key="part_no", desc="Parça No", desc_en="Part No", type="integer",
         group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.par_a | par_a_part | no"),
    dict(key="ref", desc="Referans Kodu", desc_en="Reference Code",
         type="char", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.referans_referance | "
         "referans_reference | referans"),
    dict(key="position", desc="Pozisyon Bilgisi", desc_en="Position Info",
         type="char", group="general", sets=["ROOT"], level="variant",
         source="variant_quantitative.adet_qty | adet"),
]

GROUPS_SPARE = [{"key": "general", "name": "Genel", "name_en": "General"}]

GROUPS_POND = [
    {"key": "general", "name": "Genel", "name_en": "General"},
    {"key": "technical", "name": "Teknik Özellikler",
     "name_en": "Technical Specs"},
    {"key": "electrical", "name": "Elektrik", "name_en": "Electrical"},
    {"key": "physical", "name": "Fiziksel Özellikler",
     "name_en": "Physical Specs"},
    {"key": "connection", "name": "Bağlantı ve Montaj",
     "name_en": "Connection & Fitting"},
]

# ---------------------------------------------------------------------------
# Kategori yapilandirmasi
# ---------------------------------------------------------------------------
CATEGORY_CONFIG = {
    "01": {
        "prefix": "pump",
        "root_set": {"key": "pumps", "name": "Pompalar", "name_en": "Pumps"},
        "attrs": ATTRS_PUMP,
        "groups": GROUPS_PUMP,
        "builder": "pump",
        "name_overrides": {
            "senkron-smart-dalg-pompa-senkron-smart-submersible-pump": (
                "Senkron Smart Dalgıç Pompa", "Senkron Smart Submersible Pump"),
            "l-ks-seri-lux-series": ("Lüks Seri", "Lux Series"),
            "zaman-r-leli-with-timer": ("Zaman Röleli", "With Timer"),
        },
        "series": {
            "senkron-serisi": {
                "name": "Senkron Serisi", "name_en": "Senkron Series",
                "families": ["senkron-1", "senkron-2", "senkron-3",
                             "senkron-jet"],
            },
            "havuz-pompalari": {
                "name": "Havuz Pompaları", "name_en": "Pool Pumps",
                "families": ["trione-storm", "ninfa-nk", "ondina-ok",
                             "s2-model", "koral-kse", "niger-kng", "kapri-kap",
                             "karpa-ka", "prime-kpr", "kan-plus", "kse-vs-150"],
            },
            "hcp-serisi": {
                "name": "HCP Yerleşik Pompalar",
                "name_en": "HCP Built-in Pumps",
                "families": ["hcp-3600", "hcp-3800", "hcp-4000", "hcp-4200"],
            },
            "dalgic-pompalar": {
                "name": "Dalgıç Pompalar", "name_en": "Submersible Pumps",
                "families": [
                    "senkron-smart-dalg-pompa-senkron-smart-submersible-pump"],
            },
            "pompa-setleri": {
                "name": "Pompa Setleri", "name_en": "Pump Sets",
                "families": ["l-ks-seri-lux-series", "zaman-r-leli-with-timer"],
            },
        },
    },
    "02": {
        "prefix": "filter",
        "root_set": {"key": "filters", "name": "Filtreler",
                     "name_en": "Filters"},
        "attrs": ATTRS_FILTER,
        "groups": GROUPS_FILTER,
        "builder": "filter",
        # aile product_id -> kisa set key eslemesi (attrs'da kisa key kullanilir)
        "key_overrides": {
            "lamex-filtreler-lamex-filters": "lamex",
            "rotex-serisi-plastik-filtrelerrotex-series-polyethylen-filte":
                "rotex",
            "woundex-serisi-ws-filtrelerwoundex-series-ws-filters": "woundex",
            "6-yollu-vanalar-6-way-valves": "vana-6y",
            "3-yollu-vanalar3-way-valves": "vana-3y",
            "flowclear-kum-filtresi-flowclear-sand-filter": "flowclear",
            "yedek-kartu-fi-ltre-spare-part-cartridge-filter": "yedek-kartus",
            "25-mi-kron-fi-ltreleme-25-micron-filtration": "25-mikron",
            "kuvars-kum-quartz-sand": "kuvars-kum",
            "zeolit-zeolite": "zeolit-diger",
        },
        "name_overrides": {
            "lamex-filtreler-lamex-filters": ("Lamex® Filtreler",
                                              "Lamex® Filters"),
            "rotex-serisi-plastik-filtrelerrotex-series-polyethylen-filte": (
                "Rotex Serisi Plastik Filtreler",
                "Rotex Series Polyethylene Filters"),
            "woundex-serisi-ws-filtrelerwoundex-series-ws-filters": (
                "Woundex Serisi WS Filtreler", "Woundex Series WS Filters"),
            "6-yollu-vanalar-6-way-valves": ("6 Yollu Vanalar",
                                             "6-Way Valves"),
            "3-yollu-vanalar3-way-valves": ("3 Yollu Vanalar", "3-Way Valves"),
            "flowclear-kum-filtresi-flowclear-sand-filter": (
                "Flowclear Kum Filtresi", "Flowclear Sand Filter"),
            "yedek-kartu-fi-ltre-spare-part-cartridge-filter": (
                "FB Filtre Sistemleri", "FB Filter Systems"),
            "25-mi-kron-fi-ltreleme-25-micron-filtration": (
                "25 Mikron Filtreleme", "25 Micron Filtration"),
            "kuvars-kum-quartz-sand": ("Kuvars Kum", "Quartz Sand"),
            "zeolit-zeolite": ("Zeolit ve Diğer Ürünler",
                               "Zeolite and Other Products"),
        },
        "series": {
            "kum-filtreleri": {
                "name": "Kum Filtreleri", "name_en": "Sand Filters",
                "families": ["lamex", "rotex", "woundex", "flowclear"],
            },
            "kartus-filtreleri": {
                "name": "Kartuş Filtreleri", "name_en": "Cartridge Filters",
                "families": ["25-mikron", "yedek-kartus"],
            },
            "vanalar": {
                "name": "Vanalar", "name_en": "Valves",
                "families": ["vana-6y", "vana-3y"],
            },
            "filtre-medyalari": {
                "name": "Filtre Medyaları", "name_en": "Filter Media",
                "families": ["kuvars-kum", "zeolit-diger"],
            },
        },
    },
    "03": {
        "prefix": "white",
        "root_set": {"key": "white-equipment",
                     "name": "Havuz İçi ve Elektrik",
                     "name_en": "White Equipment & Lighting"},
        "attrs": ATTRS_WHITE,
        "groups": GROUPS_WHITE,
        "builder": "white",
        "name_overrides": {
            "skimmer-skimmers": ("Skimmerlar", "Skimmers"),
            "su-seviye-reg-lat-r-water-level-regulator": (
                "Su Seviye Regülatörü", "Water Level Regulator"),
            "par-56-amp-ller-bulbs-with-led-par-56": (
                "Par 56 Ampüller (LED)", "Par 56 Bulbs with LED"),
            "par-56-powerled-amp-ller-bulbs-with-power-led-par-56": (
                "Par 56 PowerLED Ampüller", "Par 56 PowerLED Bulbs"),
            "stream-equipments": ("Jet Stream Ekipmanları",
                                  "Stream Equipments"),
        },
        "series": {},  # duz yapi
        # kok sete dogrudan baglanan aileler (series yoksa)
        "root_families": [
            "skimmer-skimmers",
            "su-seviye-reg-lat-r-water-level-regulator",
            "par-56-amp-ller-bulbs-with-led-par-56",
            "par-56-powerled-amp-ller-bulbs-with-power-led-par-56",
            "stream-equipments",
        ],
    },
    "04": {
        "prefix": "outdoor",
        "root_set": {"key": "pool-outdoor",
                     "name": "Havuz Kenar Ürünleri",
                     "name_en": "Pool Outdoor Products"},
        "attrs": ATTRS_OUTDOOR,
        "groups": GROUPS_OUTDOOR,
        "builder": "outdoor",
        "name_overrides": {
            "merdivenler-basamaklar": ("Merdivenler ve Basamaklar",
                                       "Ladders & Steps"),
            "du-lar-showers": ("Duşlar", "Showers"),
            "ta-ma-izgaralar-overflow-gratings": (
                "Taşma Izgaraları", "Overflow Gratings"),
        },
        "series": {},  # duz yapi
        "root_families": [
            "merdivenler-basamaklar",
            "du-lar-showers",
            "ta-ma-izgaralar-overflow-gratings",
        ],
    },
    "05": {
        "prefix": "clean",
        "root_set": {"key": "pool-cleaning",
                     "name": "Havuz Temizlik Ürünleri",
                     "name_en": "Pool Cleaning Products"},
        "attrs": ATTRS_CLEAN,
        "groups": GROUPS_CLEAN,
        "builder": "clean",
        "name_overrides": {
            "poolvac-v-flex": ("PoolVac V-Flex", "PoolVac V-Flex"),
            "tigershark": ("TigerShark", "TigerShark"),
            "tigershark-qc": ("TigerShark QC", "TigerShark QC"),
            "tigershark-xl-qc": ("TigerShark XL QC", "TigerShark XL QC"),
            "tigershark-2": ("TigerShark 2", "TigerShark 2"),
            "havuz-robotu-ta-ma-arabas-caddy-card": (
                "Havuz Robotu Taşıma Arabası", "Robot Caddy Cart"),
            "havuz-kep-eleri-leaf-scoops": ("Havuz Kepçeleri", "Leaf Scoops"),
            "havuz-f-r-alar-pool-brushes": ("Havuz Fırçaları",
                                            "Pool Brushes"),
            "magic-eraser-temizlik-s-nger-magic-eraser": (
                "Magic Eraser Temizlik Süngeri",
                "Magic Eraser Cleaning Sponge"),
            "havuz-ve-spa-termometleri": ("Havuz ve Spa Termometreleri",
                                          "Pool & Spa Thermometers"),
        },
        "series": {
            "robotlar": {
                "name": "Havuz Robotları", "name_en": "Pool Robots",
                "families": [
                    "goodrob-easy", "goodrob-easy-plus", "goodrob-maxi",
                    "goodrob-pro", "goodrob-king-500", "goodrob-king-1250",
                    "goodrob-king-serisi-yedek-par-alar", "poolvac-v-flex",
                    "tigershark", "tigershark-qc", "tigershark-xl-qc",
                    "tigershark-2", "havuz-robotu-ta-ma-arabas-caddy-card",
                ],
            },
            "kepce-fircalar": {
                "name": "Kepçe ve Fırçalar",
                "name_en": "Leaf Scoops & Brushes",
                "families": ["havuz-kep-eleri-leaf-scoops",
                             "havuz-f-r-alar-pool-brushes"],
            },
            "termometreler": {
                "name": "Havuz ve Spa Termometreleri",
                "name_en": "Pool & Spa Thermometers",
                "families": ["havuz-ve-spa-termometleri"],
            },
        },
        "root_families": ["magic-eraser-temizlik-s-nger-magic-eraser"],
    },
    "06": {
        "prefix": "disinf",
        "root_set": {"key": "pool-disinfection",
                     "name": "Havuz Dezenfeksiyon Ekipmanları",
                     "name_en": "Pool Disinfection Equipment"},
        "attrs": ATTRS_DISINF,
        "groups": GROUPS_DISINF,
        "builder": "disinf",
        "name_overrides": {
            "5-year-guarantee": ("UV Sistemleri (MPL)", "UV Systems (MPL)"),
            "end-stri-yel-uv-industrial-uv": ("Endüstriyel UV",
                                              "Industrial UV"),
            "uv-benefits-for-public-pools-and-water-parks": (
                "Havuz UV Sistemleri (FW)", "Pool UV Systems (FW)"),
            "sistem-ba-lant-emas-system-connection-diagram": (
                "Kontrol Sistemleri (KLX)", "Control Systems (KLX)"),
            "max-veri-m-max-efficiency": ("Max. Verim Serisi",
                                          "Max. Efficiency Series"),
            "havuz-y-neti-mi-pool-manager": (
                "Havuz Yönetimi (Pool Manager)", "Pool Manager"),
            "wifi-i-le-hi-jyen-wi-fi-hygiene": ("Wi-Fi ile Hijyen",
                                                "Wi-Fi Hygiene"),
            "6-si-bi-r-arada-6-in-one": ("6'sı Bir Arada (6 in One)",
                                         "6 in One"),
            "mini-dev-mighty-mini": ("Mini Dev (Mighty Mini)",
                                     "Mighty Mini"),
            "akilli-klor-pool-manager": ("Akıllı Klor (Pool Manager)",
                                         "Smart Chlorine (Pool Manager)"),
            "deni-z-dayanimi-sea-resistant": ("Deniz Dayanımlı",
                                              "Sea Resistant"),
            "uv-c-teknoloji-si-uv-c-technology": ("UV-C Teknolojisi",
                                                  "UV-C Technology"),
            "fotokatalitik-oksidasyon-photocatalytic-oxidation": (
                "Fotokatalitik Oksidasyon", "Photocatalytic Oxidation"),
            "ozon-jenerat-rleri-ozone-generators": ("Ozon Jeneratörleri",
                                                    "Ozone Generators"),
        },
        "series": {
            "uv-sistemleri": {
                "name": "UV Sistemleri", "name_en": "UV Systems",
                "families": [
                    "5-year-guarantee",
                    "end-stri-yel-uv-industrial-uv",
                    "uv-benefits-for-public-pools-and-water-parks",
                    "uv-c-teknoloji-si-uv-c-technology",
                    "fotokatalitik-oksidasyon-photocatalytic-oxidation",
                ],
            },
            "klor-ureticileri": {
                "name": "Klor Üreticileri", "name_en": "Chlorine Generators",
                "families": [
                    "sistem-ba-lant-emas-system-connection-diagram",
                    "havuz-y-neti-mi-pool-manager", "automation",
                    "s-serisi-s-series", "deni-z-dayanimi-sea-resistant",
                    "mini-dev-mighty-mini", "6-si-bi-r-arada-6-in-one",
                    "wifi-i-le-hi-jyen-wi-fi-hygiene",
                    "akilli-klor-pool-manager",
                ],
            },
            "dozaj-panelleri": {
                "name": "Dozaj Pompaları ve Panelleri",
                "name_en": "Dosing Pumps & Panels",
                "families": [
                    "kompact-model", "kompact-drp-200-model",
                    "kompact-drp-200-model-set", "trp-603-model",
                    "tekna-evo-aks-model", "pool-dose-panel",
                    "kemidose-panel", "evo-basic-panel",
                    "aks-800-803-panel", "k-800-cl-panel",
                    "akl-800-803-panel",
                    "poolone-peristaltik-dozaj-pompas-poolone-"
                    "peristaltic-dosing-",
                ],
            },
            "dozaj-aksesuarlari": {
                "name": "Dozaj Aksesuarları",
                "name_en": "Dosing Accessories",
                "families": [
                    "emi-filtresi-ve-ekvalfi-suction-filter-and-check-valve",
                    "basma-ekvalfi-discharge-check-valve",
                    "kalibrasyon-s-v-lar-calibration-fluid-kit",
                    "ph-probu-ph-probe", "orp-elektrotu-orp-electrode",
                    "seviye-sens-r-level-sensor",
                    "prob-tutucular-probe-holder",
                    "klorinat-r-chlorinator", "chemical-mixing-tank",
                    "motorized-mixing-tank", "chemical-mixer", "dispenser",
                ],
            },
            "hijyen-test": {
                "name": "Hijyen ve Test Ürünleri",
                "name_en": "Hygiene & Test Products",
                "families": [
                    "ayak-y-kama-teknesi-foot-washing-basin",
                    "ph-otomatik-su-kalite-dedekt-r-oh-automatic-water-"
                    "quality-de",
                    "test-kitleri-test-kits", "test-ka-d-test-strips",
                    "test-kit-dpd1-and-phenol-tablets",
                    "test-kit-with-liquid-set", "granular-salt",
                ],
            },
        },
        "root_families": [
            "ozon-jenerat-rleri-ozone-generators",
            "max-veri-m-max-efficiency",
        ],
    },
    "07": {
        "prefix": "chem",
        "root_set": {"key": "pool-chemicals",
                     "name": "Havuz Kimyasal Ürünleri",
                     "name_en": "Pool Chemical Products"},
        "attrs": ATTRS_CHEM,
        "groups": GROUPS_CHEM,
        "builder": "chem",
        "name_overrides": {
            "gc-56-granular-chlorine": ("Granül Klor %56 (GC 56)",
                                        "Granular Chlorine 56% (GC 56)"),
            "gc-90-granular-chlorine": ("Granül Klor %90 (GC 90)",
                                        "Granular Chlorine 90% (GC 90)"),
            "the-secret-weapon-of-indoor-pools": (
                "Kapalı Havuz Kimyasalı (Secret Weapon)",
                "Indoor Pool Chemical (Secret Weapon)"),
            "tc-200-chlorine-tablet": ("Klor Tableti (TC 200)",
                                       "Chlorine Tablet (TC 200)"),
            "b-t-n-bakim-complete-care": ("Bütün Bakım (Complete Care)",
                                          "Complete Care"),
            "pr-ph-reducer": ("pH Düşürücü (PR −)", "pH Reducer (PR −)"),
            "pr-ph-increaseer": ("pH Yükseltici (PR +)",
                                 "pH Increaser (PR +)"),
            "lac-liquid-algaecide": ("Sıvı Yosun Giderici (LAC)",
                                     "Liquid Algaecide (LAC)"),
            "cleaner-s-power": ("Temizlik Kimyasalı (Cleaner's Power)",
                                "Cleaner's Power"),
            "lb-liquid-brighener": ("Sıvı Parlatıcı (LB)",
                                    "Liquid Brightener (LB)"),
            "sc-liquid-surface-cleaner": ("Sıvı Yüzey Temizleyici (SC)",
                                          "Liquid Surface Cleaner (SC)"),
        },
        "series": {
            "klor-urunleri": {
                "name": "Klor Ürünleri", "name_en": "Chlorine Products",
                "families": [
                    "gc-56-granular-chlorine", "gc-90-granular-chlorine",
                    "tc-200-chlorine-tablet",
                    "the-secret-weapon-of-indoor-pools",
                ],
            },
            "ph-kontrol": {
                "name": "pH Kontrol", "name_en": "pH Control",
                "families": ["pr-ph-reducer", "pr-ph-increaseer"],
            },
            "temizlik-bakim": {
                "name": "Temizlik ve Bakım Kimyasalları",
                "name_en": "Cleaning & Maintenance Chemicals",
                "families": [
                    "lac-liquid-algaecide", "cleaner-s-power",
                    "lb-liquid-brighener", "sc-liquid-surface-cleaner",
                    "b-t-n-bakim-complete-care",
                ],
            },
        },
    },
    "08": {
        "prefix": "heat",
        "root_set": {"key": "pool-heating",
                     "name": "Havuz Isıtma ve Nem Alma Ürünleri",
                     "name_en": "Pool Heating and Dehumidification"},
        "attrs": ATTRS_HEAT,
        "groups": GROUPS_HEAT,
        "builder": "heat",
        "name_overrides": {
            "6x-efficiency": ("6x Verimli Isı Pompası",
                              "6x Efficiency Heat Pump"),
            "residential-inverter": ("Konut Tipi İnverter",
                                     "Residential Inverter"),
            "smart-inverter": ("Smart İnverter", "Smart Inverter"),
            "sfs-joey": ("SFS Joey", "SFS Joey"),
            "plakal-e-anj-r-plate-heat-exchanger": ("Plakalı Eşanjör",
                                                    "Plate Heat Exchanger"),
            "g2c-heat-exchanger": ("G2C Eşanjör", "G2C Heat Exchanger"),
            "g2-multi-tubular": ("G2 Multi Tubular Eşanjör",
                                 "G2 Multi Tubular Heat Exchanger"),
        },
        "series": {
            "isi-pompalari": {
                "name": "Isı Pompaları", "name_en": "Heat Pumps",
                "families": [
                    "nano-spa-model", "flowline-2", "evolution-2",
                    "optima-compact", "sfs-joey", "titan-optima",
                    "heatsmart-koolsmart", "pool-smart-plus",
                    "6x-efficiency", "smart-inverter",
                    "residential-inverter",
                ],
            },
            "esanjorler": {
                "name": "Eşanjörler", "name_en": "Heat Exchangers",
                "families": [
                    "plakal-e-anj-r-plate-heat-exchanger",
                    "g2c-heat-exchanger", "g2-multi-tubular",
                ],
            },
        },
    },
    "09": {
        "prefix": "lining",
        "root_set": {"key": "pool-lining",
                     "name": "Havuz İçi ve Kenar Kaplama Ürünleri",
                     "name_en": "Pool Indoor and Outdoor Products"},
        "attrs": ATTRS_LINING,
        "groups": GROUPS_LINING,
        "builder": "lining",
        "model_keys": ["model", "r_n_i_smi_product_name",
                       "tanim_description"],
        "name_overrides": {
            "liner-pool-cover": ("Liner Kaplama", "Liner Pool Cover"),
            "pvc-kapl-metal-liner-montaj-tas-d-z-pvc-coated-metal-straigh": (
                "PVC Kaplı Metal Liner Montaj Çıtası (Düz)",
                "PVC Coated Metal Liner Strip (Straight)"),
            "pvc-kapl-metal-liner-tas-k-vr-lm-pvc-coated-metal-liner-fixi": (
                "PVC Kaplı Metal Liner Çıtası (Kıvrılmış)",
                "PVC Coated Metal Liner Strip (Curved)"),
            "liner-kenar-tutama-liner-handle": ("Liner Kenar Tutamağı",
                                                "Liner Handle"),
            "liner-liquid-transparent-liner-liquid-blue": (
                "Liner Likit", "Liner Liquid"),
            "liner-geotextile": ("Liner Geotextil", "Liner Geotextile"),
            "liner-vinly-pool-repair-kit": ("Liner Vinil Onarım Kiti",
                                            "Vinyl Pool Repair Kit"),
            "tutamak-kobalt-handle-cobalt": ("Tutamak Kobalt",
                                             "Cobalt Handle"),
            "oluklu-tutamak-kobalt-grooved-handle-cobalt": (
                "Oluklu Tutamak Kobalt", "Grooved Handle Cobalt"),
            "b-y-k-tutamak-kobalt-big-handle-cobalt": (
                "Büyük Tutamak Kobalt", "Big Handle Cobalt"),
            "oluklu-b-y-k-tutamak-kobalt-grooved-big-handle-cobalt": (
                "Oluklu Büyük Tutamak Kobalt",
                "Grooved Big Handle Cobalt"),
            "profilli-b-y-k-tutamak-kobalt-big-handle-big-profile-cobalt": (
                "Profilli Büyük Tutamak Kobalt",
                "Big Handle With Profile Cobalt"),
            "profilli-oluklu-b-y-k-tutamak-kobalt-big-handle-with-profile": (
                "Profilli Oluklu Büyük Tutamak Kobalt",
                "Grooved Big Handle With Profile Cobalt"),
            "s-rs-z-kaymaz-unglazed-antisip": ("Sırsız Kaymaz Antisip",
                                               "Unglazed Antisip"),
            "profilli-s-rs-z-kaymaz-unglazed-antisip-with-profile": (
                "Profilli Sırsız Kaymaz Antisip",
                "Unglazed Antisip With Profile"),
            "d-k-e-external-corner-cobalt": ("Dış Köşe Kobalt",
                                             "External Corner Cobalt"),
            "i-k-e-internal-corner-cobalt": ("İç Köşe Kobalt",
                                             "Internal Corner Cobalt"),
        },
        "series": {
            "liner-urunleri": {
                "name": "Liner Ürünleri", "name_en": "Liner Products",
                "families": [
                    "liner-pool-cover",
                    "pvc-kapl-metal-liner-montaj-tas-d-z-pvc-coated-metal-"
                    "straigh",
                    "pvc-kapl-metal-liner-tas-k-vr-lm-pvc-coated-metal-"
                    "liner-fixi",
                    "liner-kenar-tutama-liner-handle",
                    "liner-liquid-transparent-liner-liquid-blue",
                    "liner-geotextile", "liner-vinly-pool-repair-kit",
                ],
            },
            "kenar-tutamaklar": {
                "name": "Kenar Ürünleri ve Tutamaklar",
                "name_en": "Edging & Handles",
                "families": [
                    "tutamak-kobalt-handle-cobalt",
                    "oluklu-tutamak-kobalt-grooved-handle-cobalt",
                    "b-y-k-tutamak-kobalt-big-handle-cobalt",
                    "oluklu-b-y-k-tutamak-kobalt-grooved-big-handle-cobalt",
                    "profilli-b-y-k-tutamak-kobalt-big-handle-big-profile-"
                    "cobalt",
                    "profilli-oluklu-b-y-k-tutamak-kobalt-big-handle-with-"
                    "profile",
                    "s-rs-z-kaymaz-unglazed-antisip",
                    "profilli-s-rs-z-kaymaz-unglazed-antisip-with-profile",
                    "d-k-e-external-corner-cobalt",
                    "i-k-e-internal-corner-cobalt",
                ],
            },
        },
        "root_families": ["havuz-seramikleri-pool-ceramics"],
    },
    "10": {
        "prefix": "spa",
        "root_set": {"key": "jacuzzi-spa",
                     "name": "Jakuzi ve Spa Ürünleri",
                     "name_en": "Jacuzzi and Spa Products"},
        "attrs": ATTRS_SPA,
        "groups": GROUPS_SPA,
        "builder": "spa",
        "model_keys": ["model", "tanim_description"],
        "name_overrides": {
            "32-mm-hava-ve-32-su-k-l-32-mm-air-and-32-water-outlet": (
                "Ø32 Hava ve Ø32 Su Çıkışlı Jet",
                "Ø32 Air and Ø32 Water Jet"),
            "32-mm-hava-ve-50-su-k-l-32-mm-air-and-50-water-outlet": (
                "Ø32 Hava ve Ø50 Su Çıkışlı Jet",
                "Ø32 Air and Ø50 Water Jet"),
            "damla-model-jakuzi-seti-face-eyeball-spa-jet": (
                "Damla Model Jakuzi Seti (Face Eyeball)",
                "Face Eyeball Spa Jet Set"),
            "ok-du-seti-barb-jet": ("Şok Duş Seti (Barb Jet)",
                                    "Shock Shower Set (Barb Jet)"),
            "d-ner-tip-11-jet-contas-yla-11-face-swirl-jet-with-gasket": (
                "Döner Tip Ø11 ½\" Jet (Contalı)",
                "Rotary Ø11 ½\" Jet with Seal"),
            "d-z-g-r-n-ml-standart-jet-smooth-face-swirl-jet": (
                "Düz Görünümlü (Standart) Jet",
                "Smooth Face (Swirl) Jet"),
            "d-ner-tip-jet-rotary-type-jet": ("Döner Tip Jet",
                                              "Rotary Type Jet"),
            "damla-model-d-ner-jet-drop-type-adjustable-jet": (
                "Damla Model Döner Jet", "Drop Type Adjustable Jet"),
            "pnomatik-buton-pneumatic-button": ("Pnömatik Buton",
                                                "Pneumatic Button"),
            "hava-ayar-butonu-air-adjustment-button": (
                "Hava Ayar Butonu", "Air Adjustment Button"),
            "9-delikli-blower-nozulu-9-hole-nozzle": (
                "9 Delikli Blower Nozulu", "9 Hole Nozzle"),
            "blower-nozulu-air-blower-nozzle": ("Blower Nozulu",
                                                "Air Blower Nozzle"),
            "jakuzi-emi-s-zge-leri-50-mm-jacuzzi-drains-50-mm": (
                "Jakuzi Emiş Süzgeçleri 50 mm",
                "Jacuzzi Drains 50 mm"),
            "jakuzi-kollekt-rleri-jacuzzi-collectors": (
                "Jakuzi Kollektörleri", "Jacuzzi Collectors"),
            "jakuzi-hortumlar-jacuzzi-hoses": ("Jakuzi Hortumları",
                                               "Jacuzzi Hoses"),
            "jakuzi-hava-blower-jacuzzi-air-blower": (
                "Jakuzi Hava Blower'ı", "Jacuzzi Air Blower"),
            "blower-wf-model": ("Blower WF Model", "Blower WF Model"),
            "blower-yedekleri-blower-parts": ("Blower Yedekleri",
                                              "Blower Parts"),
        },
        "series": {
            "jetler": {
                "name": "Jakuzi Jetleri", "name_en": "Spa Jets",
                "families": [
                    "32-mm-hava-ve-32-su-k-l-32-mm-air-and-32-water-outlet",
                    "damla-model-jakuzi-seti-face-eyeball-spa-jet",
                    "ok-du-seti-barb-jet",
                    "d-ner-tip-11-jet-contas-yla-11-face-swirl-jet-with-gasket",
                    "32-mm-hava-ve-50-su-k-l-32-mm-air-and-50-water-outlet",
                    "d-z-g-r-n-ml-standart-jet-smooth-face-swirl-jet",
                    "d-ner-tip-jet-rotary-type-jet",
                    "damla-model-d-ner-jet-drop-type-adjustable-jet",
                ],
            },
            "butonlar-nozullar": {
                "name": "Butonlar ve Nozullar",
                "name_en": "Buttons & Nozzles",
                "families": [
                    "pnomatik-buton-pneumatic-button",
                    "hava-ayar-butonu-air-adjustment-button",
                    "9-delikli-blower-nozulu-9-hole-nozzle",
                    "blower-nozulu-air-blower-nozzle",
                ],
            },
            "su-hatti": {
                "name": "Emiş, Kollektör ve Hortumlar",
                "name_en": "Drains, Collectors & Hoses",
                "families": [
                    "jakuzi-emi-s-zge-leri-50-mm-jacuzzi-drains-50-mm",
                    "jakuzi-kollekt-rleri-jacuzzi-collectors",
                    "jakuzi-hortumlar-jacuzzi-hoses",
                ],
            },
            "blowerlar": {
                "name": "Blowerlar ve Yedekleri",
                "name_en": "Blowers & Parts",
                "families": [
                    "jakuzi-hava-blower-jacuzzi-air-blower",
                    "blower-wf-model", "blower-yedekleri-blower-parts",
                ],
            },
        },
    },
    "11": {
        "prefix": "sauna",
        "root_set": {"key": "sauna-steam",
                     "name": "Sauna ve Buhar Ürünleri",
                     "name_en": "Sauna and Steam Products"},
        "attrs": ATTRS_SAUNA,
        "groups": GROUPS_SAUNA,
        "builder": "sauna",
        "name_overrides": {
            "mw-model": ("MW Model", "MW Model"),
            "kumanda-panolar-g-kontrol-panel": (
                "Kumanda Panoları ve Güç Kontrol Paneli",
                "Controls & Power Control Panels"),
            "sauna-cam-kap-s-security-glass-door-for-saunas": (
                "Sauna Cam Kapısı", "Security Glass Door for Saunas"),
            "sauna-kap-s-ah-ap-tutamak-seti-wooden-handle-set-for-saunas-": (
                "Sauna Kapısı Ahşap Tutamak Seti",
                "Wooden Handle Set for Saunas"),
            "abachi-lambri-paneli-abachi-wall-panel": (
                "Abachi Lambri Paneli", "Abachi Wall Panel"),
            "abachi-ranzal-k-paneli-abachi-sitting-panel": (
                "Abachi Ranzalık Paneli", "Abachi Sitting Panel"),
            "fin-ladini-lambri-paneli-spruce-wall-panel": (
                "Fin Ladini Lambri Paneli", "Spruce Wall Panel"),
            "fin-am-lambri-budaks-z-paneli-pipe-wall-panel": (
                "Fin Çamı Lambri Budaksız Paneli",
                "Pine Wall Panel (Knotless)"),
            "ftsg-model-buhar-jenerat-r-steam-generations-ftsg-model": (
                "FTSG Model Buhar Jeneratörü", "Steam Generator FTSG"),
            "deluxe-model-buhar-jenerat-r-steam-generations-deluxe-model": (
                "Deluxe Model Buhar Jeneratörü", "Steam Generator Deluxe"),
        },
        "series": {
            "isiticilar-kumandalar": {
                "name": "Sauna Isıtıcıları ve Kumandalar",
                "name_en": "Sauna Heaters & Controls",
                "families": [
                    "mw-model", "ftn-model", "club-model", "round-model",
                    "combi-model", "kumanda-panolar-g-kontrol-panel",
                ],
            },
            "lambri-panelleri": {
                "name": "Lambri Panelleri", "name_en": "Wall Panels",
                "families": [
                    "abachi-lambri-paneli-abachi-wall-panel",
                    "abachi-ranzal-k-paneli-abachi-sitting-panel",
                    "fin-ladini-lambri-paneli-spruce-wall-panel",
                    "fin-am-lambri-budaks-z-paneli-pipe-wall-panel",
                ],
            },
            "buhar-jeneratori": {
                "name": "Buhar Jeneratörleri", "name_en": "Steam Generators",
                "families": [
                    "ftsg-model-buhar-jenerat-r-steam-generations-ftsg-model",
                    "deluxe-model-buhar-jenerat-r-steam-generations-deluxe-"
                    "model",
                ],
            },
            "kapilar-aksesuarlar": {
                "name": "Kapılar ve Aksesuarlar",
                "name_en": "Doors & Accessories",
                "families": [
                    "sauna-cam-kap-s-security-glass-door-for-saunas",
                    "sauna-kap-s-ah-ap-tutamak-seti-wooden-handle-set-for-"
                    "saunas-",
                    "sauna-aksesuarlar-sauna-accessories",
                ],
            },
        },
    },
    "12": {
        "prefix": "fount",
        "root_set": {"key": "fountain",
                     "name": "Süs Havuzu Ürünleri",
                     "name_en": "Fountain Products"},
        "attrs": ATTRS_FOUNT,
        "groups": GROUPS_FOUNT,
        "builder": "fount",
        "name_overrides": {
            "k-p-k-nozul-foam-nozzle": ("Köpük Nozulu", "Foam Nozzle"),
            "cascade-nozul-cascade-nozzle": ("Kaskad Nozulu",
                                             "Cascade Nozzle"),
            "komet-jet-oynar-ba-l-nozul-comet-jet-adjustable-nozzle": (
                "Komet Jet Oynar Başlı Nozul",
                "Comet Jet Adjustable Nozzle"),
            "emsiye-f-skiye-nozul-water-bell-nozzle": (
                "Şemsiye Fıskiye Nozulu", "Water Bell Nozzle"),
            "emsiye-f-skiye-nozul-brass-water-bell-nozzle": (
                "Şemsiye Fıskiye Nozulu (Pirinç)",
                "Brass Water Bell Nozzle"),
            "yar-m-emsiye-f-skiye-nozul-half-water-bell-nozzle": (
                "Yarım Şemsiye Fıskiye Nozulu", "Half Water Bell Nozzle"),
            "yelpaze-nozul-finger-nozzle": ("Yelpaze Nozul",
                                            "Finger Nozzle"),
            "film-yelpaze-nozul-fan-jet-nozzle": ("Film Yelpaze Nozul",
                                                  "Fan Jet Nozzle"),
            "volkan-nozul-volcano-nozzle": ("Volkan Nozul",
                                            "Volcano Nozzle"),
            "gonca-nozul-bud-nozzle": ("Gonca Nozul", "Bud Nozzle"),
            "papatya-nozul-daisy-nozzle": ("Papatya Nozul",
                                           "Daisy Nozzle"),
            "i-ek-nozul-flower-nozzle": ("Çiçek Nozul", "Flower Nozzle"),
            "su-topac-nozul-water-spinner-nozzle": (
                "Su Topaç Nozul", "Water Spinner Nozzle"),
            "su-k-resi-nozul-water-sphere-nozzle": (
                "Su Küresi Nozul", "Water Sphere Nozzle"),
            "y-ld-z-f-skiye-nozul-star-nozzle": ("Yıldız Fıskiye Nozul",
                                                 "Star Nozzle"),
            "ledli-lambalar-led-lights": ("LEDli Lambalar", "LED Lights"),
            "halka-s-s-havuzu-lambalar-ring-fountain-led-lights": (
                "Halka Süs Havuzu Lambaları",
                "Ring Fountain LED Lights"),
            "kobra-model-cobra-model": ("Kobra Model", "Cobra Model"),
            "maui-model-maui-model": ("Maui Model", "Maui Model"),
            "salyangoz-model-snail-model": ("Salyangoz Model",
                                            "Snail Model"),
            "yunus-model-dolphin-model": ("Yunus Model", "Dolphin Model"),
            "decorative-flow": ("Dekoratif Akış", "Decorative Flow"),
        },
        "series": {
            "nozullar": {
                "name": "Süs Havuzu Nozulları", "name_en": "Fountain Nozzles",
                "families": [
                    "k-p-k-nozul-foam-nozzle",
                    "cascade-nozul-cascade-nozzle",
                    "komet-jet-oynar-ba-l-nozul-comet-jet-adjustable-nozzle",
                    "emsiye-f-skiye-nozul-water-bell-nozzle",
                    "emsiye-f-skiye-nozul-brass-water-bell-nozzle",
                    "yar-m-emsiye-f-skiye-nozul-half-water-bell-nozzle",
                    "yelpaze-nozul-finger-nozzle",
                    "film-yelpaze-nozul-fan-jet-nozzle",
                    "volkan-nozul-volcano-nozzle",
                    "gonca-nozul-bud-nozzle",
                    "papatya-nozul-daisy-nozzle",
                    "i-ek-nozul-flower-nozzle",
                    "su-topac-nozul-water-spinner-nozzle",
                    "su-k-resi-nozul-water-sphere-nozzle",
                    "y-ld-z-f-skiye-nozul-star-nozzle",
                ],
            },
            "lambalar": {
                "name": "Süs Havuzu Lambaları",
                "name_en": "Fountain LED Lights",
                "families": [
                    "ledli-lambalar-led-lights",
                    "halka-s-s-havuzu-lambalar-ring-fountain-led-lights",
                ],
            },
            "fontlar": {
                "name": "Dekoratif Fontlar",
                "name_en": "Decorative Fountains",
                "families": [
                    "kobra-model-cobra-model", "maui-model-maui-model",
                    "salyangoz-model-snail-model",
                    "yunus-model-dolphin-model",
                ],
            },
        },
        "root_families": ["decorative-flow"],
    },
    "13": {
        "prefix": "pond",
        "root_set": {"key": "garden-pond",
                     "name": "Bahçe ve Gölet Ürünleri",
                     "name_en": "Garden and Pond Products"},
        "attrs": ATTRS_POND,
        "groups": GROUPS_POND,
        "builder": "pond",
        "model_keys": ["model", "r_n_adi_name"],
        "name_overrides": {
            "g-venli-fi-lrasyon-reliable-filtration": (
                "Gölet Filtresi (Biyolojik)", "Pond Bio Filter"),
            "basin-li-fi-lrasyon-pressurized-filtration": (
                "Basınçlı Gölet Filtresi (UV-C)",
                "Pressurized Pond Filter with UV"),
            "uv-g-vencesi-uv-assurance": ("Gölet UV Dezenfektanı",
                                          "Pond UV Clarifier"),
            "enerji-tasarrufu-energy-saving": (
                "Gölet Pompası (Enerji Tasarruflu)",
                "Pond Pump (Energy Saving)"),
            "tamamen-su-ge-i-rmez-motor-sealed-waterproof": (
                "Gölet Pompası (Su Geçirmez Motor)",
                "Pond Pump (Waterproof Motor)"),
            "temi-z-si-rk-lasyon-clean-circulation": (
                "Gölet Pompa ve UV Kombinleri",
                "Pond Pump & UV Combos"),
            "senkron-smart": ("Senkron Smart Gölet Pompası",
                              "Senkron Smart Pond Pump"),
            "trione": ("Trione Gölet Pompası", "Trione Pond Pump"),
            "suni-ah-ap-taban-wooden-base": (
                "Bahçe ve Güneş Duşları", "Garden & Solar Showers"),
            "esteti-k-aki-aesthetic-flow": ("Su Perdesi Kanalları",
                                            "Waterfall Channels"),
        },
        "series": {
            "golet-filtreleri": {
                "name": "Gölet Filtreleri", "name_en": "Pond Filters",
                "families": [
                    "g-venli-fi-lrasyon-reliable-filtration",
                    "basin-li-fi-lrasyon-pressurized-filtration",
                    "uv-g-vencesi-uv-assurance",
                ],
            },
            "golet-pompalari": {
                "name": "Gölet Pompaları", "name_en": "Pond Pumps",
                "families": [
                    "enerji-tasarrufu-energy-saving",
                    "tamamen-su-ge-i-rmez-motor-sealed-waterproof",
                    "temi-z-si-rk-lasyon-clean-circulation",
                    "senkron-smart", "trione",
                ],
            },
        },
        "root_families": [
            "esteti-k-aki-aesthetic-flow",
            "suni-ah-ap-taban-wooden-base",
        ],
    },
    "14": {
        "prefix": "olympic",
        "root_set": {"key": "olympic-pool",
                     "name": "Olimpik Havuz Ürünleri",
                     "name_en": "Olympic Pool Products"},
        "attrs": ATTRS_OLYMPIC,
        "groups": GROUPS_OLYMPIC,
        "builder": "olympic",
        "model_keys": ["model"],
        "name_overrides": {
            "4-5-6-number-products": (
                "Kulvar Bağlantı ve Topları", "Lane Connectors & Balls"),
            "kulvar-seperat-r-y-zd-r-c-ve-toplar-lane-separator-"
            "floater-a": ("Kulvar Ayracı", "Lane Ropes"),
            "sabit-atlama-platformu-fixed-starting-blocks": (
                "Sabit Atlama Platformu", "Fixed Starting Block"),
            "sabit-2-basamakl-atlama-platformu-fixed-2-step-"
            "starting-plat": ("Sabit 2 Basamaklı Atlama Platformu",
                              "Fixed 2-Step Starting Block"),
            "ayarlanabilir-atlama-platformu-adjustable-starting-"
            "blocks": ("Ayarlanabilir Atlama Platformu",
                       "Adjustable Starting Block"),
            "beton-tip-ankraj-concrete-type-anchor": (
                "Beton Tip Ankraj", "Concrete Type Anchor"),
            "fil-sava-tip-ankraj-finnish-inclined-type-anchor": (
                "Fil Ayağı Tip Ankraj", "Finnish Inclined Anchor"),
            "seperat-r-ankra-bronz-d-k-m-kromajl-bronze-casting-and-"
            "chrom": ("Kulvar Ayracı Ankrajı (Bronz Döküm, Kromajlı)",
                      "Lane Anchor (Bronze Casting, Chromed)"),
            "gerdirme-ubu-u-double-edged-hooked-brass": (
                "Gerdirme Çubuğu (Pirinç)", "Tension Rod (Brass)"),
            "seperat-r-gerdirici-bronz-d-k-m-kromajl-spring-model-"
            "sunborn": ("Kulvar Gerdiricisi (Yaylı, Bronz Döküm)",
                        "Lane Tensioner (Spring, Bronze Casting)"),
            "seperat-r-kancas-makaral-float-line-hook": (
                "Kulvar Kancası (Makaralı)", "Float Line Hook (Pulley)"),
            "ask-kancas-emniyet-mandal-hook-with-safety-latch": (
                "Aski Kancası (Emniyet Mandalı)",
                "Hanging Hook (Safety Latch)"),
            "su-st-ba-lama-halkas-overhead-bracket": (
                "Tavan Bağlama Halkası", "Overhead Bracket"),
            "kulvar-sarma-tamburu-float-lines-roller": (
                "Kulvar Sarma Tamburu", "Float Lines Roller"),
            "yanl-k-i-kaz-dire-i-false-start-indicator": (
                "Yanlış Başlama Direği", "False Start Indicator"),
            "geri-d-n-i-kaz-dire-i-backstroke-turn-indicators": (
                "Sırt Üstü Dönüş Direği", "Backstroke Turn Indicator"),
            "d-n-paneli-ve-deste-i-return-panel-and-bracket": (
                "Dönüş Paneli ve Desteği", "Return Panel and Bracket"),
            "can-kurtaran-hakem-koltu-u-life-guard-chair": (
                "Can Kurtaran Hakem Koltuğu", "Life Guard Chair"),
        },
        "series": {
            "kulvar-sistemleri": {
                "name": "Kulvar Sistemleri", "name_en": "Lane Systems",
                "families": [
                    "4-5-6-number-products",
                    "kulvar-seperat-r-y-zd-r-c-ve-toplar-lane-"
                    "separator-floater-a",
                    "kulvar-sarma-tamburu-float-lines-roller",
                    "seperat-r-ankra-bronz-d-k-m-kromajl-bronze-casting-"
                    "and-chrom",
                    "gerdirme-ubu-u-double-edged-hooked-brass",
                    "seperat-r-gerdirici-bronz-d-k-m-kromajl-spring-"
                    "model-sunborn",
                    "seperat-r-kancas-makaral-float-line-hook",
                    "ask-kancas-emniyet-mandal-hook-with-safety-latch",
                    "su-st-ba-lama-halkas-overhead-bracket",
                ],
            },
            "atlama-platformlari": {
                "name": "Atlama Platformları",
                "name_en": "Starting Blocks",
                "families": [
                    "sabit-atlama-platformu-fixed-starting-blocks",
                    "sabit-2-basamakl-atlama-platformu-fixed-2-step-"
                    "starting-plat",
                    "ayarlanabilir-atlama-platformu-adjustable-"
                    "starting-blocks",
                    "beton-tip-ankraj-concrete-type-anchor",
                    "fil-sava-tip-ankraj-finnish-inclined-type-anchor",
                ],
            },
            "yaris-ekipmanlari": {
                "name": "Yarış Ekipmanları",
                "name_en": "Racing Equipment",
                "families": [
                    "yanl-k-i-kaz-dire-i-false-start-indicator",
                    "geri-d-n-i-kaz-dire-i-backstroke-turn-indicators",
                    "d-n-paneli-ve-deste-i-return-panel-and-bracket",
                    "can-kurtaran-hakem-koltu-u-life-guard-chair",
                ],
            },
        },
        "root_families": [],
    },
    "15": {
        "prefix": "swim",
        "root_set": {"key": "fiberglass-spas",
                     "name": "Fiberglass, Yer Üstü Havuzlar, Spalar",
                     "name_en": "Fiberglass, Above Ground Pools, Spas"},
        "attrs": ATTRS_SWIM,
        "groups": GROUPS_SWIM,
        "builder": "swim",
        "model_keys": [],
        "name_overrides": {
            "sonsuz-y-z-endless-swimming": (
                "Sonsuz Yüzüş (Endless Swimming)", "Endless Swimming"),
        },
        "series": {},
        "root_families": ["sonsuz-y-z-endless-swimming"],
    },
    "16": {
        "prefix": "membrane",
        "root_set": {"key": "su-yalitim-membrani",
                     "name": "Su Yalıtım Membrani",
                     "name_en": "Waterproofing Membrane"},
        "attrs": ATTRS_MEMBRANE,
        "groups": GROUPS_MEMBRANE,
        "builder": "membrane",
        "model_keys": ["r_n_adi_product_name"],
        "name_overrides": {},
        "series": {},
        "root_families": ["almera"],
    },
    "17": {
        "prefix": "valve",
        "root_set": {"key": "pvc-vana-cozumleri",
                     "name": "PVC Vana Çözümleri",
                     "name_en": "PVC Valve Solutions"},
        "attrs": ATTRS_VALVE,
        "groups": GROUPS_VALVE,
        "builder": "valve",
        "model_keys": ["model"],
        "name_overrides": {
            "u-pvc-solvent-cement-true-union-ball-valve-for-water": (
                "Yapıştırma Bilyalı Vana",
                "U-PVC Solvent Cement True Union Ball Valve"),
            "u-pvc-solvent-cement-spring-check-valve": (
                "Yapıştırma Yaylı Check Vana",
                "U-PVC Solvent Cement Spring Check Valve"),
            "u-pvc-wafer-check-valve": (
                "Wafer Check Vana", "U-PVC Wafer Check Valve"),
            "uh-pvc-yap-t-rma-muflu-serbest-flan-uh-pvc-solvent-"
            "cement-fl": ("Yapıştırma Muflu Serbest Flanşlı Check Vana",
                          "UH-PVC Solvent Cement Free Flanged Check Valve"),
            "uh-pvc-yap-t-rma-flan-l-man-on-uh-pvc-solvent-cement-"
            "flange-": ("Yapıştırma Flanşlı Manşonlu Check Vana",
                        "UH-PVC Solvent Cement Flanged Socket Check Valve"),
            "uh-pvc-t-ekvalf-uh-pvc-t-check-valve": (
                "T-Check Vana", "UH-PVC T-Check Valve"),
            "u-pvc-kelebek-vana-plak-u-pvc-butterfly-valve-without-"
            "flange": ("Kelebek Vana (Plak Tipi)",
                       "U-PVC Butterfly Valve (Wafer Type)"),
            "u-pvc-flan-l-kelebek-vana-tak-m-u-pvc-butterfly-valve-"
            "with-f": ("Kelebek Vana (Flanşlı Takım)",
                       "U-PVC Butterfly Valve (With Flanges)"),
            "uh-pvc-rakor-uh-pvc-union": (
                "Yapıştırma Rakor", "UH-PVC Solvent Cement Union"),
            "uh-pvc-one-side-female-threaded-union": (
                "Tek Tarafı Dişli Rakor",
                "UH-PVC One Side Female Threaded Union"),
            "uh-pvc-both-sides-female-threaded-union": (
                "Çift Tarafı Dişli Rakor",
                "UH-PVC Both Sides Female Threaded Union"),
            "uh-pvc-pompa-rakoru-d-tan-di-li-uh-pvc-male-threaded-"
            "union": ("Pompa Rakoru (Dış Dişli)",
                      "UH-PVC Male Threaded Union"),
            "uh-pvc-rakor-d-di-pirin-k-l-uh-pvc-union-outlet-male-"
            "threade": ("Rakor (Dış Dişli Pirinç Gövdeli)",
                        "UH-PVC Union Outlet Male Threaded Brass"),
            "yap-t-rma-muflu-90-dirsek-u-pvc-solvent-cement-90-"
            "elbow": ("Yapıştırma Muflu 90 Dirsek",
                      "U-PVC Solvent Cement 90 Elbow"),
            "u-pvc-45-yap-t-rma-muflu-dirsek-u-pvc-45-solvent-"
            "cement-elbo": ("Yapıştırma Muflu 45 Dirsek",
                            "U-PVC 45 Solvent Cement Elbow"),
            "u-pvc-yap-t-rma-muflu-te-u-pvc-solvent-cement-te": (
                "Yapıştırma Muflu Te", "U-PVC Solvent Cement Tee"),
            "uh-pvc-yap-t-rma-muflu-i-negal-te-u-pvc-solvent-"
            "cement-reduc": ("Yapıştırma Muflu Redüksiyon Te",
                             "UH-PVC Solvent Cement Reducer Tee"),
            "uh-pvc-one-side-female-threaded-reducer-adaptor": (
                "Tek Tarafı Dişli Redüksiyon Adaptör",
                "UH-PVC One Side Female Threaded Reducer Adaptor"),
            "uh-pvc-side-female-threaded-reducer-adaptor": (
                "Dişli Redüksiyon Adaptör",
                "UH-PVC Side Female Threaded Reducer Adaptor"),
            "uh-pvc-yap-t-rma-muflu-90-kruva-uh-pvc-solvent-"
            "cement-90-cro": ("Yapıştırma Muflu 90 Kruva",
                              "UH-PVC Solvent Cement 90 Cross"),
            "uh-pvc-yap-t-rma-muflu-man-on-uh-pvc-double-socket": (
                "Yapıştırma Muflu Manşon", "UH-PVC Double Socket"),
            "uh-pvc-solvent-cement-end-cap": (
                "Yapıştırma Tıpa", "UH-PVC Solvent Cement End Cap"),
            "p-pe-clamp": ("P-PE Kelepçe", "P-PE Clamp"),
            "uh-pvc-yap-t-rma-muflu-red-ksiyon-uh-pvc-solvent-"
            "cement-redu": ("Yapıştırma Muflu Redüksiyon",
                            "UH-PVC Solvent Cement Reducer"),
            "uh-pvc-yap-t-rma-muflu-borular-uh-pvc-solvent-cement-"
            "sockete": ("Yapıştırma Muflu Borular",
                        "UH-PVC Solvent Cement Socketed Pipes"),
            "pvc-yap-t-r-c-lar-pvc-cements": (
                "PVC Yapıştırıcılar", "PVC Cements"),
            "u-pvc-yap-t-r-c-u-pvc-solvent": (
                "U-PVC Yapıştırıcı", "U-PVC Solvent"),
        },
        "series": {
            "vanalar": {
                "name": "Vanalar", "name_en": "Valves",
                "families": [
                    "u-pvc-solvent-cement-true-union-ball-valve-for-"
                    "water",
                    "u-pvc-solvent-cement-spring-check-valve",
                    "u-pvc-wafer-check-valve",
                    "uh-pvc-yap-t-rma-muflu-serbest-flan-uh-pvc-"
                    "solvent-cement-fl",
                    "uh-pvc-yap-t-rma-flan-l-man-on-uh-pvc-solvent-"
                    "cement-flange-",
                    "uh-pvc-t-ekvalf-uh-pvc-t-check-valve",
                    "u-pvc-kelebek-vana-plak-u-pvc-butterfly-valve-"
                    "without-flange",
                    "u-pvc-flan-l-kelebek-vana-tak-m-u-pvc-butterfly-"
                    "valve-with-f",
                ],
            },
            "rakorlar": {
                "name": "Rakorlar", "name_en": "Unions",
                "families": [
                    "uh-pvc-rakor-uh-pvc-union",
                    "uh-pvc-one-side-female-threaded-union",
                    "uh-pvc-both-sides-female-threaded-union",
                    "uh-pvc-pompa-rakoru-d-tan-di-li-uh-pvc-male-"
                    "threaded-union",
                    "uh-pvc-rakor-d-di-pirin-k-l-uh-pvc-union-outlet-"
                    "male-threade",
                ],
            },
            "muflu-fittingler": {
                "name": "Muflu Fittingler",
                "name_en": "Solvent Cement Fittings",
                "families": [
                    "yap-t-rma-muflu-90-dirsek-u-pvc-solvent-cement-90-"
                    "elbow",
                    "u-pvc-45-yap-t-rma-muflu-dirsek-u-pvc-45-solvent-"
                    "cement-elbo",
                    "u-pvc-yap-t-rma-muflu-te-u-pvc-solvent-cement-te",
                    "uh-pvc-yap-t-rma-muflu-i-negal-te-u-pvc-solvent-"
                    "cement-reduc",
                    "uh-pvc-one-side-female-threaded-reducer-adaptor",
                    "uh-pvc-side-female-threaded-reducer-adaptor",
                    "uh-pvc-yap-t-rma-muflu-90-kruva-uh-pvc-solvent-"
                    "cement-90-cro",
                    "uh-pvc-yap-t-rma-muflu-man-on-uh-pvc-double-socket",
                    "uh-pvc-solvent-cement-end-cap",
                    "uh-pvc-yap-t-rma-muflu-red-ksiyon-uh-pvc-solvent-"
                    "cement-redu",
                    "uh-pvc-yap-t-rma-muflu-borular-uh-pvc-solvent-"
                    "cement-sockete",
                ],
            },
            "kelepce-yapistiricilar": {
                "name": "Kelepçe ve Yapıştırıcılar",
                "name_en": "Clamps & Cements",
                "families": [
                    "p-pe-clamp",
                    "pvc-yap-t-r-c-lar-pvc-cements",
                    "u-pvc-yap-t-r-c-u-pvc-solvent",
                ],
            },
        },
        "root_families": [],
    },
    "18": {
        "prefix": "spare",
        "root_set": {"key": "yedek-parcalar",
                     "name": "Havuz Ekipmanları Yedek Parçaları",
                     "name_en": "Pool Equipment Spare Parts"},
        "attrs": ATTRS_SPARE,
        "groups": GROUPS_SPARE,
        "builder": "spare",
        "model_keys": ["model"],
        "name_overrides": {
            "senkron-1-pompa-yedek-par-alari-spare-parts-of-senkron-1-"
            "pum": ("Senkron 1 Pompa Yedek Parçaları",
                    "Spare Parts of Senkron 1 Pump"),
            "senkron-2-pompa-yedek-par-alari-spare-parts-of-senkron-2-"
            "pum": ("Senkron 2 Pompa Yedek Parçaları",
                    "Spare Parts of Senkron 2 Pump"),
            "senkron-3-pompa-yedek-par-alari-spare-parts-of-senkron-3-"
            "pum": ("Senkron 3 Pompa Yedek Parçaları",
                    "Spare Parts of Senkron 3 Pump"),
            "senkron-3-jet-pompa-yedek-par-alari-spare-parts-of-"
            "senkron-3": ("Senkron 3 Jet Pompa Yedek Parçaları",
                          "Spare Parts of Senkron 3 Jet Pump"),
            "ninfa-yedek-par-alari-spare-parts-of-ninfa-pump": (
                "Ninfa Pompa Yedek Parçaları",
                "Spare Parts of Ninfa Pump"),
            "ondina-yedek-par-alari-spare-parts-of-ondina-pump": (
                "Ondina Pompa Yedek Parçaları",
                "Spare Parts of Ondina Pump"),
            "koral-seri-si-yedek-par-alari-spare-parts-of-koral-"
            "series-pu": ("Koral Serisi Pompa Yedek Parçaları",
                          "Spare Parts of Koral Series Pump"),
            "karpa-seri-si-yedek-par-alari-spare-parts-of-karpa-"
            "series-pu": ("Karpa Serisi Pompa Yedek Parçaları",
                          "Spare Parts of Karpa Series Pump"),
            "kan-seri-si-yedek-par-alari-spare-parts-of-kan-series-"
            "pump": ("Kan Serisi Pompa Yedek Parçaları",
                     "Spare Parts of Kan Series Pump"),
            "kapri-seri-si-yedek-par-alari-spare-parts-of-kapri-"
            "series-pu": ("Kapri Serisi Pompa Yedek Parçaları",
                          "Spare Parts of Kapri Series Pump"),
            "lamex-fi-ltre-yedek-par-alari-spare-parts-of-lamex-"
            "filter": ("Lamex Filtre Yedek Parçaları",
                       "Spare Parts of Lamex Filter"),
            "rotex-fi-ltre-yedek-par-alari-spare-parts-of-rotex-"
            "filter": ("Rotex Filtre Yedek Parçaları",
                       "Spare Parts of Rotex Filter"),
            "woundex-fi-ltre-yedek-par-alari-spare-parts-of-woundex-"
            "filte": ("Woundex Filtre Yedek Parçaları",
                      "Spare Parts of Woundex Filter"),
            "goodrob-easy-kablosuz-havuz-s-p-rgesi-goodrob-easy-"
            "cordless-": ("Goodrob Easy Yedek Parçaları",
                          "Spare Parts of Goodrob Easy"),
            "goodrob-maxi-kablosuz-havuz-robotu-goodrob-maxi-"
            "cordless-poo": ("Goodrob Maxi Yedek Parçaları",
                             "Spare Parts of Goodrob Maxi"),
            "goodrob-pro-kablosuz-havuz-robotu-goodrob-pro-"
            "cordless-pool-": ("Goodrob Pro Yedek Parçaları",
                               "Spare Parts of Goodrob Pro"),
            "goodrob-king-cordless-pool-robotic-cleaner": (
                "Goodrob King Yedek Parçaları",
                "Spare Parts of Goodrob King"),
            "tiger-shark-havuz-robotu-tiger-shark-pool-robotic-"
            "cleaner": ("Tiger Shark Yedek Parçaları",
                        "Spare Parts of Tiger Shark"),
            "clomax-200-salt-chlorinator": (
                "Clomax 200 Yedek Parçaları",
                "Spare Parts of Clomax 200"),
            "clomax-500-salt-chlorinator": (
                "Clomax 500 Yedek Parçaları",
                "Spare Parts of Clomax 500"),
            "klx-tuzdan-klor-jenerat-r-klx-salt-chlorinator": (
                "KLX Klorinatör Yedek Parçaları",
                "Spare Parts of KLX Salt Chlorinator"),
        },
        "series": {
            "senkron-pompalar": {
                "name": "Senkron Pompa Yedekleri",
                "name_en": "Senkron Pump Spares",
                "families": [
                    "senkron-1-pompa-yedek-par-alari-spare-parts-of-"
                    "senkron-1-pum",
                    "senkron-2-pompa-yedek-par-alari-spare-parts-of-"
                    "senkron-2-pum",
                    "senkron-3-pompa-yedek-par-alari-spare-parts-of-"
                    "senkron-3-pum",
                    "senkron-3-jet-pompa-yedek-par-alari-spare-parts-"
                    "of-senkron-3",
                ],
            },
            "diger-pompalar": {
                "name": "Diğer Pompa Yedekleri",
                "name_en": "Other Pump Spares",
                "families": [
                    "ninfa-yedek-par-alari-spare-parts-of-ninfa-pump",
                    "ondina-yedek-par-alari-spare-parts-of-ondina-pump",
                    "koral-seri-si-yedek-par-alari-spare-parts-of-"
                    "koral-series-pu",
                    "karpa-seri-si-yedek-par-alari-spare-parts-of-"
                    "karpa-series-pu",
                    "kan-seri-si-yedek-par-alari-spare-parts-of-kan-"
                    "series-pump",
                    "kapri-seri-si-yedek-par-alari-spare-parts-of-"
                    "kapri-series-pu",
                ],
            },
            "filtreler": {
                "name": "Filtre Yedekleri", "name_en": "Filter Spares",
                "families": [
                    "lamex-fi-ltre-yedek-par-alari-spare-parts-of-"
                    "lamex-filter",
                    "rotex-fi-ltre-yedek-par-alari-spare-parts-of-"
                    "rotex-filter",
                    "woundex-fi-ltre-yedek-par-alari-spare-parts-of-"
                    "woundex-filte",
                ],
            },
            "havuz-robotlari": {
                "name": "Havuz Robotu Yedekleri",
                "name_en": "Pool Robot Spares",
                "families": [
                    "goodrob-easy-kablosuz-havuz-s-p-rgesi-goodrob-"
                    "easy-cordless-",
                    "goodrob-maxi-kablosuz-havuz-robotu-goodrob-maxi-"
                    "cordless-poo",
                    "goodrob-pro-kablosuz-havuz-robotu-goodrob-pro-"
                    "cordless-pool-",
                    "goodrob-king-cordless-pool-robotic-cleaner",
                    "tiger-shark-havuz-robotu-tiger-shark-pool-"
                    "robotic-cleaner",
                ],
            },
            "klorinatorler": {
                "name": "Klorinatör Yedekleri",
                "name_en": "Chlorinator Spares",
                "families": [
                    "clomax-200-salt-chlorinator",
                    "clomax-500-salt-chlorinator",
                    "klx-tuzdan-klor-jenerat-r-klx-salt-chlorinator",
                ],
            },
        },
        "root_families": [],
    },
}

# Urun adi/verisine eslenen, nitelige donusturulmeyen anahtarlar
NATIVE_MAPPING = {
    "kod_code": "default_code",
    "code": "default_code",
    "kod": "default_code",
    "model_model": "name (aile basligi + model)",
    "model": "name (aile basligi + model)",
    "model_kod_model_code": "name (aile basligi + model)",
    "fi_yat_price": "prices (EUR)",
    "fi_yat": "prices (USD, plakali esanjor)",
    "price": "prices (EUR)",
    "price_eur": "prices (EUR)",
}

IGNORED_KEYS = ["", ":", "(6)", "marka_brand", "stok_kodu",
                "stok_kodu_code"]  # bos kolon basliklari; PDF logo dipnotu; kodun kendisi

PRICE_KEY = "fi_yat_price"  # '0,50 €' / '1.710 \\$' gibi ham fiyat kolonu


# ---------------------------------------------------------------------------
# Deger normalizasyon yardimcilari
# ---------------------------------------------------------------------------
def tr_ascii(s: str) -> str:
    """Turkce karakterleri ASCII'ye cevirir (unidecode benzeri)."""
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = s.translate(table)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def tech_name(key: str, prefix: str) -> str:
    return "x_" + prefix + "_" + tr_ascii(key.strip().lower()).replace("-", "_")


def parse_float(raw):
    """'0,50' -> 0.5, '*15' -> 15.0, '-' -> None, '10.000' -> 10000.0,
    '550W' -> 550.0, '8,5 mt' -> 8.5."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "-", "--", "*"):
        return None
    s = s.replace("*", "").replace("€", "").strip()
    m = re.search(r"\d[\d.,]*", s)
    if not m:
        return None
    s = m.group(0)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # binlik ayirici nokta
        s = s.replace(".", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_int(raw):
    v = parse_float(raw)
    return int(v) if v is not None else None


def parse_choice(raw, option_map):
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "-", "--"):
        return None
    return option_map.get(s, s)


def parse_length_m(raw):
    """'12,5 mt' -> 12.5; '120 cm' -> 1.2; '-' -> None."""
    v = parse_float(raw)
    if v is None:
        return None
    if "cm" in str(raw).lower():
        return v / 100.0
    return v


def parse_weight_kg(raw):
    """'440 gr' -> 0.44; '25 kg' -> 25.0."""
    v = parse_float(raw)
    if v is None:
        return None
    if "gr" in str(raw).lower() and "kg" not in str(raw).lower():
        return v / 1000.0
    return v


def parse_dims(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s not in ("", "-", "--") else None


def normalize_icon(raw):
    """Ikon etiketlerini normalize eder: yildiz/tire/RESIDENTAL vb."""
    s = str(raw).strip().strip("*").strip()
    s = re.sub(r"^-\s*", "", s).strip()
    return s.replace("RESIDENTAL", "RESIDENTIAL")


# ---------------------------------------------------------------------------
# Value builder'lar: kategoriye ozel aile/variant deger uretimi
# ---------------------------------------------------------------------------
def family_values_pump(fam, attr_by_key):
    specs = fam.get("family_specs_quantitative") or {}
    qual = fam.get("qualitative") or {}
    fv = {
        "max_water_temp_c": parse_float(specs.get("max_temp_c")),
        "max_pressure_bar": parse_float(specs.get("max_pressure_bar")),
        "rpm": parse_int(specs.get("rpm")),
        "highlights": "\n".join(qual.get("bullets_tr") or []) or None,
        "icons": [normalize_icon(i) for i in (qual.get("icons") or [])],
    }
    return fv


def variant_values_pump(vq, attr_by_key):
    flow = parse_float(vq.get("debi_m_h_flow") or vq.get("debi_m_3_h_flow")
                       or vq.get("debi_m_h_flow_max"))
    if flow is None:
        lh = parse_float(vq.get("debi_l_h_flow_l_h"))
        if lh:
            flow = lh / 1000.0  # L/h -> m3/h
    g_power = parse_float(vq.get("g_power"))
    return {
        "power_hp": parse_float(vq.get("g_hp_power_hp")),
        "power_kw": (parse_float(vq.get("g_kw_power"))
                     or (g_power / 1000.0 if g_power and g_power > 20
                         else None)),
        "flow_m3h": flow,
        "head_m": parse_float(vq.get("basma_y_ksekli_i_head")),
        "efficiency_class": parse_choice(
            vq.get("yeterli_li_k_efficiency"),
            attr_by_key["efficiency_class"]["option_map"]),
        "voltage": parse_choice(
            vq.get("voltaj_voltage") or vq.get("amper_amps"),
            attr_by_key["voltage"]["option_map"]),
        "cable_length_m": parse_float(vq.get("kablo_cable")),
        "connection": parse_choice(
            vq.get("ba_lanti_gi_ri_iki_inlet_outlet")
            or vq.get("ba_lanti_gi_ri_iki_inlet_outlet_d_outside_i_inside"),
            attr_by_key["connection"]["option_map"]),
        "sound_dba": parse_float(vq.get("ses_i_ddeti_dp_sound_dp")
                                 or vq.get("ses_i_ddeti_sound")),
        "weight": parse_float(vq.get("a_irlik_kg_weight_kg")),
        "package_dims": parse_dims(vq.get("paket_package")
                                   or vq.get("paket_uxgxy_package_lxwxh")),
        "variant_description": parse_dims(vq.get("a_iklama_description")),
    }


def family_values_filter(fam, attr_by_key):
    specs = fam.get("family_specs_quantitative") or {}
    qual = fam.get("qualitative") or {}
    fv = {
        "max_water_temp_c": parse_float(specs.get("max_temp_c")),
        "max_pressure_bar": parse_float(specs.get("max_pressure_bar")),
        "highlights": "\n".join(qual.get("bullets_tr") or []) or None,
        "icons": [normalize_icon(i) for i in (qual.get("icons") or [])],
    }
    return fv


def variant_values_filter(vq, attr_by_key):
    vmap = attr_by_key["connection"]["option_map"]
    ap_dia = (vq.get("ap_diameter") or "").strip() or None
    grain = None
    diameter = None
    if ap_dia:
        if "-" in ap_dia:  # "0,5-1,2 mm" -> tane boyutu, filtre capi degil
            grain = ap_dia
        else:
            diameter = parse_float(ap_dia)
    if vq.get("boyut_mm_size_mm"):
        bz = str(vq["boyut_mm_size_mm"]).strip()
        grain = bz if bz.endswith("mm") else f"{bz} mm"
    micron = vq.get("micron")
    rating = str(micron).replace("⩽", "≤ ").strip() if micron else None
    pump_raw = vq.get("pompa_pump")
    phase = None
    if pump_raw:
        if "Monofaze" in str(pump_raw):
            phase = "Monofaze"
        elif "Trifaze" in str(pump_raw):
            phase = "Trifaze"
    interior = vq.get("i_l_ler_interior_dimensions")
    if interior:
        m = re.match(r"([\dxX., ]+)", str(interior))
        interior = m.group(1).strip() if m else str(interior).strip()
    return {
        "flow_m3h": parse_float(vq.get("debi_m_h_flow")
                                or vq.get("debi_m_3_h_flow")),
        "connection": parse_choice(
            vq.get("ba_lanti_gi_ri_iki_inlet_outlet")
            or vq.get("ba_lanti_connection"), vmap),
        "weight": parse_float(vq.get("a_irlik_kg_weight_kg")
                              or vq.get("a_irlik_weight")
                              or vq.get("ambalaj_packing")),
        "diameter_mm": diameter,
        "sand_capacity_kg": parse_float(vq.get("kum_kg_sand_kg")
                                        or vq.get("kum_sand")),
        "working_pressure_bar": parse_float(
            vq.get("ali_ma_basinci_working_pressure")),
        "max_working_pressure_bar": parse_float(
            vq.get("max_ali_ma_basinci_max_working_pressure")),
        "test_pressure_bar": parse_float(vq.get("test_basinci_test_pressure")),
        "rating_micron": rating,
        "cartridge_d_mm": parse_float(vq.get("d_mm")),
        "cartridge_e_mm": parse_float(vq.get("e_mm")),
        "grain_size": grain,
        "filter_type": parse_choice(vq.get("fi_ltre_t_r_filter"),
                                    attr_by_key["filter_type"]["option_map"]),
        "skimmer": parse_choice(vq.get("skimfilter_skimfilter"),
                                {"1 Adet 1 Pcs": "1 Adet"}),
        "pump_hp": parse_float(pump_raw),
        "pump_phase": phase,
        "max_pool_m2": parse_float(vq.get("max_havuz_m_max_pool_m")),
        "machine_room": parse_choice(vq.get("maki_na_dai_resi_mechanical_room"),
                                     attr_by_key["machine_room"]["option_map"]),
        "contents": parse_dims(vq.get("i_i_ndeki_ler_contents")),
        "interior_dims": interior,
        "outer_sizes": parse_dims(vq.get("di_tan_di_a_outher_sizes")),
        "length_cm": parse_float(vq.get("uzunluk_lenght")
                                 or vq.get("uzunluk_length")),
        "width_cm": parse_float(vq.get("geni_li_k_width")),
        "height_cm": parse_float(vq.get("y_ksekli_k_height")),
        "steps": parse_int(vq.get("basamak_step")),
    }


def family_values_white(fam, attr_by_key):
    """03 kategorisinde family specs/bullets/ikonlar bos."""
    return {}


POOL_TYPE_VALUES = {"Liner", "Beton Concrete"}


def variant_values_white(vq, attr_by_key):
    model_val = (vq.get("model_model") or "").strip() or None
    if model_val in POOL_TYPE_VALUES:
        model = None
    else:
        model = model_val
    cmap = attr_by_key["color"]["option_map"]
    color_raw = vq.get("renk_color")
    if color_raw:
        color_raw = re.sub(r"\s*AISI 316 Frame$", "", str(color_raw).strip())
    smap = attr_by_key["skimmer_type"]["option_map"]
    power_raw = vq.get("g_power")
    power_w = parse_float(power_raw)
    voltage = None
    if power_raw and re.search(r"12\s*v", str(power_raw), re.I):
        voltage = 12
    hp_raw = vq.get("g_hp_power_hp")
    phase = None
    if hp_raw and "Trifaze" in str(hp_raw):
        phase = "Trifaze"
    elif hp_raw and "Monofaze" in str(hp_raw):
        phase = "Monofaze"
    ap_dia = (vq.get("ap_dia") or "").strip()
    diameter = float(ap_dia.replace("Ø", "")) if ap_dia.replace("Ø", "").isdigit() else None
    length = None
    l_dia = (vq.get("l_diameter") or "").strip()
    if l_dia and "mt" in l_dia:
        length = parse_float(l_dia)
    product_label = (vq.get("r_n_adi_product")
                     or vq.get("r_n_adi_product_name") or None)
    if l_dia and "komple set" in l_dia.lower():
        product_label = l_dia
    dims_parts = [vq.get("l_dimension"), vq.get("l_mm_size_mm"),
                  vq.get("boy_size")]
    dims = None
    for d in dims_parts:
        if d and str(d).strip() not in ("", "-", "--"):
            s = str(d).strip()
            if not s.endswith("mm"):
                s = f"{s} mm"
            dims = s
            break
    flow = vq.get("debi_l_dk_flowrate_lt_min")
    pool_src = vq.get("havuz_ti_pi_pool_type") or (
        model_val if model_val in POOL_TYPE_VALUES else None)
    return {
        "model": model,
        "product_label": product_label,
        "pool_type": parse_choice(pool_src,
                                  attr_by_key["pool_type"]["option_map"]),
        "color": parse_choice(color_raw, cmap),
        "power_w": power_w,
        "voltage_v": voltage,
        "connection": parse_choice(vq.get("ba_lanti_connection"),
                                   attr_by_key["connection"]["option_map"]),
        "diameter_mm": diameter,
        "length_m": length,
        "weight": parse_float(vq.get("a_irlik_weight")),
        "skimmer_type": parse_choice(vq.get("eki_l_type"), smap),
        "dims": dims,
        "width_cm": parse_float(vq.get("geni_li_k_width")),
        "depth_cm": parse_float(vq.get("deri_nli_k_l_s_power")),
        "power_hp": parse_float(hp_raw),
        "phase": phase,
        "model_name": parse_dims(vq.get("model_adi_model_name")),
        "flow_lmin": (str(flow).replace("-", " - ").strip()
                      if flow and str(flow).strip() not in ("", "-") else None),
    }


def family_values_outdoor(fam, attr_by_key):
    specs = fam.get("family_specs_quantitative") or {}
    return {
        "max_pressure_bar": parse_float(specs.get("max_pressure_bar")),
    }


def _parse_length_m(raw):
    """'1.300 mm' -> 1.3, '0,5 mt' -> 0.5, '2000 mm' -> 2.0."""
    if raw is None:
        return None
    s = str(raw).strip()
    v = parse_float(s)
    if v is None:
        return None
    return v / 1000.0 if "mm" in s.lower() else v


def variant_values_outdoor(vq, attr_by_key):
    model = parse_dims(vq.get("model"))
    label = (vq.get("r_n_i_smi_product_name")
             or vq.get("tanim_description") or None)
    aisi = None
    dims = None
    l_size = (vq.get("l_size") or "").strip() or None
    if l_size and l_size.upper().startswith("AISI"):
        m = re.search(r"(304|316)", l_size)
        aisi = m.group(1) if m else None
        rest = re.sub(r"AISI\s*(304|316)?\s*", "", l_size).strip()
        dims = rest or None
    else:
        dims = l_size
    if not dims:
        dims = parse_dims(vq.get("l_ler_uxgxy_size_lxwxh"))
    dia_raw = (vq.get("ap_dia") or vq.get("ap_diameter")
               or vq.get("boru_api_pipe_diameter") or "").strip() or None
    edge = None
    diameter = None
    if dia_raw:
        if "x" in dia_raw:
            edge = dia_raw
        else:
            diameter = parse_float(dia_raw.replace("Ø", ""))
    if not edge:
        edge = parse_dims(vq.get("kenar_l_leri_edge_size"))
    speed = parse_float(vq.get("hiz_max_velocity_max"))
    return {
        "model": model,
        "product_label": label,
        "connection": parse_choice(vq.get("ba_lanti_connection"),
                                   attr_by_key["connection"]["option_map"]),
        "steps": parse_choice(vq.get("basamak_sayisi_step_number"),
                              attr_by_key["steps"]["option_map"]),
        "tank_capacity": parse_float(vq.get("tank_kapasi_tesi_tank_capacity")),
        "tank_material": parse_dims(vq.get("tank_ci_nsi_tank_material")),
        "aisi": aisi,
        "dims": dims,
        "diameter_mm": diameter,
        "edge_size": edge,
        "width_cm": parse_float(vq.get("geni_li_k_width")),
        "length_m": _parse_length_m(vq.get("boy_length")
                                    or vq.get("uzunluk_lenght")),
        "volume_m3": parse_float(vq.get("haci_m_volume")),
        "weight": parse_float(vq.get("a_irlik_weight")),
        "max_pressure_bar": parse_float(vq.get("basin_max_pressure")),
        "speed": speed,
        "launch_time": parse_dims(vq.get(
            "y_kl_suya_i_ndi_rme_s_resi_launch_time_with_load")),
        "load_time": parse_dims(vq.get("y_kl_kaldirma_s_resi_load_time")),
        "hose_dia": parse_choice(vq.get("hortum_api_hose_dia"),
                                 attr_by_key["hose_dia"]["option_map"]),
        "hose_length": parse_dims(vq.get("uzunluk_length")),
        "filter_model": parse_dims(vq.get("fi_ltre_filter")),
        "pump_model": parse_dims(vq.get("pompa_pump")),
        "filtration_flow": parse_dims(vq.get(
            "fi_lrasyon_debi_si_filtration_flow")),
        "pump_flow": parse_dims(vq.get("pompa_debi_si_pump_flow")),
    }


def variant_values_clean(vq, attr_by_key):
    return {
        "model": parse_dims(vq.get("model")),
        "compatibility": parse_dims(vq.get("uyumluluk_compatibility")),
        "weight": parse_float(vq.get("a_irlik_weight")),
        "dims": parse_dims(vq.get("l_ler_size"))
        or parse_dims(vq.get("l_size")),
        "length_cm": parse_float(vq.get("uzunluk_length")),
        "material": parse_dims(vq.get("malzeme_material")),
        "pole_length": parse_dims(vq.get("sap_uzunlu_u_pole_length")),
        "power_w": parse_float(vq.get("g_power")),
        "power_input": parse_dims(vq.get("g_power_input")),
        "charge_time_h": parse_float(vq.get("arj_s_resi_charging_time")),
        "hose_length_m": parse_float(vq.get("hortum_uzunlu_u_hose_length")),
        "max_pool_size": parse_dims(vq.get("max_havuz_l_s_pool_max_size")),
        "recommended_pool_size": parse_dims(
            vq.get("neri_len_havuz_boyutu_recommended_pool_size")),
        "suction_flow_m3h": parse_float(
            vq.get("emi_kapasi_tesi_suction_capacity")),
        "cleaning_speed": parse_dims(vq.get("temi_zli_k_hizi_cleaning_speed")),
        "filtration_fineness": parse_dims(
            vq.get("fi_ltasyon_hassasi_yeti_filtration_fineness")),
    }


def family_values_disinf(fam, attr_by_key):
    specs = fam.get("family_specs_quantitative") or {}
    return {
        "pressure_bar": parse_float(specs.get("max_pressure_bar")),
    }


def variant_values_disinf(vq, attr_by_key):
    return {
        "model": parse_dims(vq.get("model")),
        "product_label": (vq.get("r_n_i_smi_product_name")
                          or vq.get("tanim_description") or None),
        "pool_volume_m3": parse_float(vq.get("havuz_hacmi_pool_volume")),
        "max_pool_volume_m3": parse_float(
            vq.get("max_havuz_hacmi_max_pool_volume")),
        "max_flow_m3h": parse_float(
            vq.get("max_debi_m_3_h_max_flow_rate_m_3_h")
            or vq.get("max_debi_m_h_max_flow_rate_m_h")
            or vq.get("max_debi_m_h_max_flow_m_h")
            or vq.get("max_debi_m_3_h_max_flow_m_3_h")),
        "connection": parse_dims(vq.get("ba_lanti_connection"))
        or parse_dims(vq.get("ba_lanti_mm_connection_mm")),
        "weight": parse_float(vq.get("a_irlik_weight")),
        "power_w": parse_float(vq.get("watt")),
        "voltage": parse_dims(vq.get("voltaj_voltage"))
        or parse_dims(vq.get("voltaj_frekans_voltage_frequency")),
        "lamp_power": parse_dims(vq.get("uv_lamba_g_c_uv_lamp_power")),
        "reactor_length_mm": parse_float(
            vq.get("reakt_r_uzunlu_u_reactor_length")
            or vq.get("r_n_boyutu_uzunluk_product_size_length")),
        "tube": parse_dims(vq.get("t_p_tube")),
        "chlorine_gph": parse_float(vq.get("klor_reti_mi_chlorine")),
        "salt_level": parse_dims(vq.get("tuz_sevi_yesi_salt_level")
                                 or vq.get("tuz_arali_i_salinity_range")),
        "pipe": parse_dims(vq.get("boru_pipe")),
        "orp_level": parse_dims(vq.get("orp_sevi_yesi_orp_level")),
        "water_hardness": parse_dims(vq.get("su_sertli_i_water_hardness")),
        "water_temp": parse_dims(vq.get("su_sicakli_i_water_temp")),
        "protection": parse_dims(vq.get("koruma_protection")),
        "rated_current": parse_dims(vq.get("akim_rated_current")),
        "rated_voltage": parse_dims(vq.get("geri_li_m_rated_voltage")),
        "power_input": parse_dims(vq.get("g_gi_ri_i_power_input")),
        "power_output": parse_dims(vq.get("g_iki_i_power_output")),
        "ph_valve": parse_dims(vq.get("ph_valfi_ph_valve")),
        "flow_lth": parse_float(vq.get("debi_lt_h_flow_lt_h")),
        "pressure_bar": parse_float(vq.get("basin_power")
                                    or vq.get("basin_pressure")
                                    or vq.get("basin_bar_pressure")),
        "pump_capacity": parse_dims(vq.get("pompa_kapasi_tesi_pump_capacity")),
        "capacity": parse_dims(vq.get("kapasi_te_capacity")),
        "measuring_range": parse_dims(vq.get("l_m_arali_i_measuring_range")),
        "tablet_capacity": parse_dims(
            vq.get("tablet_kapasi_te_tablet_carrying_capacity")),
        "dims": parse_dims(vq.get("r_n_l_leri_cm_product_sizes_cm")),
        "tupe": parse_dims(vq.get("t_p_tupe")),
        "gross_kg": parse_float(vq.get("br_t_kg_gross_kg")),
        "flow_switch": parse_dims(vq.get("aki_anahtari_flow_switch")),
        "plug": parse_dims(vq.get("pri_z_plug")),
        "lamp_indicator": parse_dims(
            vq.get("analog_lamba_m_r_g_stergeli_digital_lamp_life_indicator")),
        "vh_mount": parse_dims(
            vq.get("di_key_yatay_montaj_vertical_or_horizontal_mountable")),
        "lamp_sign": parse_dims(vq.get("lamba_g_stergesi_lamp_sign")),
        "pool_type_mark": parse_dims(vq.get("havuz_tipi_for_pool_type")),
    }


def variant_values_chem(vq, attr_by_key):
    """'50' -> 50 kg; '25 Kova Drum' -> 25 kg + 'Kova Drum'."""
    kg, ptype = None, None
    raw = str(vq.get("ambalaj_packing") or "").strip()
    m = re.match(r"^(\d+)\s*(.*)$", raw)
    if m:
        kg = float(m.group(1))
        ptype = m.group(2).strip() or None
    return {"packing_kg": kg, "packing_type": ptype}


def family_values_heat(fam, attr_by_key):
    specs = fam.get("family_specs_quantitative") or {}
    return {
        "pressure_bar": parse_float(specs.get("max_pressure_bar")),
    }


def variant_values_heat(vq, attr_by_key):
    return {
        "model": parse_dims(vq.get("model")),
        "phase": parse_choice(vq.get("faz_phase"),
                              attr_by_key["phase"]["option_map"]),
        "power_kw": parse_float(vq.get("g_power")),
        "required_flow_m3h": parse_float(
            vq.get("debi_i_hti_yaci_flow_requirements")),
        "max_flow_m3h": parse_float(vq.get("")),
        "dims": parse_dims(vq.get("l_ler_uxdxg_dimensions_lxdxw")),
        "frequency": parse_dims(vq.get("frekans_frequency")),
        "volume_m3": parse_float(vq.get("haci_m_volume")),
        "gross_kg": parse_float(vq.get("a_irlik_gross_weight")),
        "power_output": parse_dims(vq.get("g_iki_i_power_output")),
        "accessories_included": parse_dims(
            vq.get("aksesuarlar_dahi_ldi_r_accessories_included")),
        "hot_water_flow": parse_float(vq.get("sicak_su_aki_i_hot_water_flow")),
        "pool_water_flow": parse_float(
            vq.get("havuzun_suyunun_aki_i_flow_of_pool_water")),
        "heat_capacity_kcalh": parse_float(
            vq.get("e_anj_r_kapasi_tesi_kcal_h")),
        "pool_area_m2": parse_float(vq.get("havuz_m")),
        "reji_m": parse_float(vq.get("reji_m")),
        "exchanger_model": parse_dims(vq.get("e_anj_r_modeli")),
        "plate_count": parse_float(vq.get("plaka_sayisi")),
        "temp_range": parse_dims(vq.get("sicaklik")),
        "connection": parse_dims(vq.get("ba_lanti_connection"))
        or parse_dims(vq.get("iki_ba_lanti")),
        "length_mm": parse_float(vq.get("l_mm")),
        "primer_flow_m3h": parse_float(vq.get("primer_debi_primary_flow")),
        "primer_loss_kpa": parse_float(
            vq.get("primer_ba_sin_kaybi_loss_kpa")),
        "secondary_flow_m3h": parse_float(
            vq.get("sekonder_debi_secondary_flow")),
        "secondary_loss_kpa": parse_float(
            vq.get("sekonder_basin_kaybi_loss_kpa")),
        "heat_15c_kw": parse_float(vq.get("t_15_c_kw")),
        "heat_30c_kw": parse_float(vq.get("t_30_c_kw")),
        "heat_65c_kw": parse_float(vq.get("t_65_c_kw")),
    }


def variant_values_lining(vq, attr_by_key):
    return {
        "model": parse_dims(vq.get("model")),
        "product_label": parse_dims(vq.get("r_n_i_smi_product_name")),
        "alt_code": parse_dims(vq.get("")),
        "length_m": parse_float(vq.get("uzunluk_length")
                                or vq.get("uzunl_uk_le_ngth")),
        "thickness_mm": parse_float(vq.get("kalinlik_thickness")),
        "width_cm": parse_float(vq.get("geni_li_k_width")),
        "roll_m2": parse_float(vq.get("rulo_m_2_roll_m_2")),
        "dims": parse_dims(vq.get("l_size")),
        "package_size": parse_dims(vq.get("gramaj_weight")),
        "ceramic_bases": parse_dims(vq.get("serami_k_kodlari_bases")),
    }


def variant_values_spa(vq, attr_by_key):
    """'220V - 350W' -> 350 W + 220 V."""
    watt = vq.get("watt")
    power, volt = None, None
    if watt:
        nums = re.findall(r"(\d+(?:,\d+)?)", str(watt))
        if len(nums) >= 2:
            volt = float(nums[0].replace(",", "."))
            power = float(nums[1].replace(",", "."))
        elif len(nums) == 1:
            power = float(nums[0].replace(",", "."))
    return {
        "model": parse_dims(vq.get("model")),
        "product_label": parse_dims(vq.get("tanim_description")
                                    or vq.get("r_n_tanimi_description")),
        "phase": parse_choice(vq.get("faz_phase"),
                              attr_by_key["phase"]["option_map"]),
        "power_w": power,
        "voltage_v": volt,
        "noise_db": parse_float(vq.get("desi_bel_decibel")),
        "connection": parse_dims(vq.get("ba_lanti_connection")),
        "diameter_mm": parse_float(vq.get("ap_dia")),
    }


def variant_values_sauna(vq, attr_by_key):
    pr = parse_dims(vq.get("power_g"))
    if pr and " Arası" in pr:
        pr = pr.split(" Arası", 1)[0].strip()
    vol = parse_dims(vq.get("sauna_hacmi_sauna_volume"))
    if vol:
        vol = vol.replace("Max. ", "Maks. ").replace("Max ", "Maks. ")
    return {
        "model": parse_dims(vq.get("model")),
        "power_kw": parse_float(vq.get("g_power")),
        "power_range": pr,
        "stone_capacity_kg": parse_float(
            vq.get("ta_kapasi_tesi_stone_capacity")),
        "sauna_volume_m3": vol,
        "max_cabin_volume_m3": parse_float(
            vq.get("kabi_n_hacmi_max_cabin_volume_max")),
        "dims": parse_dims(vq.get("l_size"))
        or parse_dims(vq.get("l_ler_uxtxg_dimensions_lxtxw"))
        or parse_dims(vq.get("l_ler_uxdxg_dimensions_lxdxw")),
        "packing_l": parse_float(vq.get("ambalaj_packing")),
    }


def variant_values_fount(vq, attr_by_key):
    return {
        "model": parse_dims(vq.get("model")),
        "color": parse_choice(vq.get("renk_color"),
                              attr_by_key["color"]["option_map"]),
        "lamp_power": parse_dims(vq.get("g_power")),
        "connection": parse_choice(vq.get("ba_lanti_connection"),
                                   attr_by_key["connection"]["option_map"]),
        "dims": parse_dims(vq.get("l_size")),
        "diameter_mm": parse_float(vq.get("ap_dia")),
        "max_flow_lth": parse_float(vq.get("debi_flow_max")),
        "head_max_m": parse_float(vq.get("basma_y_ksekli_i_head_max")),
        "outlet": parse_dims(vq.get("iki_outlet")),
        "weight": parse_float(vq.get("a_irlik_weight")),
    }


def _parse_kw_w(raw):
    """'0,55 kW' -> 550.0; '100w' -> 100.0."""
    if raw is None:
        return None
    s = str(raw).strip()
    v = parse_float(s)
    if v is None:
        return None
    return v * 1000.0 if "kw" in s.lower() else v


def variant_values_pond(vq, attr_by_key):
    return {
        "model": parse_dims(vq.get("model"))
        or parse_dims(vq.get("r_n_adi_name")),
        "power_w": _parse_kw_w(vq.get("g_power")),
        "rated_power_w": parse_float(vq.get("g_de_eri_rated_power")),
        "max_flow_lth": parse_float(
            vq.get("debi_max_flow") or vq.get("debi_flow")
            or vq.get("debi_flow_max") or vq.get("debi_flow_rate")
            or vq.get("debi_l_h_flow_l_h")),
        "head_max_m": parse_float(
            vq.get("max_ati_max_head") or vq.get("basma_y_ksekli_i_head_max")
            or vq.get("basma_y_ksekli_i_head")),
        "pond_fish_m3": parse_float(vq.get("balikli_g_let_pond_with_fish")),
        "pond_normal_m3": parse_float(
            vq.get("dekorati_f_g_let_normal_pond")),
        "capacity": parse_dims(vq.get("kapasi_te_capacity"))
        or parse_dims(vq.get("uv_lamba_g_c_uv_lamp_powerfish")),
        "tank_capacity_l": parse_float(
            vq.get("kapasi_te_tank_capacity")
            or vq.get("tank_kapasi_tesi_tank_capacity")),
        "tank_material": parse_dims(vq.get("tank_ci_nsi_tank_material")),
        "pressure_bar": parse_float(vq.get("basin_max_pressure")),
        "uv_power_w": parse_float(vq.get("uv_g_c_bulb_power")
                                  or vq.get("uv_c_lamba_uv_c_lamp")),
        "dims": parse_dims(vq.get("l_dimensions"))
        or parse_dims(vq.get("r_n_boyutu_item_size"))
        or parse_dims(vq.get("l_size")),
        "length_mm": parse_float(vq.get("uzunluk_production_length")),
        "lip_length_mm": parse_float(vq.get("a_iz_uzunlu_u_lip_length")),
        "with_led": parse_choice(vq.get("ledli_with_led"),
                                 attr_by_key["with_led"]["option_map"]),
        "cable_m": parse_float(vq.get("kablo_cable")),
        "voltage": parse_dims(vq.get("voltaj_voltage")),
        "connection": parse_dims(vq.get("hortum_adapt_r_dimensions"))
        or parse_dims(vq.get("gi_ri_iki_adapt_r_inlet_outlet_adapter"))
        or parse_dims(vq.get("uv_c_ba_lanti_connection_uv_c")),
        "outlet": parse_dims(vq.get("iki_outlet")),
        "certificate": parse_dims(vq.get("serti_fi_ka_certificate")),
        "weight": parse_float(vq.get("a_irlik_weight")),
    }


_OLY_COLOR_RE = re.compile(r"(kırmızı|mavi|beyaz)")


def variant_values_olympic(vq, attr_by_key):
    model = parse_dims(vq.get("model"))
    values = {
        "length_m": parse_length_m(vq.get("uzunluk_lenght"))
        or parse_float(vq.get("uzunluk_mt_length_mt")),
        "steps": (lambda v: int(v) if v is not None else None)(
            parse_float(vq.get("basamak_step"))),
        "height_cm": parse_float(vq.get("y_ksekli_k_cm_height_cm")),
        "weight": parse_weight_kg(vq.get("a_irlik_weight")),
    }
    if model:
        m = _OLY_COLOR_RE.search(model.lower())
        if m:
            values["color"] = attr_by_key["color"]["option_map"][m.group(1)]
            tip = re.sub(r"^\d+-\s*", "", model)
            values["model"] = re.split(
                r"\s+(?:kırmızı|mavi|beyaz)", tip, flags=re.I)[0].strip()
        else:
            values["model"] = model
    return values


def variant_values_swim(vq, attr_by_key):
    return {
        "intensity_levels": (lambda v: int(v) if v is not None else None)(
            parse_float(vq.get("zorluk_sevi_yesi_intensity_levels"))),
    }


def variant_values_membrane(vq, attr_by_key):
    return {
        "model": parse_dims(vq.get("r_n_adi_product_name")),
        "unit": parse_choice(vq.get("bi_ri_m_unit"),
                             attr_by_key["unit"]["option_map"]),
        "dims": parse_dims(vq.get("l_ler_dimensions")),
    }


def variant_values_valve(vq, attr_by_key):
    dia = parse_float(vq.get("ap_mm_dia_mm"))
    pn = parse_float(vq.get("basin_pn"))
    qty = parse_dims(vq.get("mi_ktar_quantity"))
    desc = parse_dims(vq.get("tanim_description"))
    threads = parse_dims(vq.get("rp_inch")) \
        or parse_dims(vq.get("i_n_inch"))
    if desc:
        label = desc
    else:
        parts = []
        if dia:
            parts.append(f"Ø{dia:g}")
        if pn:
            parts.append(f"PN{pn:g}")
        if threads:
            parts.append(threads)
        label = " ".join(parts) or None
    box = parse_float(vq.get("koli_adet_box_pcs"))
    return {
        "model": label,
        "diameter_mm": dia,
        "pn": pn,
        "threads": threads,
        "box_pcs": (lambda v: int(v) if v is not None else None)(box),
        "quantity": qty,
        "description": desc,
        "weight": parse_weight_kg(vq.get("a_irlik_weight")),
    }


def variant_values_spare(vq, attr_by_key):
    part = (parse_float(vq.get("par_a"))
            or parse_float(vq.get("par_a_part"))
            or parse_float(vq.get("no")))
    return {
        "model": parse_dims(vq.get("a_klama_description"))
        or parse_dims(vq.get("a_klama")),
        "part_no": (lambda v: int(v) if v is not None else None)(part),
        "ref": parse_dims(vq.get("referans_referance"))
        or parse_dims(vq.get("referans_reference"))
        or parse_dims(vq.get("referans")),
        "position": parse_dims(vq.get("adet_qty"))
        or parse_dims(vq.get("adet")),
    }


BUILDERS = {
    "pump": (family_values_pump, variant_values_pump),
    "filter": (family_values_filter, variant_values_filter),
    "white": (family_values_white, variant_values_white),
    "outdoor": (family_values_outdoor, variant_values_outdoor),
    "clean": (lambda fam, attr_by_key: {}, variant_values_clean),
    "disinf": (family_values_disinf, variant_values_disinf),
    "chem": (lambda fam, attr_by_key: {}, variant_values_chem),
    "heat": (family_values_heat, variant_values_heat),
    "lining": (lambda fam, attr_by_key: {}, variant_values_lining),
    "spa": (lambda fam, attr_by_key: {}, variant_values_spa),
    "sauna": (lambda fam, attr_by_key: {}, variant_values_sauna),
    "fount": (lambda fam, attr_by_key: {}, variant_values_fount),
    "pond": (lambda fam, attr_by_key: {}, variant_values_pond),
    "olympic": (lambda fam, attr_by_key: {}, variant_values_olympic),
    "swim": (lambda fam, attr_by_key: {}, variant_values_swim),
    "membrane": (lambda fam, attr_by_key: {}, variant_values_membrane),
    "valve": (lambda fam, attr_by_key: {}, variant_values_valve),
    "spare": (lambda fam, attr_by_key: {}, variant_values_spare),
}

MODEL_SOURCE_KEYS = ["model_model", "model", "model_kod_model_code",
                     "r_n_adi_product_name"]


def product_identity(p) -> tuple[str, str | None]:
    """Gercek urun kodu: kod_code -> code_raw -> code onceligi.

    Bazi kaynaklarda 'code' alani kisaltilmis/cakisan degerler icerir;
    PDF'teki gercek KOD kod_code/code_raw alanlarindadir.

    Kod icinde varyant adi tasiyan kaynaklar (orn. '14016273018
    Fircali Brush') temizlenir: ilk token tamamen rakamsa o gercek kod,
    kalan varyant etiketidir. Harf baslayan kodlar (orn. 'FB 1001-C
    CARMAX1ING75M') oldugu gibi kalir; PDF 'yeni' etiketi (orn.
    'MPL700 Image: NEW') koddan ayrilir.
    """
    vq = p.get("variant_quantitative") or {}
    raw = str(vq.get("kod_code") or p.get("code_raw") or p["code"]).strip()
    if " " in raw and raw.split(None, 1)[0].isdigit():
        code, tag = raw.split(None, 1)
        tag = _CODE_TAG_FIXES.get(tag.strip(), tag.strip())
        return code, tag
    if " Image:" in raw:
        code, tag = raw.split(" Image:", 1)
        tag = tag.strip().strip(":").strip()
        return code.strip(), (tag or None)
    return raw, None


# PDF cikarimindaki bozuk varyant etiketleri
_CODE_TAG_FIXES = {"Sngerli Foam": "Süngerli Foam"}


# ---------------------------------------------------------------------------
# Uretim
# ---------------------------------------------------------------------------
def build(cat_no: str):
    cfg = CATEGORY_CONFIG[cat_no]
    prod_file = [p for p in CAT_DIR.glob(f"{cat_no}_*.json")
                 if not p.name.endswith("_attributes.json")][0]
    attr_file = CAT_DIR / prod_file.name.replace(".json", "_attributes.json")

    products = json.loads(prod_file.read_text(encoding="utf-8"))
    famdata = json.loads(attr_file.read_text(encoding="utf-8"))
    families = {f["family_product_id"]: f for f in famdata["families"]}

    prefix = cfg["prefix"]
    root_key = cfg["root_set"]["key"]
    attrs_def = cfg["attrs"]
    build_family, build_variant = BUILDERS[cfg["builder"]]
    model_keys = cfg.get("model_keys", MODEL_SOURCE_KEYS)
    name_overrides = cfg.get("name_overrides", {})
    key_overrides = cfg.get("key_overrides", {})
    # aile product_id -> set key ters eslemesi
    rev_keys = {v: k for k, v in key_overrides.items()}

    # --- Nitelik tanimlari ---
    attributes = []
    for a in attrs_def:
        name = a["native_field"] if a.get("nature") == "native" \
            else tech_name(a["key"], prefix)
        set_keys = [root_key if s == "ROOT" else s for s in a["sets"]]
        attributes.append({
            "key": a["key"],
            "name": name,
            "nature": a.get("nature", "custom"),
            "native_field": a.get("native_field"),
            "field_description": a["desc"],
            "field_description_en": a["desc_en"],
            "attribute_type": a["type"],
            "serialized": False,
            "widget": "many2many_tags" if a["type"] == "multiselect" else None,
            "group_key": a["group"],
            "set_keys": set_keys,
            "value_level": a["level"],
            "source": a.get("source"),
            "options": a.get("options", []),
            "option_map": a.get("option_map", {}),
        })
    attr_by_key = {a["key"]: a for a in attributes}

    # kaynak anahtar -> nitelik eslesmesi (denetim icin)
    variant_source_keys = set()
    for a in attrs_def:
        for part in (a.get("source") or "").split("|"):
            part = part.strip()
            if part:
                key = re.sub(r"\(.*$", "", part.split(".")[-1]).strip()
                if key:
                    variant_source_keys.add(key)

    # --- Set hiyerarsisi (ustten alta sirali) ---
    sets = [dict(cfg["root_set"], key=root_key, parent_key=None,
                 sequence=10, is_root=True)]
    seq = 20
    for skey, s in cfg["series"].items():
        sets.append({"key": skey, "name": s["name"], "name_en": s["name_en"],
                     "parent_key": root_key, "sequence": seq})
        seq += 10
    fam_seq = 10
    for skey, s in cfg["series"].items():
        for set_key in s["families"]:
            fam_id = rev_keys.get(set_key, set_key)
            fam = families[fam_id]
            name_tr, name_en = name_overrides.get(
                fam_id, (fam["family_title_tr"].strip(),
                         fam["family_title_en"].strip()))
            sets.append({
                "key": set_key,
                "name": name_tr,
                "name_en": name_en,
                "parent_key": skey,
                "sequence": fam_seq,
                "family_product_id": fam_id,
                "family_variant_count": sum(
                    1 for p in products if p["family_product_id"] == fam_id),
            })
            fam_seq += 10
    for set_key in cfg.get("root_families", []):
        fam_id = rev_keys.get(set_key, set_key)
        fam = families[fam_id]
        name_tr, name_en = name_overrides.get(
            fam_id, (fam["family_title_tr"].strip(),
                     fam["family_title_en"].strip()))
        sets.append({
            "key": set_key,
            "name": name_tr,
            "name_en": name_en,
            "parent_key": root_key,
            "sequence": fam_seq,
            "family_product_id": fam_id,
            "family_variant_count": sum(
                1 for p in products if p["family_product_id"] == fam_id),
        })
        fam_seq += 10

    # --- Aile seviyesi degerler ---
    family_values = {}
    for fk, fam in families.items():
        set_key = key_overrides.get(fk, fk)
        fv = build_family(fam, attr_by_key)
        family_values[set_key] = {k: v for k, v in fv.items()
                                  if v not in (None, [])}

    # --- Urun (variant) seviyesi degerler ---
    product_values = {}
    unmapped = {}
    for p in products:
        vq = p.get("variant_quantitative") or {}
        raw0 = str(vq.get("kod_code") or p.get("code_raw")
                   or p.get("code") or "").strip()
        if re.match(r"AISI\s*\d+\s+PASLANMAZ", raw0):
            # aile tablosundaki malzeme notu; urun degil
            continue
        vals = build_variant(vq, attr_by_key)
        vals = {k: v for k, v in vals.items() if v not in (None, "")}

        # eslenmeyen anahtar denetimi
        for k in vq:
            if k not in variant_source_keys and k not in NATIVE_MAPPING \
                    and k not in IGNORED_KEYS:
                unmapped.setdefault(k, []).append(p["code"])

        model = next((str(vq[k]).strip() for k in model_keys
                      if vq.get(k)), "")
        fam_id = p["family_product_id"]
        set_key = key_overrides.get(fam_id, fam_id)
        fam_name = name_overrides.get(fam_id, (None,))[0] \
            or p["family_title_tr"].strip()
        identity, code_tag = product_identity(p)
        price = vq.get("price_eur")
        usd_price = parse_float(vq.get("fi_yat"))
        raw_price = vq.get(PRICE_KEY)
        if raw_price and "$" in str(raw_price) and usd_price is None:
            usd_price = parse_float(raw_price)
        if model and "model" in attr_by_key:
            vals.setdefault("model", model)

        if identity in product_values:
            # Ayni kod katalogda birden fazla satirda listelenmis
            # (orn. model tablosu + ozellik isaret/fiyat tablosu):
            # satirlar birlestirilir; dolu deger kazanir.
            cur = product_values[identity]
            for k, v in vals.items():
                if v not in (None, "") and not cur["values"].get(k):
                    cur["values"][k] = v
            nat = cur["native"]
            if price is not None and not any(
                    pp["currency"] == "EUR" for pp in nat["prices"]):
                nat["prices"].append({"currency": "EUR", "price": price})
            if usd_price is not None and not any(
                    pp["currency"] == "USD" for pp in nat["prices"]):
                nat["prices"].append({"currency": "USD",
                                      "price": usd_price})
        else:
            prices = []
            if price is not None:
                prices.append({"currency": "EUR", "price": price})
            if usd_price is not None:
                prices.append({"currency": "USD", "price": usd_price})
            product_values[identity] = {
                "family_key": fam_id,
                "attribute_set_key": set_key,
                "values": vals,
                "native": {
                    "default_code": identity,
                    "name": None,
                    "prices": prices,
                    "category_code": p["category_no"],
                },
            }

        # Isim: birlestirilmis model (varsa) + aile basligi.
        # Merge durumunda (ayni kodun sonraki satirlari) sahip satirin
        # aile adi/seti korunur; isim yeniden ezilmez.
        merged_model = product_values[identity]["values"].get("model") or ""
        owner_fam = product_values[identity]["family_key"]
        owner_name = name_overrides.get(owner_fam, (None,))[0] or ""
        if merged_model:
            name = f"{owner_name} {merged_model}".strip()
        elif code_tag:
            name = f"{owner_name} ({identity} {code_tag})"
        else:
            pk = product_values[identity]["values"].get("packing_kg")
            if pk:
                name = f"{owner_name} {pk:g} kg"
            else:
                name = f"{owner_name} ({identity})"
        product_values[identity]["native"]["name"] = name

    out = {
        "meta": {
            "generator": "pim/generate_pim_json.py",
            "generated_at": date.today().isoformat(),
            "source_files": [prod_file.name, attr_file.name],
            "category_no": cat_no,
            "category_tr": famdata["category_tr"],
            "category_en": famdata["category_en"],
            "odoo_model": MODEL,
            "pim_modules": ["attribute_set", "product_attribute_set", "pim"],
            "technical_name_prefix": prefix,
            "family_count": famdata["family_count"],
            "variant_count": famdata["variant_count"],
            "import_order": [
                "attribute_groups",
                "attribute_sets (ustten alta, parent once)",
                "attributes (custom -> ir.model.fields; native -> field_id)",
                "attribute.option kayitlari (select/multiselect icin)",
                "product_category (varsayilan set baglanti)",
                "product_values (product.template + x_ alan degerleri)",
            ],
            "design_notes": [
                "Set hiyerarşisi attribute.set.parent_id ile kurulur; alt "
                "setler üst setin niteliklerini kalıtır "
                "(complete_attribute_ids).",
                "Kategori genelinde ortak nitelikler kök sette; yalnızca alt "
                "gruplarda görülen nitelikler ilgili ara/aile setine bağlanır "
                "(ör. kum kapasitesi yalnızca Kum Filtreleri setinde).",
                "Bir nitelik birden fazla sete bağlanabilir "
                "(attribute_set_ids m2m): grain_size hem 25 Mikron hem Filtre "
                "Medyaları setinde.",
                "serialized=False seçildi; gerçek kolon arama/filtreleme/"
                "gruplama avantajı sağlar. Yüzlerce niteliğe çıkılırsa "
                "serialized=True önerilir (x_custom_json_attrs JSON blob).",
                "Ağırlık doğal (native) nitelik olarak product.template.weight "
                "alanına bağlandı; ambalaj ağırlığı (25 kg çuvallar) da bu "
                "alana yazılır.",
                "select/multiselect nitelikler attribute.option kayıtlarıyla "
                "normalize edildi; serbest metin yerine seçim listesi "
                "kullanılarak veri tutarlılığı sağlanır.",
                "Urun adi (name) aile başlığı + model; model yoksa aile "
                "başlığı + koddan üretilir. default_code her zaman koddur.",
            ],
            "data_quality_notes": [
                "Ikon değerleri normalize edildi (yildiz/tire temizligi, "
                "'RESIDENTAL' -> 'RESIDENTIAL', '- POOL PLUMBING LINES' -> "
                "'POOL PLUMBING LINES').",
                "6 yollu vanalarda büyük 'Ø' disli, küçük 'ø' yapistirma "
                "baglantiyi belirtir; secenek etiketleri buna gore "
                "aciklastirildi.",
                "ap_diameter alani iki anlamda kullaniliyor: sayisal degerler "
                "filtre capi (diameter_mm), aralik degerler ('0,5-1,2 mm') "
                "tane boyutu (grain_size) olarak ayristirildi.",
                "'ambalaj_packing' ('25 kg') degeri urunun gercek agirligi "
                "oldugu icin native weight alanina yazildi.",
                "Rotex ailesinde family spec 'max_pressure_bar=1.5' ile "
                "variant tablosundaki 'MAX. CALISMA BASINCI 2,5 bar' "
                "celisiyor; her ikisi ayri nitelikte (kok 'Maks. Basinc' ve "
                "kum filtre 'Maks. Calisma Basinci') tasindi, gozden "
                "gecirilmeli.",
                "Lamex tablolarindaki 1.050+ mm capli satirlar kum filtreler "
                "icin dogrudur; PDF'te pompa bolumune tasmasi kaynak "
                "cikarimidir (02 kategorisinde zaten yer alirlar).",
                "Rotex aile tablosunda Woundex ile ayni kodlu satirlar var "
                "(12015123100-03); urun atamalari Woundex tarafindadir ve "
                "cift uretim engellendi.",
                "bullets_tr listesi bazi ailelerde TR+EN satirlari icerir; "
                "highlights alani kaynagini birebir tasir.",
                "Zeolit ailesi kaynak PDF'te skimmer, havuz ortusu, merdiven "
                "gibi diger urunleri de kapsar; set adi 'Zeolit ve Diger "
                "Urunler' olarak duzenlendi.",
            ],
        },
        "attribute_groups": [
            {**g, "sequence": (i + 1) * 10}
            for i, g in enumerate(cfg["groups"])
        ],
        "attribute_sets": sets,
        "attributes": attributes,
        "product_category": {
            "code": cat_no,
            "name": famdata["category_tr"],
            "name_en": famdata["category_en"],
            # Kok seviye kategori: Goods gibi varsayilan gruplarin altina
            # baglanmaz, kendi basina durur (parent=None).
            "parent": None,
            "default_attribute_set_key": root_key,
        },
        "family_values": family_values,
        "product_values": product_values,
    }

    # --- Dogrulamalar ---
    errors = []
    set_keys = {s["key"] for s in sets}
    for a in attributes:
        for sk in a["set_keys"]:
            if sk not in set_keys:
                errors.append(f"attr {a['key']}: bilinmeyen set {sk}")
    for fam_key in family_values:
        if fam_key not in set_keys:
            errors.append(f"aile seti yok: {fam_key}")
    for code, pv in product_values.items():
        if pv["attribute_set_key"] not in set_keys:
            errors.append(f"{code}: bilinmeyen set {pv['attribute_set_key']}")
        for k, v in pv["values"].items():
            a = attr_by_key[k]
            if a["attribute_type"] in ("select", "multiselect"):
                opts = a["options"]
                check = v if isinstance(v, list) else [v]
                for item in check:
                    if item not in opts:
                        errors.append(f"{code}.{k}: '{item}' seceneklerde yok")
    if unmapped:
        for k, codes in unmapped.items():
            errors.append(f"eslenmemis anahtar '{k}' ({len(codes)} urun)")

    return out, errors


def main():
    cat_nos = sys.argv[1:] or ["01"]

    # --- Isim cakismasi cozumu (nitelik soneki) ---
    # Ayni ada sahip urunler (orn. "STANDART" merdivenin 2/3/4/5 basamakli
    # versiyonlari) ayirt edici nitelik degerleriyle isimlendirilir.
    SUFFIX_PRIORITY = [
        "steps", "aisi", "color", "power", "power_w", "voltage_v",
        "diameter_mm", "width_cm", "length_m", "volume_m3", "tank_capacity",
        "speed", "edge_size", "dims", "hose_dia", "hose_length", "sand_kg",
        "part_no",
    ]
    SUFFIX_EXCLUDE = {"model", "product_label", "weight"}

    def _fmt_num(v):
        return f"{float(v):g}".replace(".", ",")

    SUFFIX_LABELS = {
        "steps": lambda v: v if "(" in str(v) else f"{v} Basamak",
        "aisi": lambda v: f"AISI {v}",
        "power_w": lambda v: f"{_fmt_num(v)} W",
        "voltage_v": lambda v: f"{_fmt_num(v)} V",
        "diameter_mm": lambda v: f"Ø{_fmt_num(v)}",
        "width_cm": lambda v: f"{_fmt_num(v)} cm",
        "length_m": lambda v: f"{_fmt_num(v)} m",
        "volume_m3": lambda v: f"{_fmt_num(v)} m³",
        "tank_capacity": lambda v: f"{_fmt_num(v)} L",
        "speed": lambda v: f"{_fmt_num(v)} m/sn",
    }

    def _suffix_label(key, v):
        fn = SUFFIX_LABELS.get(key)
        if fn:
            return fn(v)
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)[:40]
        if isinstance(v, float):
            return _fmt_num(v)
        return str(v).strip()[:40]

    def resolve_name_collisions(specs):
        by_name = {}
        for spec in specs:
            for code, pv in spec["product_values"].items():
                by_name.setdefault(pv["native"]["name"], []).append(
                    (spec, code, pv))
        renamed = []
        for name, group in sorted(by_name.items()):
            if len(group) == 1:
                continue
            all_keys = set()
            for _, _, pv in group:
                all_keys |= set(pv["values"])
            all_keys -= SUFFIX_EXCLUDE
            diff_keys = []
            for k in all_keys:
                vals = {json.dumps(pv["values"].get(k)) for _, _, pv in group}
                if len(vals) > 1:
                    diff_keys.append(k)
            diff_keys.sort(key=lambda k: (SUFFIX_PRIORITY.index(k)
                                          if k in SUFFIX_PRIORITY else 99, k))
            if not diff_keys:
                for spec, code, pv in group:
                    pv["native"]["name"] = f"{name} ({code})"
                    renamed.append(f"{name} -> {pv['native']['name']}")
                continue
            parts = []
            for _, _, pv in group:
                vals = pv["values"]
                parts.append([_suffix_label(k, vals[k]) for k in diff_keys
                              if vals.get(k) not in (None, "")])
            max_k = max(len(ps) for ps in parts)
            cand = [name] * len(group)
            for k in range(1, max_k + 1):
                cand = [f"{name} ({', '.join(ps[:k])})" if ps[:k] else name
                        for ps in parts]
                if len(set(cand)) == len(cand):
                    break
            else:
                seen = {}
                for i, ((_, code, _), new) in enumerate(zip(group, cand)):
                    if new in seen:
                        cand[i] = f"{new} ({code})"
                    seen[new] = i
            for (_, _, pv), new in zip(group, cand):
                if new != name:
                    pv["native"]["name"] = new
                    renamed.append(f"{name} -> {new}")
        return renamed

    specs, all_errors = [], {}
    for cat_no in cat_nos:
        out, errors = build(cat_no)
        specs.append(out)
        all_errors[cat_no] = errors

    renamed = resolve_name_collisions(specs)

    OUT_DIR.mkdir(exist_ok=True)
    for cat_no, out in zip(cat_nos, specs):
        dest = OUT_DIR / f"{cat_no}_pim.json"
        dest.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        n_opts = sum(len(a["options"]) for a in out["attributes"])
        print(f"\n[{cat_no}] Yazildi : {dest}")
        print(f"  Setler  : {len(out['attribute_sets'])}")
        print(f"  Gruplar : {len(out['attribute_groups'])}")
        print(f"  Nitelik : {len(out['attributes'])} (toplam {n_opts} secenek)")
        print(f"  Urun    : {len(out['product_values'])}")
        errors = all_errors[cat_no]
        if errors:
            print("  UYARILAR:")
            for e in errors:
                print("   -", e)
        else:
            print("  Dogrulama: hatasiz")
    if renamed:
        print(f"\nIsim cakismalari cozuldu ({len(renamed)}):")
        for r in renamed:
            print("  -", r)


if __name__ == "__main__":
    main()
