import streamlit as st
import os, io, json
from PIL import Image
from typing import List, Dict
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd

# ============================= 
# PAGE CONFIG
# ============================= 
st.set_page_config(
    page_title="Google Drive Image Labeler",
    page_icon="📂",
    layout="wide"
)

# ============================= 
# CONFIG
# ============================= 
# Load service account from environment variable (JSON string)
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if not SERVICE_ACCOUNT_JSON:
    st.error("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable")
    st.stop()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FIXED_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1xW44N0s4moCUFfD2Q4Vz6tr7gYp9M6BE")
TEMP_FOLDER = "./temp_drive"
os.makedirs(TEMP_FOLDER, exist_ok=True)

# ============================= 
# SUPABASE CONFIG
# ============================= 
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing Supabase credentials in environment variables")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================= 
# SESSION STATE
# ============================= 
st.session_state.setdefault("images", [])
st.session_state.setdefault("index", 0)
st.session_state.setdefault("labels", {})
st.session_state.setdefault("current_path", "")
st.session_state.setdefault("current_name", "")
st.session_state.setdefault("current_side", "none")

# ============================= 
# GOOGLE DRIVE
# ============================= 
@st.cache_resource
def drive_service():
    # Parse the JSON string from environment variable
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)

drive = drive_service()

def list_drive_images(folder_id: str) -> List[Dict]:
    q = f"'{folder_id}' in parents and trashed=false"
    res = drive.files().list(
        q=q,
        fields="files(id,name,mimeType)"
    ).execute()
    return [f for f in res.get("files", []) if f["mimeType"].startswith("image/")]

def download_image(file_id: str) -> io.BytesIO:
    request = drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh

# ============================= 
# SUPABASE HELPERS
# ============================= 
def load_labels():
    res = supabase.table("image_labels").select("*").execute()
    labels = {}
    for r in res.data:
        labels[r["image_name"]] = {
            "description": r["description"],
            "side": r.get("side", "none")
        }
    return labels

def save_label(name: str, desc: str, side: str):
    supabase.table("image_labels").upsert({
        "image_name": name,
        "description": desc,
        "side": side
    }).execute()
    st.session_state.labels[name] = {
        "description": desc,
        "side": side
    }

# ============================= 
# IMAGE LOADER
# ============================= 
def load_current_image():
    img = st.session_state.images[st.session_state.index]
    data = download_image(img["id"])
    image = Image.open(data)
    path = os.path.join(TEMP_FOLDER, img["name"])
    image.save(path)
    st.session_state.current_path = path
    st.session_state.current_name = img["name"]
    
    # Load existing side if available
    if img["name"] in st.session_state.labels:
        st.session_state.current_side = st.session_state.labels[img["name"]].get("side", "none")
    else:
        st.session_state.current_side = "none"

# ============================= 
# INITIAL LOAD
# ============================= 
if not st.session_state.images:
    with st.spinner("Loading images from Google Drive..."):
        st.session_state.images = list_drive_images(FIXED_FOLDER_ID)
        st.session_state.labels = load_labels()
        if st.session_state.images:
            load_current_image()

# ============================= 
# UI
# ============================= 
st.title("📂 Vehicle Damage Labeler (ICS)")

tab1, tab2 = st.tabs(["🏷️ Labeling", "📊 Live Preview"])

