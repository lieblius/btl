# BTL Parser

Parse Sea-Bird `.btl` bottle summary files and extract a clean table of salinity and depth per bottle — ready to paste into Google Sheets.

## Usage

Upload a `.btl` file and get back a table with Bottle #, Sal00, and DepSM. Download as CSV or copy the tab-separated output directly.

## Deploy

This app is set up for [Streamlit Community Cloud](https://streamlit.io/cloud). Point it at this repo with `app.py` as the entrypoint.

## Run locally

```
uv run streamlit run app.py
```

## Test

```
uv run --extra test pytest
```
