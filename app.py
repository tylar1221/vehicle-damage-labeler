# import streamlit as st
# import os
# import io
# import json
# from PIL import Image
# from typing import List, Dict
# from supabase import create_client
# from google.oauth2 import service_account
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaIoBaseDownload
# import pandas as pd


# # =============================
# # PAGE CONFIG
# # =============================
# st.set_page_config(
#     page_title="Google Drive Image Labeler",
#     page_icon="📂",
#     layout="wide",
# )


# # =============================
# # CONFIG
# # =============================
# SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
# if not SERVICE_ACCOUNT_JSON:
#     st.error("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable")
#     st.stop()

# SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# FIXED_FOLDER_ID = os.getenv(
#     "GOOGLE_DRIVE_FOLDER_ID",
#     "1xW44N0s4moCUFfD2Q4Vz6tr7gYp9M6BE",
# )

# TEMP_FOLDER = "./temp_drive"
# os.makedirs(TEMP_FOLDER, exist_ok=True)


# # =============================
# # SUPABASE CONFIG
# # =============================
# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# if not SUPABASE_URL or not SUPABASE_KEY:
#     st.error("Missing Supabase credentials in environment variables")
#     st.stop()

# supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# # =============================
# # SESSION STATE
# # =============================
# st.session_state.setdefault("images", [])
# st.session_state.setdefault("index", 0)
# st.session_state.setdefault("labels", {})
# st.session_state.setdefault("current_path", "")
# st.session_state.setdefault("current_name", "")
# st.session_state.setdefault("current_side", "none")


# # =============================
# # GOOGLE DRIVE
# # =============================
# @st.cache_resource
# def drive_service():
#     service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
#     creds = service_account.Credentials.from_service_account_info(
#         service_account_info,
#         scopes=SCOPES,
#     )
#     return build("drive", "v3", credentials=creds)


# drive = drive_service()


# def list_drive_images(folder_id: str) -> List[Dict]:
#     q = f"'{folder_id}' in parents and trashed=false"
#     res = (
#         drive.files()
#         .list(q=q, fields="files(id,name,mimeType)")
#         .execute()
#     )

#     return [
#         f for f in res.get("files", [])
#         if f["mimeType"].startswith("image/")
#     ]


# def download_image(file_id: str) -> io.BytesIO:
#     request = drive.files().get_media(fileId=file_id)
#     fh = io.BytesIO()
#     downloader = MediaIoBaseDownload(fh, request)

#     done = False
#     while not done:
#         _, done = downloader.next_chunk()

#     fh.seek(0)
#     return fh


# # =============================
# # SUPABASE HELPERS
# # =============================
# def load_labels():
#     res = supabase.table("image_labels").select("*").execute()
#     labels = {}

#     for r in res.data:
#         labels[r["image_name"]] = {
#             "description": r["description"],
#             "side": r.get("side", "none"),
#         }

#     return labels


# def save_label(name: str, desc: str, side: str):
#     supabase.table("image_labels").upsert(
#         {
#             "image_name": name,
#             "description": desc,
#             "side": side,
#         }
#     ).execute()

#     st.session_state.labels[name] = {
#         "description": desc,
#         "side": side,
#     }


# # =============================
# # IMAGE LOADER
# # =============================
# def load_current_image():
#     img = st.session_state.images[st.session_state.index]
#     data = download_image(img["id"])

#     image = Image.open(data)
#     path = os.path.join(TEMP_FOLDER, img["name"])
#     image.save(path)

#     st.session_state.current_path = path
#     st.session_state.current_name = img["name"]

#     if img["name"] in st.session_state.labels:
#         st.session_state.current_side = (
#             st.session_state.labels[img["name"]].get("side", "none")
#         )
#     else:
#         st.session_state.current_side = "none"


# # =============================
# # INITIAL LOAD
# # =============================
# if not st.session_state.images:
#     with st.spinner("Loading images from Google Drive..."):
#         st.session_state.images = list_drive_images(FIXED_FOLDER_ID)
#         st.session_state.labels = load_labels()

#     if st.session_state.images:
#         load_current_image()


# # =============================
# # UI
# # =============================
# st.title("📂 Vehicle Damage Labeler (ICS)")
# tab1, tab2 = st.tabs(["🏷️ Labeling", "📊 Live Preview"])


# # =============================
# # TAB 1 — LABELING
# # =============================
# with tab1:
#     if not st.session_state.images:
#         st.warning("No images found")
#         st.stop()

#     col1, col2 = st.columns([2, 1])

#     # IMAGE PANEL
#     with col1:
#         st.image(st.session_state.current_path, use_container_width=True)
#         st.caption(st.session_state.current_name)

#         st.progress(
#             (st.session_state.index + 1)
#             / len(st.session_state.images)
#         )

#         st.caption(
#             f"Image {st.session_state.index + 1} "
#             f"of {len(st.session_state.images)}"
#         )

#     # LABEL PANEL
#     with col2:
#         existing_data = st.session_state.labels.get(
#             st.session_state.current_name,
#             {},
#         )

