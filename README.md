# JPW Error Summary Only — Render-ready Repository

A minimal Streamlit app that accepts the weekly **JPW Excel** (5 sheets), runs only the **SOP error checks**, and returns a downloadable **`error_summary.csv`**. Built to **deploy on Render** directly from GitHub.

---

## 📁 Repository Structure

```
jpw-error-summary-only/
├── app.py
├── requirements.txt
├── Procfile
├── render.yaml
├── README.md
└── .gitignore
```

---

## `app.py`

```python
import io
import pandas as pd
import streamlit as st
from typing import Dict, List, Optional

st.set_page_config(page_title="JPW Error Summary Only", page_icon="🧾", layout="centered")

EXPECTED_SHEETS = [
    "Merchants",
    "Partners",
    "PartnerMerchantMapping",
    "Lead",
    "Leadpartnermapping",
]

# Suggested/typical column names. We keep it simple for the "error summary only" app.
SUGGESTED_COLS = {
    "Merchants": {"id": ["MerchantID", "merchant_id", "id"], "user_id": ["UserID", "user_id"], "mobile": ["MobileNumber", "mobile"]},
    "Partners":  {"id": ["PartnerID",  "partner_id",  "id"], "user_id": ["UserID", "user_id"], "mobile": ["MobileNumber", "mobile"]},
    "Lead":      {"id": ["LeadID",     "lead_id",     "id"], "user_id": ["UserID", "user_id"], "mobile": ["MobileNumber", "mobile"]},
    "PartnerMerchantMapping": {"partner_id": ["PartnerID", "partner_id"], "merchant_id": ["MerchantID", "merchant_id"]},
    "Leadpartnermapping":     {"lead_id": ["LeadID", "lead_id"], "partner_id": ["PartnerID", "partner_id"]},
}

@st.cache_data(show_spinner=False)
def read_excel(file_bytes: bytes) -> Dict[str, pd.DataFrame]:
    x = pd.ExcelFile(file_bytes)
    sheets: Dict[str, pd.DataFrame] = {}
    for name in x.sheet_names:
        df = x.parse(name)
        df.columns = [str(c).strip() for c in df.columns]
        df = df.loc[:, ~df.columns.str.match(r"Unnamed: ")]
        sheets[name] = df
    return sheets

# Utility: find first present column among candidates

def first_present(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None

# SOP checks ---------------------------------------------------------------

def duplicate_issues(df: pd.DataFrame, cols: List[Optional[str]], sheet: str, entity: str) -> pd.DataFrame:
    issues = []
    for c in cols:
        if c and c in df.columns:
            dup_rows = df[df.duplicated(c, keep=False) & df[c].notna()]
            for idx, row in dup_rows.iterrows():
                issues.append({
                    "sheet": sheet,
                    "row_index": int(idx) + 2,  # 1-based + header row
                    "error_type": f"Duplicate {c}",
                    "entity": entity,
                    "message": f"Value '{row[c]}' in column '{c}' appears more than once",
                })
    return pd.DataFrame(issues)


def validate_sop(sheets: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    def colmap(sheet: str, role: str) -> Optional[str]:
        df = sheets.get(sheet, pd.DataFrame())
        return first_present(df, SUGGESTED_COLS.get(sheet, {}).get(role, []))

    errors = []

    # --- 1) Avoid Duplicacy (Lead, Partners, Merchants on Mobile or UserID) ---
    lead_df = sheets.get("Lead", pd.DataFrame())
    partners_df = sheets.get("Partners", pd.DataFrame())
    merchants_df = sheets.get("Merchants", pd.DataFrame())

    errors.append(duplicate_issues(lead_df,      [colmap("Lead", "mobile"),      colmap("Lead", "user_id")],      "Lead",      "Lead"))
    errors.append(duplicate_issues(partners_df,  [colmap("Partners", "mobile"),  colmap("Partners", "user_id")],  "Partners",  "Partner"))
    errors.append(duplicate_issues(merchants_df, [colmap("Merchants", "mobile"), colmap("Merchants", "user_id")], "Merchants", "Merchant"))

    # --- 2) Enforce Proper Partner-Lead Mapping ---
    # Each Lead must be mapped in Leadpartnermapping
    lead_id = colmap("Lead", "id")
    lpm_lead_id = colmap("Leadpartnermapping", "lead_id")

    if lead_id and lpm_lead_id and not lead_df.empty:
        lpm_df = sheets.get("Leadpartnermapping", pd.DataFrame())
        missing_mask = ~lead_df[lead_id].isin(lpm_df[lpm_lead_id]) & lead_df[lead_id].notna()
        for idx, row in lead_df[missing_mask].iterrows():
            errors.append(pd.DataFrame([{
                "sheet": "Lead",
                "row_index": int(idx) + 2,
                "error_type": "Unmapped Lead",
                "entity": "Lead",
                "message": f"LeadID '{row[lead_id]}' has no entry in Leadpartnermapping.{lpm_lead_id}",
            }]))

    # (Optional but helpful) Referential integrity for mapping tables
    # Leadpartnermapping.partner_id must exist in Partners.id
    lpm_partner_id = colmap("Leadpartnermapping", "partner_id")
    partners_id = colmap("Partners", "id")
    if lpm_partner_id and partners_id:
        lpm_df = sheets.get("Leadpartnermapping", pd.DataFrame())
        missing = ~lpm_df[lpm_partner_id].isin(partners_df[partners_id]) & lpm_df[lpm_partner_id].notna()
        for idx, row in lpm_df[missing].iterrows():
            errors.append(pd.DataFrame([{
                "sheet": "Leadpartnermapping",
                "row_index": int(idx) + 2,
                "error_type": "Invalid reference: Partner",
                "entity": "Leadpartnermapping",
                "message": f"{lpm_partner_id} '{row[lpm_partner_id]}' not found in Partners.{partners_id}",
            }]))

    # PartnerMerchantMapping.partner_id -> Partners.id
    pmm_df = sheets.get("PartnerMerchantMapping", pd.DataFrame())
    pmm_partner_id = colmap("PartnerMerchantMapping", "partner_id")
    pmm_merchant_id = colmap("PartnerMerchantMapping", "merchant_id")
    merchants_id = colmap("Merchants", "id")

    if pmm_partner_id and partners_id and not pmm_df.empty:
        missing = ~pmm_df[pmm_partner_id].isin(partners_df[partners_id]) & pmm_df[pmm_partner_id].notna()
        for idx, row in pmm_df[missing].iterrows():
            errors.append(pd.DataFrame([{
                "sheet": "PartnerMerchantMapping",
                "row_index": int(idx) + 2,
                "error_type": "Invalid reference: Partner",
                "entity": "PartnerMerchantMapping",
                "message": f"{pmm_partner_id} '{row[pmm_partner_id]}' not found in Partners.{partners_id}",
            }]))

    # PartnerMerchantMapping.merchant_id -> Merchants.id
    if pmm_merchant_id and merchants_id and not pmm_df.empty:
        missing = ~pmm_df[pmm_merchant_id].isin(merchants_df[merchants_id]) & pmm_df[pmm_merchant_id].notna()
        for idx, row in pmm_df[missing].iterrows():
            errors.append(pd.DataFrame([{
                "sheet": "PartnerMerchantMapping",
                "row_index": int(idx) + 2,
                "error_type": "Invalid reference: Merchant",
                "entity": "PartnerMerchantMapping",
                "message": f"{pmm_merchant_id} '{row[pmm_merchant_id]}' not found in Merchants.{merchants_id}",
            }]))

    # Flatten
    if not errors:
        return pd.DataFrame(columns=["sheet", "row_index", "error_type", "entity", "message"])
    return pd.concat(errors, ignore_index=True)

# ---------------- UI ----------------

st.title("🧾 JPW Error Summary (SOP-only)")
st.write("Upload the weekly Excel file (5 sheets). We will return **error_summary.csv** only.")

uploaded = st.file_uploader("Upload .xlsx", type=["xlsx"], accept_multiple_files=False)

if uploaded is None:
    with st.expander("Need a blank template?", expanded=False):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for s, cols in SUGGESTED_COLS.items():
                if s in ("Merchants", "Partners", "Lead"):
                    frame = pd.DataFrame(columns=[cols["id"][0], cols["user_id"][0], cols["mobile"][0]])
                elif s == "PartnerMerchantMapping":
                    frame = pd.DataFrame(columns=[cols["partner_id"][0], cols["merchant_id"][0]])
                else:  # Leadpartnermapping
                    frame = pd.DataFrame(columns=[cols["lead_id"][0], cols["partner_id"][0]])
                frame.to_excel(writer, sheet_name=s, index=False)
        st.download_button("Download template.xlsx", data=buf.getvalue(), file_name="JPW_template.xlsx")
    st.stop()

try:
    sheets = read_excel(uploaded.getvalue())
except Exception as e:
    st.error(f"Failed to read Excel: {e}")
    st.stop()

# Validate presence of required sheets
missing = [s for s in EXPECTED_SHEETS if s not in sheets]
if missing:
    st.error(f"Missing required sheets: {', '.join(missing)}")
    st.stop()

# Run SOP validation
with st.spinner("Generating error summary..."):
    errors_df = validate_sop(sheets)

# Offer CSV download only
csv_bytes = errors_df.to_csv(index=False).encode("utf-8")
st.download_button("Download error_summary.csv", data=csv_bytes, file_name="error_summary.csv", mime="text/csv")

if errors_df.empty:
    st.success("No SOP issues found. Your error summary is empty.")
else:
    st.info(f"Found {len(errors_df)} issues. Download the CSV above.")
```

