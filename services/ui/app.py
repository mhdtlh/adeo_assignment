import streamlit as st
import requests
import time
import logging
import os

# --- NEW: Create logs directory and configure file logging ---
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, "ui.log"))
    ]
)
logger = logging.getLogger("ADEO.UI")
# -------------------------------------------------------------

# Docker Service URLs
GATEWAY_URL = "http://adeo_api_gateway:8000"
INGEST_URL = "http://adeo_ingestion:8000"

st.set_page_config(page_title="ADEO AI", page_icon="🧠", layout="wide")
st.title("🧠 ADEO AI Assistant")

# --- SIDEBAR: Single File Repository Sync ---
with st.sidebar:
    st.header("📄 Repository Management")
    st.caption("Upload files directly to the `source_docs` folder.")
    
    # 'accept_multiple_files=False' ensures only one file is handled at a time
    uploaded_file = st.file_uploader(
        "Select a PDF to save to repo", 
        type=["pdf"], 
        accept_multiple_files=False
    )
    
    if uploaded_file is not None:
        # We use the file name as a key to ensure we only try the upload once per selection
        if f"last_uploaded_{uploaded_file.name}" not in st.session_state:
            with st.spinner("Checking repository..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                try:
                    # POST to upload endpoint (No ingestion call here)
                    resp = requests.post(f"{INGEST_URL}/upload", files=files)
                    result = resp.json()
                    
                    if result.get("status") == "success":
                        st.success(f"✅ Saved: {uploaded_file.name}")
                    elif result.get("status") == "duplicate":
                        st.warning(f"⚠️ Duplicate: {uploaded_file.name} is already in the repository.")
                    
                    # Mark this specific file as "attempted" so it doesn't loop
                    st.session_state[f"last_uploaded_{uploaded_file.name}"] = True
                    
                except Exception as e:
                    st.error(f"Connection Error: {e}")

# --- MAIN UI: Chat Interface ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask a question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        status_box = st.empty()
        status_box.info("Agent is searching...")
        
        try:
            payload = {
                "query": prompt,
                "history": st.session_state.messages[:-1] # Send previous turns
            }
            resp = requests.post(f"{GATEWAY_URL}/query", json=payload)
            resp.raise_for_status()
            tid = resp.json().get("request_id")
            
            for i in range(120):
                time.sleep(1)
                status_box.info(f"Agent is searching... ({i}s elapsed)")
                
                res = requests.get(f"{GATEWAY_URL}/result/{tid}")
                if res.status_code == 200:
                    data = res.json()
                    
                    if data.get("status") == "completed":
                        ans = data.get("answer", "No answer provided.")
                        
                        # --- MISSING CITATION LOGIC RESTORED HERE ---
                        try:
                            if data.get("citations"):
                                # Use a set to prevent printing duplicate pages
                                sources = set(f"- *{c.get('file_name', 'Unknown')}* (Page {c.get('page_label', 'N/A')})" for c in data['citations'])
                                ans += "\n\n**Sources:**\n" + "\n".join(sources)
                        except Exception as cite_err:
                            ans += f"\n\n*(Note: Error formatting citations: {cite_err})*"
                        # ----------------------------------------------
                        
                        status_box.empty()
                        st.markdown(ans)
                        st.session_state.messages.append({"role": "assistant", "content": ans})
                        break
                        
                    elif data.get("status") == "error":
                        status_box.error(f"Backend Error: {data.get('message')}")
                        break
                        
        except Exception as e:
            status_box.error(f"Error: {e}")