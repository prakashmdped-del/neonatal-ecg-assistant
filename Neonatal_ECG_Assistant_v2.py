
import streamlit as st
import pandas as pd
import math
from datetime import datetime
from io import BytesIO
from fpdf import FPDF
from datetime import datetime
import base64

st.set_page_config(page_title="Neonatal ECG Assistant", layout="centered")

# ------------------------------
# Embedded light pink ECG grid SVG (as background for numeric inputs)
# ------------------------------
ECG_SVG = '''
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
  <rect width="100%" height="100%" fill="#ffe6eb"/>
  <defs>
    <pattern id="small" width="8" height="8" patternUnits="userSpaceOnUse">
      <path d="M 8 0 L 0 0 0 8" fill="none" stroke="#ffb3c1" stroke-width="0.5"/>
    </pattern>
    <pattern id="big" width="40" height="40" patternUnits="userSpaceOnUse">
      <rect width="40" height="40" fill="url(#small)"/>
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#ff7f96" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="url(#big)"/>
</svg>
'''.strip()

ECG_BG = base64.b64encode(ECG_SVG.encode()).decode()

css_block = '''
<style>
  .ecg-block {
    background-image: url("data:image/svg+xml;base64,REPLACE_ECG_BG");
    background-size: cover;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid #ffd1da;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    margin-bottom: 10px;
  }
  .tooltip {
    display:inline-block;
    border-bottom: 1px dotted #999;
    cursor: help;
    color:#6b6f76;
    font-weight:600;
    margin-left:6px;
  }
  .small-note {
    font-size:0.9rem;
    color:#5c5f63;
  }
</style>
'''.replace("REPLACE_ECG_BG", ECG_BG)

st.markdown(css_block, unsafe_allow_html=True)

# ------------------------------
# Load Excel (Sheet 1 & 4)
# ------------------------------
@st.cache_data
def load_reference_data():
    try:
        xls = pd.ExcelFile("Neonatal_ECG_Pack.xlsx")
        sheet_names = xls.sheet_names
        sheet1 = pd.read_excel(xls, sheet_names[0])
        sheet4 = pd.read_excel(xls, sheet_names[3])
        return sheet1, sheet4, sheet_names
    except Exception as e:
        st.warning(f"Could not load reference Excel: {e}")
        return pd.DataFrame(), pd.DataFrame(), []

ref_df, axis_df, sheet_names = load_reference_data()

st.title("🩺 Neonatal ECG Assistant (v2.0)")
st.caption("Educational decision-support only — clinician review required.")

# ------------------------------
# Helper: detect ranges from Sheet 1
# Expected columns (flexible): Parameter, Min/Lower, Max/Upper, Age or AgeGroup
# ------------------------------
def get_range_from_ref(parameter: str, age_days: int):
    if ref_df.empty:
        return None, None, None

    df = ref_df.copy()
    # heuristics for columns
    param_col = None
    min_col = None
    max_col = None
    age_col = None
    age_min_col = None
    age_max_col = None

    for c in df.columns:
        cl = c.lower()
        if param_col is None and ("parameter" in cl or "measure" in cl or cl in ["name","metric"]):
            param_col = c
        if min_col is None and (("min" in cl) or ("lower" in cl)):
            min_col = c
        if max_col is None and (("max" in cl) or ("upper" in cl)):
            max_col = c
        if age_col is None and ("agegroup" in cl or "age group" in cl or cl=="age"):
            age_col = c
        if age_min_col is None and ("age_min" in cl or "agemin" in cl or "lower_age" in cl):
            age_min_col = c
        if age_max_col is None and ("age_max" in cl or "agemax" in cl or "upper_age" in cl):
            age_max_col = c

    # filter by parameter
    if param_col is not None:
        df = df[df[param_col].astype(str).str.strip().str.lower().eq(parameter.strip().lower())]

    # age filtering
    if age_min_col and age_max_col and (age_min_col in df.columns) and (age_max_col in df.columns):
        df = df[(pd.to_numeric(df[age_min_col], errors="coerce") <= age_days) & (age_days <= pd.to_numeric(df[age_max_col], errors="coerce"))]
    elif age_col is not None and (age_col in df.columns):
        # try to map age groups by simple keywords
        candidates = []
        for idx, r in df.iterrows():
            val = str(r[age_col]).lower()
            ok = False
            if age_days == 0 and any(k in val for k in ["<1", " day", "0-1"]):
                ok = True
            elif 1 <= age_days <= 7 and any(k in val for k in ["1–7", "1-7", "week", "7"]):
                ok = True
            elif age_days > 7 and any(k in val for k in [">7", "month", "1 month", "30"]):
                ok = True
            if ok or "all" in val:
                candidates.append(idx)
        if candidates:
            df = df.loc[candidates]

    # extract min/max
    lower = None
    upper = None
    if not df.empty:
        if min_col in df.columns:
            try:
                lower = float(pd.to_numeric(df[min_col], errors="coerce").dropna().iloc[0])
            except Exception:
                pass
        if max_col in df.columns:
            try:
                upper = float(pd.to_numeric(df[max_col], errors="coerce").dropna().iloc[0])
            except Exception:
                pass

    return lower, upper, (param_col if param_col else None)

