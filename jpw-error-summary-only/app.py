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

def first_present(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None

def duplicate_issues(df: pd.DataFrame, cols: List[Optional[str]], sheet: str, entity: str) -> pd.DataFrame:
    issues = []
    for c in cols:
        if c and c in df.columns:
            dup_rows = df[df.duplicated(c, keep=False) & df[c].notna()]
            for idx, row in dup_rows.iterrows():
                issues.append({
                    "sheet": sheet,
                    "row_index": int(idx) + 2,
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

    lead_df = sheets.get("Lead", pd.DataFrame())
    partners_df = sheets.get("Partners", pd.DataFrame())
    merchants_df = sheets.get("Merchants", pd.DataFrame())

    errors.append(duplicate_issues(lead_df,      [colmap("Lead", "mobile"),      colmap("Lead", "user_id")],      "Lead",      "Lead"))
    errors.append(duplicate_issues(partners_df,  [colmap("Partners", "mobile"),  colmap("Partners", "user_id")],  "Partners",  "Partner"))
    errors.append(duplicate_issues(merchants_df, [colmap("Merchants", "mobile"), colmap("Merchants", "user_id")], "Merchants", "Merchant"))

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

    if not errors:
        return pd.DataFrame(columns=["sheet", "row_index", "error_type", "entity", "message"]) 
    return pd.concat(errors, ignore_index=True)

st.title("🧾 JPW Error Summary (SOP-only)")
st.write("Upload the weekly Excel file (5 sheets). We will return **error_summary.csv** only.")

uploaded = st.file_uploader("Upload .xlsx", type=["xlsx"], accept_multiple_files=False)

if uploaded is None:
    st.stop()

try:
    sheets = read_excel(uploaded.getvalue())
except Exception as e:
    st.error(f"Failed to read Excel: {e}")
    st.stop()

missing = [s for s in EXPECTED_SHEETS if s not in sheets]
if missing:
    st.error(f"Missing required sheets: {', '.join(missing)}")
    st.stop()

with st.spinner("Generating error summary..."):
    errors_df = validate_sop(sheets)

csv_bytes = errors_df.to_csv(index=False).encode("utf-8")
st.download_button("Download error_summary.csv", data=csv_bytes, file_name="error_summary.csv", mime="text/csv")

if errors_df.empty:
    st.success("No SOP issues found. Your error summary is empty.")
else:
    st.info(f"Found {len(errors_df)} issues. Download the CSV above.")