#         existing_desc = existing_data.get("description", "")
#         existing_side = existing_data.get("side", "none")

#         if existing_desc:
#             st.info("📝 This image already has a label")

#         st.subheader("🚗 Vehicle Side")
#         side_cols = st.columns(5)

#         sides = {
#             "front": "🔼 Front",
#             "back": "🔽 Back",
#             "left": "◀️ Left",
#             "right": "▶️ Right",
#             "none": "⚠️ NONE",
#         }

#         for idx, (side_key, side_label) in enumerate(sides.items()):
#             with side_cols[idx]:
#                 if st.button(
#                     side_label,
#                     key=f"side_{side_key}",
#                     use_container_width=True,
#                     type="primary"
#                     if existing_side == side_key
#                     else "secondary",
#                 ):
#                     st.session_state.current_side = side_key
#                     st.rerun()

#         if st.session_state.current_side != "none":
#             st.success(
#                 f"Selected: "
#                 f"**{st.session_state.current_side.upper()}**"
#             )
#         else:
#             st.warning("⚠️ No side selected")

#         st.divider()

#         label = st.text_area(
#             "Damage Description",
#             value=existing_desc,
#             height=120,
#             placeholder="e.g. Front bumper dented, headlight cracked",
#         )

#         st.divider()

#         b1, b2, b3 = st.columns([1, 2, 1])

#         with b1:
#             prev_clicked = st.button(
#                 "⬅️ Prev",
#                 use_container_width=True,
#                 disabled=st.session_state.index == 0,
#             )

#         with b2:
#             save_clicked = st.button(
#                 "💾 Save & Next",
#                 type="primary",
#                 use_container_width=True,
#             )

#         with b3:
#             next_clicked = st.button(
#                 "➡️ Next",
#                 use_container_width=True,
#                 disabled=(
#                     st.session_state.index
#                     == len(st.session_state.images) - 1
#                 ),
#             )

#         st.divider()

#         skip_confirm = st.checkbox("Confirm skip (save as None)")
#         skip_clicked = st.button(
#             "⏭️ Skip Image",
#             use_container_width=True,
#             disabled=not skip_confirm,
#         )

#         if prev_clicked:
#             st.session_state.index -= 1
#             load_current_image()
#             st.rerun()

#         if save_clicked:
#             if label.strip():
#                 save_label(
#                     st.session_state.current_name,
#                     label.strip(),
#                     st.session_state.current_side,
#                 )

#                 if (
#                     st.session_state.index
#                     < len(st.session_state.images) - 1
#                 ):
#                     st.session_state.index += 1
#                     load_current_image()

#                 st.success("Saved ✔")
#                 st.rerun()
#             else:
#                 st.warning("Please enter a description")

#         if next_clicked:
#             st.session_state.index += 1
#             load_current_image()
#             st.rerun()

#         if skip_clicked:
#             save_label(
#                 st.session_state.current_name,
#                 "None",
#                 "none",
#             )

#             if (
#                 st.session_state.index
#                 < len(st.session_state.images) - 1
#             ):
#                 st.session_state.index += 1
#                 load_current_image()

#             st.warning("Skipped")
#             st.rerun()


# # =============================
# # TAB 2 — LIVE DATA
# # =============================
# with tab2:
#     st.header("📊 Live Supabase Data")

#     data = (
#         supabase.table("image_labels")
#         .select("*")
#         .execute()
#         .data
#     )

#     df = pd.DataFrame(data)

#     if not df.empty:
#         col1, col2, col3 = st.columns(3)

#         with col1:
#             st.metric("Total Labeled Images", len(df))

#         with col2:
#             labeled = len(df[df["side"] != "none"])
#             st.metric("Images with Side Selected", labeled)

#         with col3:
#             sides_count = (
#                 df[df["side"] != "none"]["side"].value_counts()
#             )
#             if not sides_count.empty:
#                 st.metric(
#                     "Most Common Side",
#                     sides_count.index[0].upper(),
#                 )

#         st.subheader("Side Distribution")
#         st.bar_chart(df["side"].value_counts())

#         st.divider()
#         st.subheader("All Labels")
#         st.dataframe(df, use_container_width=True)

#     else:
#         st.info("No labels yet")

#     st.caption("⚡ Realtime labeling powered by Streamlit + Supabase")
import streamlit as st
import os
import io
import json
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
    layout="wide",
)

# =============================
# CONFIG
# =============================
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if not SERVICE_ACCOUNT_JSON:
    st.error("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable")
    st.stop()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FIXED_FOLDER_ID = os.getenv(
    "GOOGLE_DRIVE_FOLDER_ID",
    "1xW44N0s4moCUFfD2Q4Vz6tr7gYp9M6BE",
)

TEMP_FOLDER = "./temp_drive"
os.makedirs(TEMP_FOLDER, exist_ok=True)

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
st.session_state.setdefault("all_images", [])
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
    creds = service_account.Credentials.from_service_account_info(
        json.loads(SERVICE_ACCOUNT_JSON),
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds)

drive = drive_service()

