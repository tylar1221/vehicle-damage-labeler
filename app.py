import streamlit as st
import os
import io
import json
from PIL import Image
from typing import Dict
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import gc

# =============================
# PAGE CONFIG
# =============================
st.set_page_config(
    page_title="Google Drive Image Labeler",
    page_icon="📂",
    layout="wide",
)

# =============================
# CONSTANTS
# =============================
BATCH_SIZE = 50
TEMP_FOLDER = "/tmp/drive_images"  # safer on Streamlit Cloud
os.makedirs(TEMP_FOLDER, exist_ok=True)

MAX_IMAGE_SIZE = (1600, 1600)  # HARD memory cap

# =============================
# GOOGLE CONFIG
# =============================
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

if not SERVICE_ACCOUNT_JSON or not GOOGLE_DRIVE_FOLDER_ID:
    st.error("Missing Google credentials")
    st.stop()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# =============================
# SUPABASE CONFIG
# =============================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing Supabase credentials")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =============================
# SESSION STATE
# =============================
for k, v in {
    "images": [],
    "index": 0,
    "labels": {},
    "current_path": "",
    "current_name": "",
    "current_side": "none",
    "next_page_token": None,
}.items():
    st.session_state.setdefault(k, v)

# =============================
# GOOGLE DRIVE SERVICE
# =============================
@st.cache_resource
def drive_service():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(SERVICE_ACCOUNT_JSON),
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds)

drive = drive_service()

# =============================
# DRIVE HELPERS
# =============================
def list_drive_images_batch(folder_id, page_token=None):
    res = drive.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="nextPageToken, files(id,name,mimeType)",
        pageSize=BATCH_SIZE,
        pageToken=page_token,
    ).execute()

    images = [
        f for f in res.get("files", [])
        if f["mimeType"].startswith("image/")
    ]

    return images, res.get("nextPageToken")

def download_and_prepare_image(file_id, filename):
    """CRITICAL: memory-safe image handling"""
    request = drive.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    buffer.seek(0)

    # SAFE image processing
    with Image.open(buffer) as img:
        img = img.convert("RGB")
        img.thumbnail(MAX_IMAGE_SIZE)

        path = os.path.join(TEMP_FOLDER, filename)
        img.save(path, format="JPEG", quality=85, optimize=True)

    buffer.close()
    gc.collect()

    return path

# =============================
# SUPABASE HELPERS
# =============================
def load_labels():
    res = supabase.table("image_labels").select("*").execute()
    return {
        r["image_name"]: {
            "description": r["description"],
            "side": r.get("side", "none"),
        }
        for r in res.data
    }

def save_label(name, desc, side):
    supabase.table("image_labels").upsert(
        {
            "image_name": name,
            "description": desc,
            "side": side,
        }
    ).execute()

    st.session_state.labels[name] = {
        "description": desc,
        "side": side,
    }

# =============================
# IMAGE MANAGEMENT
# =============================
def clear_temp_folder():
    for f in os.listdir(TEMP_FOLDER):
        try:
            os.remove(os.path.join(TEMP_FOLDER, f))
        except Exception:
            pass
    gc.collect()

def load_current_image():
    img = st.session_state.images[st.session_state.index]
    path = download_and_prepare_image(img["id"], img["name"])

    st.session_state.current_path = path
    st.session_state.current_name = img["name"]
    st.session_state.current_side = (
        st.session_state.labels.get(img["name"], {}).get("side", "none")
    )

def load_next_batch():
    clear_temp_folder()

    images, token = list_drive_images_batch(
        GOOGLE_DRIVE_FOLDER_ID,
        st.session_state.next_page_token,
    )

    st.session_state.images = images
    st.session_state.index = 0
    st.session_state.next_page_token = token

    if images:
        load_current_image()

def batch_completed():
    return all(
        img["name"] in st.session_state.labels
        for img in st.session_state.images
    )

# =============================
# INITIAL LOAD
# =============================
if not st.session_state.images:
    with st.spinner("Loading image batch..."):
        st.session_state.labels = load_labels()
        load_next_batch()

# =============================
# UI
# =============================
st.title("📂 Vehicle Damage Labeler (Cloud-Safe)")

tab1, tab2 = st.tabs(["🏷️ Labeling", "📊 Live Preview"])

# =============================
# TAB 1
# =============================
with tab1:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.image(
            st.session_state.current_path,
            width="stretch",
        )
        st.caption(st.session_state.current_name)
        st.progress(
            (st.session_state.index + 1) / len(st.session_state.images)
        )

    with col2:
        label = st.text_area("Damage Description", height=120)
        side = st.radio(
            "Vehicle Side",
            ["front", "back", "left", "right", "none"],
            index=["front", "back", "left", "right", "none"].index(
                st.session_state.current_side
            ),
        )

        if st.button("💾 Save & Next", type="primary"):
            save_label(
                st.session_state.current_name,
                label or "None",
                side,
            )

            if st.session_state.index < len(st.session_state.images) - 1:
                st.session_state.index += 1
                load_current_image()

            st.rerun()

    if batch_completed():
        st.success("✅ Batch completed")

        if st.session_state.next_page_token:
            if st.button("➡ Load Next Batch"):
                load_next_batch()
                st.rerun()
        else:
            st.balloons()
            st.success("🎉 All images labeled")

# =============================
# TAB 2
# =============================
with tab2:
    data = supabase.table("image_labels").select("*").execute().data
    df = pd.DataFrame(data)

    if not df.empty:
        st.metric("Total Labels", len(df))
        st.bar_chart(df["side"].value_counts())
        st.dataframe(df, width="stretch")
    else:
        st.info("No labels yet")