# ------------------------------
# Inputs (single-column, mobile friendly)
# ------------------------------
st.subheader("Patient / ECG Inputs")

age_days = st.number_input("Age (days)", min_value=0, max_value=30, value=1, step=1,
                           help="Enter postnatal age in days to apply age-appropriate reference ranges.")

st.markdown('<div class="ecg-block">', unsafe_allow_html=True)
hr_boxes = st.number_input("Heart Rate: small boxes between two R–R peaks",
                           min_value=1.0, max_value=50.0, value=5.0, step=0.5,
                           help="Count the number of small 1 mm boxes between two consecutive R peaks at 25 mm/s. HR = 1500 / boxes.")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="ecg-block">', unsafe_allow_html=True)
pr_boxes = st.number_input("PR interval: small boxes",
                           min_value=1.0, max_value=15.0, value=3.0, step=0.5,
                           help="At 25 mm/s, 1 small box = 40 ms. PR (ms) = boxes × 40.")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="ecg-block">', unsafe_allow_html=True)
qrs_boxes = st.number_input("QRS duration: small boxes",
                            min_value=1.0, max_value=10.0, value=1.5, step=0.5,
                            help="At 25 mm/s, 1 small box = 40 ms. QRS (ms) = boxes × 40.")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="ecg-block">', unsafe_allow_html=True)
qt_boxes = st.number_input("QT interval: small boxes",
                           min_value=1.0, max_value=20.0, value=8.0, step=0.5,
                           help="At 25 mm/s, 1 small box = 40 ms. QT (ms) = boxes × 40.")
st.markdown('</div>', unsafe_allow_html=True)

comments = st.text_area("Comments / Clinical context (optional)")

# ------------------------------
# Conversions
# ------------------------------
HR = round(1500.0 / hr_boxes, 1) if hr_boxes > 0 else None
PR_ms = round(pr_boxes * 40.0, 1)
QRS_ms = round(qrs_boxes * 40.0, 1)
QT_ms = round(qt_boxes * 40.0, 1)

# QTc calculations (Bazett, Fridericia) — RR in seconds
RR_ms = 60000.0 / HR if HR else None
RR_s = RR_ms / 1000.0 if RR_ms else None

def safe_div(x, y):
    try:
        return x / y
    except Exception:
        return None

QTc_Bazett = round(safe_div(QT_ms, math.sqrt(RR_s)) if RR_s and RR_s>0 else float("nan"), 1)
QTc_Fridericia = round(safe_div(QT_ms, (RR_s ** (1.0/3.0))) if RR_s and RR_s>0 else float("nan"), 1)

# ------------------------------
# Axis Wizard (Yes/No)
# ------------------------------
st.subheader("QRS Axis Wizard (Yes/No)")
lead_I = st.radio("Is QRS upright (positive) in Lead I?", ["Yes", "No"], horizontal=True)
lead_II = st.radio("Is QRS upright (positive) in Lead II?", ["Yes", "No"], horizontal=True)
lead_aVF = st.radio("Is QRS upright (positive) in aVF?", ["Yes", "No"], horizontal=True)
lead_V1 = st.radio("Is QRS upright (positive) in V1?", ["Yes", "No"], horizontal=True)
lead_V6 = st.radio("Is QRS upright (positive) in V6?", ["Yes", "No"], horizontal=True)

