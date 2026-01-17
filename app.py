import streamlit as st
import os, io, json, base64
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

SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if not SERVICE_ACCOUNT_JSON:
    st.error("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable")
    st.stop()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FIXED_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1xW44N0s4moCUFfD2Q4Vz6tr7gYp9M6BE")

BATCH_SIZE = 50  # Load 50 images at a time

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

st.session_state.setdefault("all_images", [])  # Complete list (metadata only)
st.session_state.setdefault("current_batch", [])  # Current batch being worked on
st.session_state.setdefault("batch_start_idx", 0)
st.session_state.setdefault("index", 0)
st.session_state.setdefault("labels", {})
st.session_state.setdefault("current_name", "")
st.session_state.setdefault("current_side", "none")
st.session_state.setdefault("filter_unlabeled", False)
st.session_state.setdefault("current_image_data", None)
st.session_state.setdefault("images_loaded", False)

# =============================
# GOOGLE DRIVE
# =============================

@st.cache_resource
def drive_service():
    service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)

drive = drive_service()

@st.cache_data(show_spinner=False)
def list_all_drive_images(folder_id: str) -> List[Dict]:
    """Fetch ONLY metadata (id, name) of all images - very lightweight"""
    all_files = []
    page_token = None
    
    while True:
        try:
            q = f"'{folder_id}' in parents and trashed=false"
            res = drive.files().list(
                q=q,
                fields="nextPageToken, files(id,name,mimeType)",
                pageSize=100,
                pageToken=page_token
            ).execute()
            
            files = res.get("files", [])
            image_files = [f for f in files if f["mimeType"].startswith("image/")]
            all_files.extend(image_files)
            
            page_token = res.get("nextPageToken")
            if not page_token:
                break
                
        except Exception as e:
            st.error(f"Error fetching images: {e}")
            break
    
    return all_files

def download_image_as_base64(file_id: str) -> str:
    """Download image and return as base64"""
    try:
        request = drive.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        
        b64_data = base64.b64encode(fh.read()).decode()
        fh.close()
        
        return b64_data
    except Exception as e:
        st.error(f"Error downloading image: {e}")
        return None

# =============================
# BATCH MANAGEMENT
# =============================

def load_next_batch():
    """Load the next batch of images"""
    start = st.session_state.batch_start_idx
    end = start + BATCH_SIZE
    
    st.session_state.current_batch = st.session_state.all_images[start:end]
    st.session_state.index = 0
    
    if st.session_state.current_batch:
        load_current_image()

