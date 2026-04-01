"""
BTL Parser - Sea-Bird Bottle Summary File Parser

Standalone Streamlit app. Run with:
    uv run streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from parsing import extract_bottle_table

st.set_page_config(page_title="BTL Parser", layout="wide")

# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.title("BTL Parser")
st.caption("Sea-Bird Bottle Summary File Parser")

uploaded = st.file_uploader(
    "Upload a .btl file (any extension accepted)",
    type=None,
    key="btl_file",
)

if not uploaded:
    st.info("Upload a Sea-Bird bottle summary file to extract salinity and depth data.")
    st.stop()

# Read and parse
raw = uploaded.read()
try:
    text = raw.decode("utf-8", errors="replace")
except Exception:
    text = raw.decode("latin-1", errors="replace")

try:
    header, result_df, all_columns, col_mapping = extract_bottle_table(text)
except Exception as e:
    st.error(f"Failed to parse **{uploaded.name}** as a BTL file: {e}")
    st.stop()

# -- Header metadata (collapsible) -----------------------------------------

with st.expander("File metadata", expanded=False):
    meta_parts = []
    if header.filename:
        meta_parts.append(f"**File:** {header.filename}")
    if header.cruise_date:
        meta_parts.append(f"**Date:** {header.cruise_date}")
    if header.latitude:
        meta_parts.append(f"**Lat:** {header.latitude}")
    if header.longitude:
        meta_parts.append(f"**Lon:** {header.longitude}")
    if header.station:
        meta_parts.append(f"**Station:** {header.station}")
    if meta_parts:
        st.markdown("  \n".join(meta_parts))
    else:
        st.caption("No metadata found in header.")

    st.caption(f"**All columns found:** {', '.join(all_columns)}")

# -- Missing columns warning -----------------------------------------------

if result_df.empty:
    st.error("No bottle data found in this file.")
    st.stop()

if "Sal00" not in result_df.columns:
    st.warning(
        f"Could not find a salinity column. Looked for: Sal00, Sal0, sal00.  \n"
        f"Columns available: {', '.join(all_columns)}"
    )

if "DepSM" not in result_df.columns and "PrDM" not in result_df.columns:
    st.warning(
        f"Could not find a depth column. Looked for: DepSM, depSM, DepS, PrDM.  \n"
        f"Columns available: {', '.join(all_columns)}"
    )

# -- Column mapping info ----------------------------------------------------

if col_mapping:
    mapping_parts = [f"{display} \u2190 {actual}" for display, actual in col_mapping.items()]
    st.caption(f"Column mapping: {', '.join(mapping_parts)}")

# -- Results table ----------------------------------------------------------

st.subheader(f"Bottle Data ({len(result_df)} bottles)")

# Highlight unusual values
def highlight_salinity(val):
    """Flag salinity values outside typical ocean range."""
    try:
        v = float(val)
        if v < 30 or v > 40:
            return "background-color: #fff3cd"
    except (ValueError, TypeError):
        pass
    return ""


styled_df = result_df.style.format(precision=4)
if "Sal00" in result_df.columns:
    styled_df = styled_df.map(highlight_salinity, subset=["Sal00"])

st.dataframe(
    styled_df,
    width="stretch",
    hide_index=True,
    height=min(len(result_df) * 35 + 38, 800),
)

# -- Copy to clipboard (tab-separated for Google Sheets) -------------------

tsv = result_df.to_csv(sep="\t", index=False)
st.code(tsv, language=None)
st.caption("Select and copy the text above, or use the button below.")

st.download_button(
    "Download as CSV",
    result_df.to_csv(index=False),
    file_name=f"{uploaded.name.rsplit('.', 1)[0]}_bottles.csv",
    mime="text/csv",
)