def list_drive_images(folder_id: str) -> List[Dict]:
    images = []
    page_token = None

    while True:
        res = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id,name,mimeType)",
            pageToken=page_token,
            pageSize=1000,
        ).execute()

        images.extend(
            [f for f in res.get("files", []) if f["mimeType"].startswith("image/")]
        )

        page_token = res.get("nextPageToken")
        if not page_token:
            break

    return images

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
    return {
        r["image_name"]: {
            "description": r["description"],
            "side": r.get("side", "none"),
        }
        for r in res.data
    }

def get_labeled_image_names():
    res = supabase.table("image_labels") \
        .select("image_name, description") \
        .execute()

    return {
        r["image_name"]
        for r in res.data
        if r["description"] and r["description"] != "None"
    }

def save_label(name: str, desc: str, side: str):
    supabase.table("image_labels").upsert({
        "image_name": name,
        "description": desc,
        "side": side,
    }).execute()

    st.session_state.labels[name] = {
        "description": desc,
        "side": side,
    }

# =============================
# IMAGE LOADER
# =============================
def load_current_image():
    if not st.session_state.images:
        return

    img = st.session_state.images[st.session_state.index]
    data = download_image(img["id"])
    image = Image.open(data)

    path = os.path.join(TEMP_FOLDER, img["name"])
    image.save(path)

    st.session_state.current_path = path
    st.session_state.current_name = img["name"]

    label = st.session_state.labels.get(img["name"])
    st.session_state.current_side = label["side"] if label else "none"

# =============================
# INITIAL LOAD (AUTO RESUME)
# =============================
if not st.session_state.all_images:
    with st.spinner("Loading images from Google Drive..."):
        st.session_state.all_images = list_drive_images(FIXED_FOLDER_ID)
        st.session_state.labels = load_labels()

    labeled_names = {
        name for name, v in st.session_state.labels.items()
        if v["description"] != "None"
    }

    for i, img in enumerate(st.session_state.all_images):
        if img["name"] not in labeled_names:
            st.session_state.index = i
            break

# =============================
# UI
# =============================
st.title("📂 Vehicle Damage Labeler (ICS)")
tab1, tab2 = st.tabs(["🏷️ Labeling", "📊 Live Preview"])

# =============================
# TAB 1 — LABELING
# =============================
with tab1:
    filter_mode = st.radio(
        "🔍 Show Images",
        ["All Images", "Only Unlabeled"],
        horizontal=True,
    )

    labeled_names = get_labeled_image_names()

    if filter_mode == "Only Unlabeled":
        st.session_state.images = [
            img for img in st.session_state.all_images
            if img["name"] not in labeled_names
        ]
        st.session_state.index = 0
    else:
        st.session_state.images = st.session_state.all_images

    if not st.session_state.images:
        st.success("🎉 All images are labeled!")
        st.stop()

    if st.session_state.index >= len(st.session_state.images):
        st.session_state.index = 0

    load_current_image()

    col1, col2 = st.columns([2, 1])

    with col1:
        st.image(st.session_state.current_path, use_container_width=True)
        st.caption(st.session_state.current_name)
        st.progress((st.session_state.index + 1) / len(st.session_state.images))
        st.caption(f"{st.session_state.index + 1} of {len(st.session_state.images)}")

    with col2:
        existing = st.session_state.labels.get(st.session_state.current_name, {})
        desc = existing.get("description", "")

        st.subheader("🚗 Vehicle Side")
        side = st.radio(
            "Side",
            ["front", "back", "left", "right", "none"],
            index=["front", "back", "left", "right", "none"].index(
                st.session_state.current_side
            ),
        )

        label = st.text_area(
            "Damage Description",
            value=desc,
            height=120,
        )

        b1, b2, b3 = st.columns(3)

        with b1:
            if st.button("⬅️ Prev", disabled=st.session_state.index == 0):
                st.session_state.index -= 1
                st.rerun()

        with b2:
            if st.button("💾 Save & Next", type="primary"):
                if label.strip():
                    save_label(
                        st.session_state.current_name,
                        label.strip(),
                        side,
                    )
                    st.session_state.index = min(
                        st.session_state.index + 1,
                        len(st.session_state.images) - 1,
                    )
                    st.rerun()
                else:
                    st.warning("Description required")

        with b3:
            if st.button(
                "➡️ Next",
                disabled=st.session_state.index == len(st.session_state.images) - 1,
            ):
                st.session_state.index += 1
                st.rerun()

# =============================
# TAB 2 — LIVE DATA
# =============================
with tab2:
    st.header("📊 Live Supabase Data")

    data = supabase.table("image_labels").select("*").execute().data
    df = pd.DataFrame(data)

    if not df.empty:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Labeled", len(df))
        with c2:
            st.metric("Total Images", len(st.session_state.all_images))
        with c3:
            st.metric(
                "Progress",
                f"{round((len(df)/len(st.session_state.all_images))*100, 2)}%",
            )

        st.bar_chart(df["side"].value_counts())
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No labels yet")

st.caption("⚡ Streamlit + Supabase + Google Drive")