def get_batch_info():
    """Get current batch information"""
    total = len(st.session_state.all_images)
    start = st.session_state.batch_start_idx
    end = min(start + BATCH_SIZE, total)
    batch_num = (start // BATCH_SIZE) + 1
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    
    return {
        "start": start,
        "end": end,
        "batch_num": batch_num,
        "total_batches": total_batches,
        "total": total
    }

def has_next_batch():
    """Check if there's a next batch available"""
    return st.session_state.batch_start_idx + BATCH_SIZE < len(st.session_state.all_images)

def move_to_next_batch():
    """Move to next batch"""
    if has_next_batch():
        st.session_state.batch_start_idx += BATCH_SIZE
        load_next_batch()
        return True
    return False

def move_to_previous_batch():
    """Move to previous batch"""
    if st.session_state.batch_start_idx > 0:
        st.session_state.batch_start_idx -= BATCH_SIZE
        load_next_batch()
        return True
    return False

# =============================
# SUPABASE HELPERS
# =============================

@st.cache_data(ttl=30)
def load_labels():
    """Load labels from Supabase"""
    try:
        res = supabase.table("image_labels").select("*").execute()
        labels = {}
        for r in res.data:
            labels[r["image_name"]] = {
                "description": r["description"],
                "side": r.get("side", "none")
            }
        return labels
    except Exception as e:
        st.error(f"Error loading labels: {e}")
        return {}

def save_label(name: str, desc: str, side: str):
    """Save label to Supabase"""
    try:
        supabase.table("image_labels").upsert({
            "image_name": name,
            "description": desc,
            "side": side
        }).execute()
        st.session_state.labels[name] = {
            "description": desc,
            "side": side
        }
        load_labels.clear()
        get_unlabeled_image_names.clear()
        return True
    except Exception as e:
        st.error(f"Error saving label: {e}")
        return False

# =============================
# FILTER HELPERS
# =============================

@st.cache_data(ttl=30)
def get_unlabeled_image_names():
    """Get list of image names that are NOT in Supabase"""
    try:
        res = supabase.table("image_labels").select("image_name").execute()
        labeled_names = {r["image_name"] for r in res.data}
        all_image_names = {img["name"] for img in st.session_state.all_images}
        return all_image_names - labeled_names
    except Exception as e:
        st.error(f"Error getting unlabeled images: {e}")
        return set()

def get_filtered_images():
    """Return filtered list based on current filter settings"""
    if st.session_state.filter_unlabeled:
        unlabeled_names = get_unlabeled_image_names()
        return [img for img in st.session_state.current_batch if img["name"] in unlabeled_names]
    
    return st.session_state.current_batch

def find_next_unlabeled_in_batch():
    """Find next unlabeled image in current batch"""
    unlabeled_names = get_unlabeled_image_names()
    
    for i in range(st.session_state.index + 1, len(st.session_state.current_batch)):
        img = st.session_state.current_batch[i]
        if img["name"] in unlabeled_names:
            return i
    return None

def get_unlabeled_count_in_batch():
    """Count unlabeled images in current batch"""
    unlabeled_names = get_unlabeled_image_names()
    return sum(1 for img in st.session_state.current_batch if img["name"] in unlabeled_names)

# =============================
# IMAGE LOADER
# =============================

def load_current_image():
    """Load current image data"""
    filtered = get_filtered_images()
    if not filtered:
        return
    
    img = filtered[st.session_state.index]
    
    # Only download if different image
    if st.session_state.current_name != img["name"]:
        with st.spinner("Loading image..."):
            st.session_state.current_image_data = download_image_as_base64(img["id"])
            st.session_state.current_name = img["name"]
    
    # Load existing side if available
    if img["name"] in st.session_state.labels:
        st.session_state.current_side = st.session_state.labels[img["name"]].get("side", "none")
    else:
        st.session_state.current_side = "none"

# =============================
# INITIAL LOAD
# =============================

if not st.session_state.images_loaded:
    with st.spinner("Loading image list from Google Drive..."):
        st.session_state.all_images = list_all_drive_images(FIXED_FOLDER_ID)
        st.session_state.labels = load_labels()
        st.session_state.images_loaded = True
        
        if st.session_state.all_images:
            st.success(f"✅ Found {len(st.session_state.all_images)} total images")
            load_next_batch()

# =============================
# UI
# =============================

st.title("📂 Vehicle Damage Labeler (ICS)")

# Get batch info
batch_info = get_batch_info()

# Filter controls in sidebar
with st.sidebar:
    st.header("📊 Progress")
    
    unlabeled_names = get_unlabeled_image_names()
    total_images = len(st.session_state.all_images)
    unlabeled_count = len(unlabeled_names)
    labeled_count = total_images - unlabeled_count
    
    st.metric("📂 Total Images", total_images)
    st.metric("✅ Labeled", labeled_count)
    st.metric("⚠️ Unlabeled", unlabeled_count)
    
    if total_images > 0:
        progress_pct = labeled_count / total_images
        st.progress(progress_pct)
        st.caption(f"{progress_pct*100:.1f}% Complete")
    
    st.divider()
    
    # Batch Navigation
    st.header("📦 Batch Navigation")
    st.info(f"**Batch {batch_info['batch_num']} of {batch_info['total_batches']}**\n\nImages {batch_info['start']+1} - {batch_info['end']}")
    
    unlabeled_in_batch = get_unlabeled_count_in_batch()
    st.metric("Unlabeled in this batch", unlabeled_in_batch)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Prev\nBatch", use_container_width=True, disabled=st.session_state.batch_start_idx == 0):
            if move_to_previous_batch():
                st.rerun()
    
    with col2:
        if st.button("Next\nBatch ➡️", use_container_width=True, disabled=not has_next_batch(), type="primary"):
            if move_to_next_batch():
                st.rerun()
    
    st.divider()
    
    # Filters
    st.header("🔍 Filters")
    
    filter_changed = st.checkbox(
        "Show only unlabeled",
        value=st.session_state.filter_unlabeled,
        key="filter_checkbox"
    )
    
    if filter_changed != st.session_state.filter_unlabeled:
        st.session_state.filter_unlabeled = filter_changed
        st.session_state.index = 0
        load_current_image()
        st.rerun()
    
    if st.button("🎯 Next Unlabeled", use_container_width=True):
        next_idx = find_next_unlabeled_in_batch()
        if next_idx is not None:
            st.session_state.index = next_idx
            load_current_image()
            st.rerun()
        else:
            st.info("No more in batch!")
    
    st.divider()
    
    current_img_name = st.session_state.current_name
    if current_img_name in unlabeled_names:
        st.warning("⚠️ Current: UNLABELED")
    else:
        st.success("✅ Current: LABELED")
    
    if st.button("🔄 Refresh Data", use_container_width=True):
        load_labels.clear()
        get_unlabeled_image_names.clear()
        st.session_state.labels = load_labels()
        st.rerun()

tab1, tab2 = st.tabs(["🏷️ Labeling", "📊 Live Preview"])

# =============================
# TAB 1 — LABELING
# =============================

with tab1:
    filtered_images = get_filtered_images()
    
    if not filtered_images:
        st.warning("No images in current batch match the filter")
        st.info("Try changing the filter or moving to a different batch")
        st.stop()
    
    col1, col2 = st.columns([2, 1])
    
    # ---- IMAGE PANEL ----
    with col1:
        if st.session_state.current_image_data:
            st.markdown(
                f'<img src="data:image/jpeg;base64,{st.session_state.current_image_data}" style="width: 100%; border-radius: 8px;">',
                unsafe_allow_html=True
            )
        else:
            st.warning("Image not loaded")
            
        st.caption(f"**{st.session_state.current_name}**")
        st.progress((st.session_state.index + 1) / len(filtered_images))
        st.caption(f"Image {st.session_state.index + 1} of {len(filtered_images)} in current view")
    
    # ---- LABEL PANEL ----
    with col2:
        existing_data = st.session_state.labels.get(st.session_state.current_name, {})
        existing_desc = existing_data.get("description", "") if isinstance(existing_data, dict) else existing_data
        existing_side = existing_data.get("side", "none") if isinstance(existing_data, dict) else "none"
        
        if existing_desc and existing_desc != "None":
            st.info("📝 Already labeled")
        
        # SIDE SELECTION
        st.subheader("🚗 Vehicle Side")
        side_cols = st.columns(5)
        sides = {
            "front": "🔼",
            "back": "🔽",
            "left": "◀️",
            "right": "▶️",
            "none": "⚠️"
        }
        
        for idx, (side_key, side_icon) in enumerate(sides.items()):
            with side_cols[idx]:
                if st.button(
                    side_icon,
                    key=f"side_{side_key}",
                    use_container_width=True,
                    type="primary" if st.session_state.current_side == side_key else "secondary",
                    help=side_key.upper()
                ):
                    st.session_state.current_side = side_key
                    st.rerun()
        
        if st.session_state.current_side != "none":
            st.success(f"**{st.session_state.current_side.upper()}**")
        else:
            st.warning("No side selected")
        
        st.divider()
        
        # DAMAGE DESCRIPTION
        label = st.text_area(
            "Damage Description",
            value=existing_desc if existing_desc != "None" else "",
            height=100,
            placeholder="e.g. Front bumper dented"
        )
        
        st.divider()
        
        # ---- BUTTONS ----
        b1, b2, b3 = st.columns([1, 2, 1])
        with b1:
            if st.button("⬅️", use_container_width=True, disabled=st.session_state.index == 0):
                st.session_state.index -= 1
                load_current_image()
                st.rerun()
        with b2:
            if st.button("💾 Save & Next", type="primary", use_container_width=True):
                if label.strip():
                    if save_label(st.session_state.current_name, label.strip(), st.session_state.current_side):
                        if st.session_state.index < len(filtered_images) - 1:
                            st.session_state.index += 1
                            load_current_image()
                        st.success("Saved ✔")
                        st.rerun()
                else:
                    st.warning("Enter description")
        with b3:
            if st.button("➡️", use_container_width=True, disabled=st.session_state.index == len(filtered_images) - 1):
                st.session_state.index += 1
                load_current_image()
                st.rerun()
        
        st.divider()
        
        skip_confirm = st.checkbox("Confirm skip")
        if st.button("⏭️ Skip", use_container_width=True, disabled=not skip_confirm):
            if save_label(st.session_state.current_name, "None", "none"):
                if st.session_state.index < len(filtered_images) - 1:
                    st.session_state.index += 1
                    load_current_image()
                st.rerun()

# =============================
# TAB 2 — LIVE DATA
# =============================

with tab2:
    st.header("📊 Live Supabase Data")
    
    try:
        data = supabase.table("image_labels").select("*").execute().data
        df = pd.DataFrame(data)
        
        if not df.empty:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Labeled", len(df))
            with col2:
                labeled = len(df[df["side"] != "none"])
                st.metric("With Side", labeled)
            with col3:
                if "side" in df.columns:
                    sides_count = df[df["side"] != "none"]["side"].value_counts()
                    if not sides_count.empty:
                        st.metric("Most Common", sides_count.index[0].upper())
            
            if "side" in df.columns:
                st.subheader("Side Distribution")
                side_counts = df["side"].value_counts()
                st.bar_chart(side_counts)
            
            st.divider()
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No labels yet")
    except Exception as e:
        st.error(f"Error: {e}")

st.caption("⚡ Powered by Streamlit + Supabase")