---

## `requirements.txt`

```txt
streamlit==1.37.1
pandas==2.2.2
openpyxl==3.1.5
```

---

## `Procfile`

```txt
web: streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

---

## `render.yaml` (optional but recommended)

```yaml
services:
  - type: web
    name: jpw-error-summary-only
    env: python
    plan: free
    buildCommand: "pip install -r requirements.txt"
    startCommand: "streamlit run app.py --server.port $PORT --server.address 0.0.0.0"
```

---

## `README.md`

````md
# JPW Error Summary Only (Render-ready)

Minimal Streamlit app to generate **error_summary.csv** for the JPW weekly upload.

## SOP Rules Implemented
1. **Avoid Duplicacy**
   - Mobile Number or User ID should not be duplicated for **Lead**, **Partners**, or **Merchants**.
2. **Enforce Proper Partner–Lead Mapping**
   - Every **Lead** must appear in **Leadpartnermapping**.
   - (Extra) Foreign key sanity checks on mapping tables.

## Input Format
An Excel workbook with 5 sheets (case-sensitive):
- `Merchants`
- `Partners`
- `PartnerMerchantMapping`
- `Lead`
- `Leadpartnermapping`

Typical columns (auto-detected):
- Merchants/Partners/Lead: `*ID`, `UserID`, `MobileNumber`
- PartnerMerchantMapping: `PartnerID`, `MerchantID`
- Leadpartnermapping: `LeadID`, `PartnerID`

## Local Run
```bash
pip install -r requirements.txt
streamlit run app.py
````

## Deploy on Render

* **Build Command**: `pip install -r requirements.txt`
* **Start Command**: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
* Or include `render.yaml` and click *New → Web Service* in Render.

````

---

## `.gitignore`
```gitignore
# Python
__pycache__/
*.pyc

# Streamlit
.streamlit/

# OS
.DS_Store
Thumbs.db
````
