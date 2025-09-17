# JPW Error Summary Only (Render-ready)

Minimal Streamlit app to generate **error_summary.csv** for the JPW weekly upload.

## SOP Rules Implemented
1. Avoid Duplicacy (Mobile/UserID in Lead/Partners/Merchants)
2. Enforce Proper Partner–Lead Mapping (every Lead mapped)

## Local Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Render
- Build Command: `pip install -r requirements.txt`
- Start Command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