# ============================= 
# TAB 1 — LABELING
# ============================= 
with tab1:
    if not st.session_state.images:
        st.warning("No images found")
        st.stop()
    
    col1, col2 = st.columns([2, 1])
    
    # ---- IMAGE PANEL ----
    with col1:
        st.image(st.session_state.current_path, use_container_width=True)
        st.caption(st.session_state.current_name)
        st.progress(
            (st.session_state.index + 1) / len(st.session_state.images)
        )
        st.caption(
            f"Image {st.session_state.index + 1} of {len(st.session_state.images)}"
        )
    
    # ---- LABEL PANEL ----
    with col2:
        existing_data = st.session_state.labels.get(
            st.session_state.current_name, {}
        )
        existing_desc = existing_data.get("description", "") if isinstance(existing_data, dict) else existing_data
        existing_side = existing_data.get("side", "none") if isinstance(existing_data, dict) else "none"
        
        if existing_desc:
            st.info("📝 This image already has a label")
        
        # SIDE SELECTION
        st.subheader("🚗 Vehicle Side")
        side_cols = st.columns(5)
        sides = {
            "front": "🔼 Front",
            "back": "🔽 Back",
            "left": "◀️ Left",
            "right": "▶️ Right",
            "NONE": "⚠️ NONE"
        }
        
        selected_side = existing_side
        for idx, (side_key, side_label) in enumerate(sides.items()):
            with side_cols[idx]:
                if st.button(
                    side_label,
                    key=f"side_{side_key}",
                    use_container_width=True,
                    type="primary" if existing_side == side_key else "secondary"
                ):
                    st.session_state.current_side = side_key
                    selected_side = side_key
                    st.rerun()
        
        # Show current selection
        if st.session_state.current_side != "none":
            st.success(f"Selected: **{st.session_state.current_side.upper()}**")
        else:
            st.warning("⚠️ No side selected")
        
        st.divider()
        
        # DAMAGE DESCRIPTION
        label = st.text_area(
            "Damage Description",
            value=existing_desc,
            height=120,
            placeholder="e.g. Front bumper dented, headlight cracked"
        )
        
        st.divider()
        
        # ---- MAIN ACTION BUTTONS ----
        b1, b2, b3 = st.columns([1, 2, 1])
        with b1:
            prev_clicked = st.button(
                "⬅️ Prev",
                use_container_width=True,
                disabled=st.session_state.index == 0
            )
        with b2:
            save_clicked = st.button(
                "💾 Save & Next",
                type="primary",
                use_container_width=True
            )
        with b3:
            next_clicked = st.button(
                "➡️ Next",
                use_container_width=True,
                disabled=st.session_state.index == len(st.session_state.images) - 1
            )
        
        st.divider()
        
        # ---- SAFE SKIP ----
        skip_confirm = st.checkbox("Confirm skip (save as None)")
        skip_clicked = st.button(
            "⏭️ Skip Image",
            use_container_width=True,
            disabled=not skip_confirm
        )
        
        # ---- LOGIC ----
        if prev_clicked:
            st.session_state.index -= 1
            load_current_image()
            st.rerun()
        
        if save_clicked:
            if label.strip():
                save_label(
                    st.session_state.current_name,
                    label.strip(),
                    st.session_state.current_side
                )
                if st.session_state.index < len(st.session_state.images) - 1:
                    st.session_state.index += 1
                    load_current_image()
                st.success("Saved ✔")
                st.rerun()
            else:
                st.warning("Please enter a description")
        
        if next_clicked:
            st.session_state.index += 1
            load_current_image()
            st.rerun()
        
        if skip_clicked:
            save_label(st.session_state.current_name, "None", "none")
            if st.session_state.index < len(st.session_state.images) - 1:
                st.session_state.index += 1
                load_current_image()
            st.warning("Skipped")
            st.rerun()

# ============================= 
# TAB 2 — LIVE DATA
# ============================= 
with tab2:
    st.header("📊 Live Supabase Data")
    data = supabase.table("image_labels").select("*").execute().data
    df = pd.DataFrame(data)
    
    if not df.empty:
        # Statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Labeled Images", len(df))
        with col2:
            labeled = len(df[df["side"] != "none"])
            st.metric("Images with Side Selected", labeled)
        with col3:
            if "side" in df.columns:
                sides_count = df[df["side"] != "none"]["side"].value_counts()
                if not sides_count.empty:
                    most_common = sides_count.index[0]
                    st.metric("Most Common Side", most_common.upper())
        
        # Side distribution
        if "side" in df.columns:
            st.subheader("Side Distribution")
            side_counts = df["side"].value_counts()
            st.bar_chart(side_counts)
        
        st.divider()
        st.subheader("All Labels")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No labels yet")

st.caption("⚡ Realtime labeling powered by Streamlit + Supabase")