def interpret_axis(i_pos: bool, ii_pos: bool, avf_pos: bool, v1_pos: bool, v6_pos: bool, age_days: int):
    # Primary determination from limb leads
    if i_pos and ii_pos and avf_pos:
        base = "Normal axis"
    elif (not i_pos) and ii_pos and avf_pos:
        base = "Right axis deviation"
    elif i_pos and (not ii_pos) and (not avf_pos):
        base = "Left axis deviation"
    elif (not i_pos) and (not ii_pos) and (not avf_pos):
        base = "Extreme axis deviation"
    else:
        base = "Indeterminate / borderline axis (consider manual angle measurement)"
    # Context note using precordial hints
    hint = []
    if v1_pos and (not v6_pos):
        hint.append("Rightward precordial pattern (V1 positive, V6 not)")
    if (not v1_pos) and v6_pos:
        hint.append("Leftward precordial pattern (V6 positive, V1 not)")
    # Neonatal physiological note
    phys = ""
    if age_days <= 7 and "Right axis deviation" in base:
        phys = "Rightward axis may be physiological in the first week of life."
    note = " | ".join(hint + ([phys] if phys else []))
    return base, note

axis_result, axis_note = interpret_axis(
    lead_I == "Yes", lead_II == "Yes", lead_aVF == "Yes", lead_V1 == "Yes", lead_V6 == "Yes", age_days
)

st.info(f"Axis: {axis_result}" + (f" — {axis_note}" if axis_note else ""))

# ------------------------------
# Compare to reference ranges (if available)
# ------------------------------
def classify(value, low, high):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if low is not None and value < low:
        return "Low"
    if high is not None and value > high:
        return "High"
    return "Normal"

# Pull ranges
hr_low, hr_high, _ = get_range_from_ref("HR", age_days)
pr_low, pr_high, _ = get_range_from_ref("PR", age_days)
qrs_low, qrs_high, _ = get_range_from_ref("QRS", age_days)
qt_low, qt_high, _ = get_range_from_ref("QT", age_days)

# Typical neonatal QTc thresholds if not present in sheet
qtc_baz_low, qtc_baz_high = None, 480.0
qtc_frd_low, qtc_frd_high = None, 460.0

# Alerting
def toast(level, msg):
    if level == "error":
        st.error(msg)
    elif level == "warning":
        st.warning(msg)
    else:
        st.info(msg)

if HR is not None and (hr_low is not None and HR < hr_low):
    toast("warning", f"Bradycardia: HR {HR} bpm < {hr_low} bpm (age-based)")
if HR is not None and (hr_high is not None and HR > hr_high):
    toast("warning", f"Tachycardia: HR {HR} bpm > {hr_high} bpm (age-based)")
if not math.isnan(QTc_Bazett) and qtc_baz_high is not None and QTc_Bazett > qtc_baz_high:
    toast("error", f"Prolonged QTc (Bazett): {QTc_Bazett} ms > {qtc_baz_high} ms")
if not math.isnan(QTc_Fridericia) and qtc_frd_high is not None and QTc_Fridericia > qtc_frd_high:
    toast("error", f"Prolonged QTc (Fridericia): {QTc_Fridericia} ms > {qtc_frd_high} ms")
if "Left axis deviation" in axis_result or "Extreme axis deviation" in axis_result:
    toast("warning", f"Axis alert: {axis_result}")

# ------------------------------
# Results table
# ------------------------------
ref_fmt = lambda lo, hi: (f"{lo:g}–{hi:g}" if (lo is not None and hi is not None) else "—")

