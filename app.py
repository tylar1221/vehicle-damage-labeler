import streamlit as st
import os, io, json, gc
from PIL import Image
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd

# =====================================================
# PAGE CONFIG (SAFE)
# =====================================================
st.set_page_config(
    page_title="Google Drive Image Labeler",
    page_icon="📂",
    layout="wide",
)

# =====================================================
# CONSTANTS
# =====================================================
BATCH_SIZE = 40                  # SAFE batch size
TEMP_FOLDER = "/tmp/drive_imgs"  # Streamlit Cloud safe
MAX_IMAGE_SIZE = (1600, 1600)

os.makedirs(TEMP_FOLDER, exist_ok=True)

# =====================================================
# ENV CHECK (NO NETWORK CALLS HERE)
# =====================================================
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

missing = []
if not SERVICE_ACCOUNT_JSON: missing.append("GOOGLE_SERVICE_ACCOUNT_JSON")
if not DRIVE_FOLDER_ID: missing.append("GOOGLE_DRIVE_FOLDER_ID")
if not SUPABASE_URL: missing.append("SUPABASE_URL")
if not SUPABASE_KEY: missing.append("SUPABASE_KEY")

if missing:
    st.error(f"Missing env vars: {', '.join(missing)}")
    st.stop()

# =====================================================
# SESSION STATE (LIGHTWEIGHT)
# =====================================================
defaults = {
    "started": False,
    "drive": None,
    "images": [],
    "index": 0,
    "labels": {},
    "next_token": None,
    "current_path": "",
    "current_name": "",
    "current_side": "none",
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# =====================================================
# SAFE START GATE (CRITICAL FOR CLOUD)
# =====================================================
st.title("📂 Vehicle Damage Labeler (Cloud Safe)")

if not st.session_state.started:
    st.info("Click start to initialize Google Drive & Supabase")
    if st.button("🚀 Start Labeling Session"):
        st.session_state.started = True
        st.rerun()
    st.stop()   # <<< HEALTH CHECK PASSES HERE

# =====================================================
# LAZY GOOGLE DRIVE
# =====================================================
@st.cache_resource
def create_drive():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(SERVICE_ACCOUNT_JSON),
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)

def get_drive():
    if st.session_state.drive is None:
        st.session_state.drive = create_drive()
    return st.session_state.drive

# =====================================================
# SUPABASE (LAZY SAFE)
# =====================================================
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

# =====================================================
# HELPERS
# =====================================================
def clear_temp():
    for f in os.listdir(TEMP_FOLDER):
        try:
            os.remove(os.path.join(TEMP_FOLDER, f))
        except:
            pass
    gc.collect()

def list_drive_batch(page_token=None):
    drive = get_drive()
    res = drive.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
        fields="nextPageToken, files(id,name,mimeType)",
        pageSize=BATCH_SIZE,
        pageToken=page_token,
    ).execute()

    images = [
        f for f in res.get("files", [])
        if f["mimeType"].startswith("image/")
    ]
    return images, res.get("nextPageToken")

def download_image(file_id, name):
    drive = get_drive()
    req = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, req)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    buf.seek(0)
    with Image.open(buf) as img:
        img = img.convert("RGB")
        img.thumbnail(MAX_IMAGE_SIZE)
        path = os.path.join(TEMP_FOLDER, name)
        img.save(path, "JPEG", quality=85, optimize=True)

    buf.close()
    gc.collect()
    return path

def load_labels():
    try:
        res = supabase.table("image_labels").select("*").execute()
        return {
            r["image_name"]: {
                "description": r["description"],
                "side": r.get("side", "none"),
            }
            for r in res.data
        }
    except:
        return {}

def save_label(name, desc, side):
    supabase.table("image_labels").upsert({
        "image_name": name,
        "description": desc,
        "side": side,
    }).execute()

    st.session_state.labels[name] = {
        "description": desc,
        "side": side,
    }

def load_current():
    img = st.session_state.images[st.session_state.index]
    st.session_state.current_path = download_image(img["id"], img["name"])
    st.session_state.current_name = img["name"]
    st.session_state.current_side = (
        st.session_state.labels.get(img["name"], {}).get("side", "none")
    )

def load_next_batch():
    clear_temp()
    imgs, token = list_drive_batch(st.session_state.next_token)
    st.session_state.images = imgs
    st.session_state.index = 0
    st.session_state.next_token = token
    if imgs:
        load_current()

def batch_done():
    return all(i["name"] in st.session_state.labels for i in st.session_state.images)

# =====================================================
# INITIAL LOAD (AFTER START BUTTON)
# =====================================================
if not st.session_state.images:
    with st.spinner("Initializing batch..."):
        st.session_state.labels = load_labels()
        load_next_batch()

# =====================================================
# UI
# =====================================================
tab1, tab2 = st.tabs(["🏷️ Labeling", "📊 Live Data"])

# ---------------- LABELING TAB ----------------
with tab1:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.image(st.session_state.current_path, width="stretch")
        st.caption(st.session_state.current_name)
        st.progress((st.session_state.index + 1) / len(st.session_state.images))

    with col2:
        desc = st.text_area("Damage Description", height=120)
        side = st.radio(
            "Vehicle Side",
            ["front", "back", "left", "right", "none"],
            index=["front","back","left","right","none"].index(
                st.session_state.current_side
            ),
        )

        if st.button("💾 Save & Next", type="primary"):
            save_label(st.session_state.current_name, desc or "None", side)

            if st.session_state.index < len(st.session_state.images) - 1:
                st.session_state.index += 1
                load_current()

            st.rerun()

    if batch_done():
        st.success("✅ Batch completed")
        if st.session_state.next_token:
            if st.button("➡ Load Next Batch"):
                load_next_batch()
                st.rerun()
        else:
            st.balloons()
            st.success("🎉 All images labeled")

# ---------------- LIVE DATA TAB ----------------
with tab2:
    data = supabase.table("image_labels").select("*").execute().data
    df = pd.DataFrame(data)

    if not df.empty:
        st.metric("Total Labels", len(df))
        st.bar_chart(df["side"].value_counts())
        st.dataframe(df, width="stretch")
    else:
        st.info("No labels yet")