results_df = pd.DataFrame([
    {"Measure": "Age (days)", "Input": age_days, "Converted": "—", "Reference": "—", "Status": "—"},
    {"Measure": "HR (from boxes)", "Input": f"{hr_boxes} boxes", "Converted": f"{HR} bpm" if HR else "—",
     "Reference": ref_fmt(hr_low, hr_high), "Status": classify(HR, hr_low, hr_high)},
    {"Measure": "PR", "Input": f"{pr_boxes} boxes", "Converted": f"{PR_ms} ms",
     "Reference": ref_fmt(pr_low, pr_high), "Status": classify(PR_ms, pr_low, pr_high)},
    {"Measure": "QRS", "Input": f"{qrs_boxes} boxes", "Converted": f"{QRS_ms} ms",
     "Reference": ref_fmt(qrs_low, qrs_high), "Status": classify(QRS_ms, qrs_low, qrs_high)},
    {"Measure": "QT", "Input": f"{qt_boxes} boxes", "Converted": f"{QT_ms} ms",
     "Reference": ref_fmt(qt_low, qt_high), "Status": classify(QT_ms, qt_low, qt_high)},
    {"Measure": "QTc (Bazett)", "Input": "—", "Converted": f"{QTc_Bazett} ms" if not math.isnan(QTc_Bazett) else "—",
     "Reference": ref_fmt(qtc_baz_low, qtc_baz_high), "Status": classify(QTc_Bazett, qtc_baz_low, qtc_baz_high)},
    {"Measure": "QTc (Fridericia)", "Input": "—", "Converted": f"{QTc_Fridericia} ms" if not math.isnan(QTc_Fridericia) else "—",
     "Reference": ref_fmt(qtc_frd_low, qtc_frd_high), "Status": classify(QTc_Fridericia, qtc_frd_low, qtc_frd_high)},
])

st.subheader("Summary")
st.dataframe(results_df, use_container_width=True)

st.markdown(f"**Axis:** {axis_result}" + (f" — {axis_note}" if axis_note else ""))

# ------------------------------
# PDF generation (clean, neutral)
# ------------------------------
def build_pdf(dataframe: pd.DataFrame, axis_text: str, axis_note: str, comments: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title & time
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Neonatal ECG Assistant", ln=1)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, datetime.now().strftime("%Y-%m-%d %H:%M"), ln=1)
    pdf.ln(2)

    # Table header
    headers = ["Measure", "Input", "Converted", "Reference", "Status"]
    col_w = [48, 40, 40, 35, 27]  # total ~190 incl. margins
    pdf.set_font("Arial", "B", 11)
    for w, h in zip(col_w, headers):
        pdf.cell(w, 8, h, border=1)
    pdf.ln(8)

    # Table rows
    pdf.set_font("Arial", "", 10)
    for _, r in dataframe.iterrows():
        row = [
            str(r["Measure"]),
            str(r["Input"]),
            str(r["Converted"]),
            str(r["Reference"]),
            str(r["Status"]),
        ]
        # simple wrap: truncate to fit cell
        for w, val in zip(col_w, row):
            pdf.cell(w, 8, (val if len(val) <= 28 else val[:27] + "…"), border=1)
        pdf.ln(8)

    pdf.ln(4)
    axis_line = axis_text + (f" — {axis_note}" if axis_note else "")
    pdf.multi_cell(0, 8, f"Axis: {axis_line}")

    if comments:
        pdf.ln(2)
        pdf.multi_cell(0, 8, f"Comments: {comments}")

    pdf.ln(3)
    pdf.set_font("Arial", "I", 10)
    pdf.multi_cell(0, 8, "Disclaimer: This tool provides educational decision-support only. "
                         "ECG findings must be reviewed by a qualified clinician.")

    # Return as bytes
    return pdf.output(dest="S").encode("latin-1")
)

# ------------------------------
# Reference viewer (expanders)
# ------------------------------
with st.expander("View reference data (Sheet 1)"):
    if not ref_df.empty:
        st.dataframe(ref_df, use_container_width=True)
    else:
        st.write("Reference sheet could not be loaded. Ensure 'Neonatal_ECG_Pack.xlsx' is in the same folder.")

with st.expander("View axis wizard matrix (Sheet 4)"):
    if not axis_df.empty:
        st.dataframe(axis_df, use_container_width=True)
    else:
        st.write("Axis sheet could not be loaded. Ensure 'Neonatal_ECG_Pack.xlsx' is in the same folder.")
