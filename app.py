# # import os
# # import io
# # import json
# # from typing import List, Dict

# # import streamlit as st
# # import pandas as pd
# # from PIL import Image

# # from supabase import create_client
# # from google.oauth2 import service_account
# # from googleapiclient.discovery import build
# # from googleapiclient.http import MediaIoBaseDownload


# # # =============================
# # # PAGE CONFIG
# # # =============================
# # st.set_page_config(
# #     page_title="Google Drive Image Labeler",
# #     page_icon="📂",
# #     layout="wide",
# # )


# # # =============================
# # # CONFIG
# # # =============================
# # SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
# # if not SERVICE_ACCOUNT_JSON:
# #     st.error("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable")
# #     st.stop()

# # SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# # FIXED_FOLDER_ID = os.getenv(
# #     "GOOGLE_DRIVE_FOLDER_ID",
# #     "1xW44N0s4moCUFfD2Q4Vz6tr7gYp9M6BE",
# # )

# # TEMP_FOLDER = "./temp_drive"
# # os.makedirs(TEMP_FOLDER, exist_ok=True)


# # # =============================
# # # SUPABASE CONFIG
# # # =============================
# # SUPABASE_URL = os.getenv("SUPABASE_URL")
# # SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# # if not SUPABASE_URL or not SUPABASE_KEY:
# #     st.error("Missing Supabase credentials")
# #     st.stop()

# # supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# # # =============================
# # # SESSION STATE
# # # =============================
# # st.session_state.setdefault("all_images", [])
# # st.session_state.setdefault("images", [])
# # st.session_state.setdefault("index", 0)
# # st.session_state.setdefault("labels", {})
# # st.session_state.setdefault("current_path", "")
# # st.session_state.setdefault("current_name", "")
# # st.session_state.setdefault("current_side", "none")


# # # =============================
# # # GOOGLE DRIVE
# # # =============================
# # @st.cache_resource
# # def drive_service():
# #     # import certifi
# #     # import httplib2
# #     # from google_auth_httplib2 import AuthorizedHttp
    
# #     creds = service_account.Credentials.from_service_account_info(
# #         json.loads(SERVICE_ACCOUNT_JSON),
# #         scopes=SCOPES,
# #     )
  
# #     return build("drive", "v3", credentials=creds, )


# # drive = drive_service()


# # def list_drive_images(folder_id: str) -> List[Dict]:
# #     images = []
# #     page_token = None

# #     while True:
# #         res = (
# #             drive.files()
# #             .list(
# #                 q=f"'{folder_id}' in parents and trashed=false",
# #                 fields="nextPageToken, files(id,name,mimeType)",
# #                 pageToken=page_token,
# #                 pageSize=1000,
# #             )
# #             .execute()
# #         )

# #         images.extend(
# #             [
# #                 f
# #                 for f in res.get("files", [])
# #                 if f["mimeType"].startswith("image/")
# #             ]
# #         )

# #         page_token = res.get("nextPageToken")
# #         if not page_token:
# #             break

# #     return images


# # def download_image(file_id: str) -> io.BytesIO:
# #     request = drive.files().get_media(fileId=file_id)
# #     fh = io.BytesIO()
# #     downloader = MediaIoBaseDownload(fh, request)

# #     done = False
# #     while not done:
# #         _, done = downloader.next_chunk()

# #     fh.seek(0)
# #     return fh


# # # =============================
# # # SUPABASE HELPERS
# # # =============================
# # def load_labels():
# #     res = supabase.table("image_labels").select("*").execute()
# #     return {
# #         r["image_name"]: {
# #             "description": r["description"],
# #             "side": r.get("side", "none"),
# #         }
# #         for r in res.data
# #     }


# # def get_labeled_image_names():
# #     res = (
# #         supabase.table("image_labels")
# #         .select("image_name, description")
# #         .execute()
# #     )
# #     return {
# #         r["image_name"]
# #         for r in res.data
# #         if r["description"] and r["description"] != "None"
# #     }


# # def save_label(name: str, desc: str, side: str):
# #     supabase.table("image_labels").upsert(
# #         {
# #             "image_name": name,
# #             "description": desc,
# #             "side": side,
# #         }
# #     ).execute()

# #     st.session_state.labels[name] = {
# #         "description": desc,
# #         "side": side,
# #     }


# # # =============================
# # # IMAGE LOADER
# # # =============================
# # def load_current_image():
# #     if not st.session_state.images:
# #         return

# #     img = st.session_state.images[st.session_state.index]
# #     data = download_image(img["id"])
# #     image = Image.open(data)

# #     path = os.path.join(TEMP_FOLDER, img["name"])
# #     image.save(path)

# #     st.session_state.current_path = path
# #     st.session_state.current_name = img["name"]

# #     label = st.session_state.labels.get(img["name"])
# #     st.session_state.current_side = label["side"] if label else "none"


# # # =============================
# # # INITIAL LOAD (AUTO RESUME)
# # # =============================
# # if not st.session_state.all_images:
# #     with st.spinner("Loading images from Google Drive..."):
# #         st.session_state.all_images = list_drive_images(FIXED_FOLDER_ID)
# #         st.session_state.labels = load_labels()

# #         labeled_names = {
# #             name
# #             for name, v in st.session_state.labels.items()
# #             if v["description"] != "None"
# #         }

# #         for i, img in enumerate(st.session_state.all_images):
# #             if img["name"] not in labeled_names:
# #                 st.session_state.index = i
# #                 break


# # # =============================
# # # UI
# # # =============================
# # st.title("📂 Vehicle Damage Labeler (ICS)")
# # tab1, tab2 = st.tabs(["🏷️ Labeling", "📊 Live Preview"])


# # # =============================
# # # TAB 1 — LABELING
# # # =============================
# # with tab1:
# #     filter_mode = st.radio(
# #         "🔍 Show Images",
# #         ["All Images", "Only Unlabeled"],
# #         horizontal=True,
# #     )

# #     labeled_names = get_labeled_image_names()

# #     if filter_mode == "Only Unlabeled":
# #         st.session_state.images = [
# #             img
# #             for img in st.session_state.all_images
# #             if img["name"] not in labeled_names
# #         ]
# #         st.session_state.index = 0
# #     else:
# #         st.session_state.images = st.session_state.all_images

# #     if not st.session_state.images:
# #         st.success("🎉 All images are labeled!")
# #         st.stop()

# #     if st.session_state.index >= len(st.session_state.images):
# #         st.session_state.index = 0

# #     load_current_image()

# #     col1, col2 = st.columns([2, 1])

# #     with col1:
# #         st.image(
# #             st.session_state.current_path,
# #             use_container_width=True,
# #         )
# #         st.caption(st.session_state.current_name)
# #         st.progress(
# #             (st.session_state.index + 1)
# #             / len(st.session_state.images)
# #         )
# #         st.caption(
# #             f"{st.session_state.index + 1} of {len(st.session_state.images)}"
# #         )

# #     with col2:
# #         existing = st.session_state.labels.get(
# #             st.session_state.current_name, {}
# #         )
# #         desc = existing.get("description", "")

# #         st.subheader("🚗 Vehicle Side")
# #         side = st.radio(
# #             "Side",
# #             ["front", "back", "left", "right", "none"],
# #             index=[
# #                 "front",
# #                 "back",
# #                 "left",
# #                 "right",
# #                 "none",
# #             ].index(st.session_state.current_side),
# #         )

# #         label = st.text_area(
# #             "Damage Description",
# #             value=desc,
# #             height=120,
# #         )

# #         b1, b2, b3 = st.columns(3)

# #         with b1:
# #             if st.button("⬅️ Prev", disabled=st.session_state.index == 0):
# #                 st.session_state.index -= 1
# #                 st.rerun()

# #         with b2:
# #             if st.button("💾 Save & Next", type="primary"):
# #                 if label.strip():
# #                     save_label(
# #                         st.session_state.current_name,
# #                         label.strip(),
# #                         side,
# #                     )
# #                     st.session_state.index = min(
# #                         st.session_state.index + 1,
# #                         len(st.session_state.images) - 1,
# #                     )
# #                     st.rerun()
# #                 else:
# #                     st.warning("Description required")

# #         with b3:
# #             if st.button(
# #                 "➡️ Next",
# #                 disabled=st.session_state.index
# #                 == len(st.session_state.images) - 1,
# #             ):
# #                 st.session_state.index += 1
# #                 st.rerun()


# # # =============================
# # # TAB 2 — LIVE DATA
# # # =============================
# # with tab2:
# #     st.header("📊 Live Supabase Data")

# #     data = (
# #         supabase.table("image_labels")
# #         .select("*")
# #         .execute()
# #         .data
# #     )
# #     df = pd.DataFrame(data)

# #     if not df.empty:
# #         c1, c2, c3 = st.columns(3)

# #         with c1:
# #             st.metric("Total Labeled", len(df))

# #         with c2:
# #             st.metric(
# #                 "Total Images",
# #                 len(st.session_state.all_images),
# #             )

# #         with c3:
# #             st.metric(
# #                 "Progress",
# #                 f"{round((len(df) / len(st.session_state.all_images)) * 100, 2)}%",
# #             )

# #         st.bar_chart(df["side"].value_counts())
# #         st.dataframe(df, use_container_width=True)
# #     else:
# #         st.info("No labels yet")

# #     st.caption("⚡ Streamlit + Supabase + Google Drive")





# import os
# import io
# import json
# from typing import List, Dict

# import streamlit as st
# import pandas as pd
# from PIL import Image

# from supabase import create_client
# from google.oauth2 import service_account
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaIoBaseDownload


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
#     st.error("Missing Supabase credentials")
#     st.stop()

# supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# # =============================
# # SESSION STATE
# # =============================
# st.session_state.setdefault("all_images", [])
# st.session_state.setdefault("images", [])
# st.session_state.setdefault("index", 0)
# st.session_state.setdefault("labels", {})
# st.session_state.setdefault("current_path", "")
# st.session_state.setdefault("current_name", "")
# st.session_state.setdefault("current_side", "none")

# st.session_state.setdefault("last_filter_mode", "All Images")


# # =============================
# # GOOGLE DRIVE
# # =============================
# @st.cache_resource
# def drive_service():
#     # import certifi
#     # import httplib2
#     # from google_auth_httplib2 import AuthorizedHttp
    
#     creds = service_account.Credentials.from_service_account_info(
#         json.loads(SERVICE_ACCOUNT_JSON),
#         scopes=SCOPES,
#     )
  
#     return build("drive", "v3", credentials=creds, )


# drive = drive_service()


# def list_drive_images(folder_id: str) -> List[Dict]:
#     images = []
#     page_token = None

#     while True:
#         res = (
#             drive.files()
#             .list(
#                 q=f"'{folder_id}' in parents and trashed=false",
#                 fields="nextPageToken, files(id,name,mimeType)",
#                 pageToken=page_token,
#                 pageSize=1000,
#             )
#             .execute()
#         )

#         images.extend(
#             [
#                 f
#                 for f in res.get("files", [])
#                 if f["mimeType"].startswith("image/")
#             ]
#         )

#         page_token = res.get("nextPageToken")
#         if not page_token:
#             break

#     # Sort images by name in ascending order
#     images.sort(key=lambda x: x["name"])
    
#     return images


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
#     return {
#         r["image_name"]: {
#             "description": r["description"],
#             "side": r.get("side", "none"),
#         }
#         for r in res.data
#     }


# def get_labeled_image_names():
#     res = (
#         supabase.table("image_labels")
#         .select("image_name, description")
#         .execute()
#     )
#     return {
#         r["image_name"]
#         for r in res.data
#         if r["description"] and r["description"] != "None"
#     }


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
#     if not st.session_state.images:
#         return

#     img = st.session_state.images[st.session_state.index]
#     data = download_image(img["id"])
#     image = Image.open(data)

#     path = os.path.join(TEMP_FOLDER, img["name"])
#     image.save(path)

#     st.session_state.current_path = path
#     st.session_state.current_name = img["name"]

#     label = st.session_state.labels.get(img["name"])
#     st.session_state.current_side = label["side"] if label else "none"


# # =============================
# # INITIAL LOAD (AUTO RESUME)
# # =============================
# if not st.session_state.all_images:
#     with st.spinner("Loading images from Google Drive..."):
#         st.session_state.all_images = list_drive_images(FIXED_FOLDER_ID)
#         st.session_state.labels = load_labels()

#         labeled_names = {
#             name
#             for name, v in st.session_state.labels.items()
#             if v["description"] != "None"
#         }

#         for i, img in enumerate(st.session_state.all_images):
#             if img["name"] not in labeled_names:
#                 st.session_state.index = i
#                 break


# # =============================
# # UI
# # =============================
# st.title("📂 Vehicle Damage Labeler (ICS)")
# tab1, tab2 = st.tabs(["🏷️ Labeling", "📊 Live Preview"])


# # =============================
# # TAB 1 — LABELING
# # =============================
# with tab1:
#     filter_mode = st.radio(
#         "🔍 Show Images",
#         ["All Images", "Only Unlabeled"],
#         horizontal=True,
#     )

#     labeled_names = get_labeled_image_names()

#     if filter_mode != st.session_state.last_filter_mode:
#        if filter_mode =="Only Unlabeled":
#         st.session_state.images = [
#             img
#             for img in st.session_state.all_images
#             if img["name"] not in labeled_names
#         ]
#         st.session_state.index = 0
#     else:
#         st.session_state.images = st.session_state.all_images
#     st.session_state.images = st.session_state.all_images
#     st.session_state.last_filter_mode = filter_mode
    
#     if not st.session_state.images:
#         st.success("🎉 All images are labeled!")
#         st.stop()

#     if st.session_state.index >= len(st.session_state.images):
#         st.session_state.index = 0

#     load_current_image()

#     col1, col2 = st.columns([2, 1])

#     with col1:
#         st.image(
#             st.session_state.current_path,
#             use_container_width=True,
#         )
#         st.caption(st.session_state.current_name)
#         st.progress(
#             (st.session_state.index + 1)
#             / len(st.session_state.images)
#         )
#         st.caption(
#             f"{st.session_state.index + 1} of {len(st.session_state.images)}"
#         )

#     with col2:
#         existing = st.session_state.labels.get(
#             st.session_state.current_name, {}
#         )
#         desc = existing.get("description", "")

#         # Tips Section
#         with st.expander("💡 Labeling Tips", expanded=True):
#             st.markdown("""
#             **Include these key details in your description:**
            
#             1. **Impact Location** 🎯  
#                Where the damage occurred (e.g., front left, rear right, center)
            
#             2. **Damaged Part** 🔧  
#                Which component is affected (e.g., handlebar, crash guard, fender, mirror, panel)
            
#             3. **Severity Indicators** ⚠️  
#                Evidence of damage (e.g., bent, scratched, cracked, dented, broken, shattered)
            
#             **Example:** *"Front left handlebar bent, crash guard scratched on right side"*
#             """)

#         st.subheader("🚗 Vehicle Side")
#         side = st.radio(
#             "Side",
#             ["front", "back", "left", "right", "none"],
#             index=[
#                 "front",
#                 "back",
#                 "left",
#                 "right",
#                 "none",
#             ].index(st.session_state.current_side),
#         )

#         label = st.text_area(
#             "Damage Description",
#             value=desc,
#             height=120,
#             placeholder="Describe the damage including location, part, and severity...",
#         )

#         b1, b2, b3 = st.columns(3)

#         with b1:
#             if st.button("⬅️ Prev", disabled=st.session_state.index == 0):
#                 st.session_state.index -= 1
#                 st.rerun()

#         with b2:
#             if st.button("💾 Save & Next", type="primary"):
#                 if label.strip():
#                     save_label(
#                         st.session_state.current_name,
#                         label.strip(),
#                         side,
#                     )
#                     st.session_state.index += 1
#                     if st.session_state.index >= len(st.session_state.images):
#                         st.session_state.index = len(st.session_state.images) -1
#                     st.rerun()
#                 else:
#                     st.warning("Description required")

#         with b3:
#             if st.button(
#                 "➡️ Next",
#                 disabled=st.session_state.index
#                 == len(st.session_state.images) - 1,
#             ):
#                 st.session_state.index += 1
#                 st.rerun()


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
#         c1, c2, c3 = st.columns(3)

#         with c1:
#             st.metric("Total Labeled", len(df))

#         with c2:
#             st.metric(
#                 "Total Images",
#                 len(st.session_state.all_images),
#             )

#         with c3:
#             st.metric(
#                 "Progress",
#                 f"{round((len(df) / len(st.session_state.all_images)) * 100, 2)}%",
#             )

#         st.bar_chart(df["side"].value_counts())
#         st.dataframe(df, use_container_width=True)
#     else:
#         st.info("No labels yet")

#     st.caption("⚡ Streamlit + Supabase + Google Drive")
"""
Google Drive Image Labeler for Vehicle Damage
A Streamlit application for labeling vehicle damage images stored in Google Drive
"""

import os
import io
import json
from typing import List, Dict

import streamlit as st
import pandas as pd
from PIL import Image

from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# =============================
# PAGE CONFIGURATION
# =============================
st.set_page_config(
    page_title="Google Drive Image Labeler",
    page_icon="📂",
    layout="wide",
)


# =============================
# ENVIRONMENT CONFIGURATION
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
# SUPABASE CONFIGURATION
# =============================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing Supabase credentials")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# =============================
# SESSION STATE INITIALIZATION
# =============================
st.session_state.setdefault("all_images", [])
st.session_state.setdefault("images", [])
st.session_state.setdefault("index", 0)
st.session_state.setdefault("labels", {})
st.session_state.setdefault("current_path", "")
st.session_state.setdefault("current_name", "")
st.session_state.setdefault("current_side", "none")
st.session_state.setdefault("last_filter_mode", "All Images")


# =============================
# GOOGLE DRIVE SERVICE
# =============================
@st.cache_resource
def drive_service():
    """Initialize and cache Google Drive service"""
    creds = service_account.Credentials.from_service_account_info(
        json.loads(SERVICE_ACCOUNT_JSON),
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds)


drive = drive_service()


def list_drive_images(folder_id: str) -> List[Dict]:
    """
    List all image files from a Google Drive folder
    
    Args:
        folder_id: Google Drive folder ID
        
    Returns:
        List of image file metadata sorted by name
    """
    images = []
    page_token = None

    while True:
        res = (
            drive.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id,name,mimeType)",
                pageToken=page_token,
                pageSize=1000,
            )
            .execute()
        )

        images.extend(
            [
                f
                for f in res.get("files", [])
                if f["mimeType"].startswith("image/")
            ]
        )

        page_token = res.get("nextPageToken")
        if not page_token:
            break

    # Sort images by name in ascending order
    images.sort(key=lambda x: x["name"])
    
    return images


def download_image(file_id: str) -> io.BytesIO:
    """
    Download an image file from Google Drive
    
    Args:
        file_id: Google Drive file ID
        
    Returns:
        BytesIO object containing image data
    """
    request = drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.seek(0)
    return fh


# =============================
# SUPABASE DATABASE HELPERS
# =============================
def load_labels() -> Dict:
    """
    Load all labels from Supabase
    
    Returns:
        Dictionary mapping image names to their labels
    """
    res = supabase.table("image_labels").select("*").execute()
    return {
        r["image_name"]: {
            "description": r["description"],
            "side": r.get("side", "none"),
        }
        for r in res.data
    }


def get_labeled_image_names() -> set:
    """
    Get set of image names that have been labeled
    
    Returns:
        Set of labeled image names
    """
    res = (
        supabase.table("image_labels")
        .select("image_name, description")
        .execute()
    )
    return {
        r["image_name"]
        for r in res.data
        if r["description"] and r["description"] != "None"
    }


def save_label(name: str, desc: str, side: str):
    """
    Save or update a label in Supabase
    
    Args:
        name: Image filename
        desc: Damage description
        side: Vehicle side (front/back/left/right/none)
    """
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
# IMAGE LOADING
# =============================
def load_current_image():
    """Load the current image from Drive and save to temp folder"""
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
# INITIAL DATA LOADING
# =============================
if not st.session_state.all_images:
    with st.spinner("Loading images from Google Drive..."):
        st.session_state.all_images = list_drive_images(FIXED_FOLDER_ID)
        st.session_state.labels = load_labels()

        # Auto-resume from first unlabeled image
        labeled_names = {
            name
            for name, v in st.session_state.labels.items()
            if v["description"] != "None"
        }

        for i, img in enumerate(st.session_state.all_images):
            if img["name"] not in labeled_names:
                st.session_state.index = i
                break


# =============================
# USER INTERFACE
# =============================
st.title("📂 Vehicle Damage Labeler (ICS)")
tab1, tab2 = st.tabs(["🏷️ Labeling", "📊 Live Preview"])


# =============================
# TAB 1: LABELING INTERFACE
# =============================
with tab1:
    # Filter controls
    filter_mode = st.radio(
        "🔍 Show Images",
        ["All Images", "Only Unlabeled"],
        horizontal=True,
    )

    labeled_names = get_labeled_image_names()

    # Update filtered images when filter mode changes
    if filter_mode != st.session_state.last_filter_mode:
        if filter_mode == "Only Unlabeled":
            st.session_state.images = [
                img
                for img in st.session_state.all_images
                if img["name"] not in labeled_names
            ]
            st.session_state.index = 0
        else:
            st.session_state.images = st.session_state.all_images
        
        st.session_state.last_filter_mode = filter_mode
    
    # Ensure images list is set correctly
    if filter_mode == "All Images":
        st.session_state.images = st.session_state.all_images
    
    # Check if all images are labeled
    if not st.session_state.images:
        st.success("🎉 All images are labeled!")
        st.stop()

    # Ensure index is within bounds
    if st.session_state.index >= len(st.session_state.images):
        st.session_state.index = 0

    # Load current image
    load_current_image()

    # Layout: Image on left, controls on right
    col1, col2 = st.columns([2, 1])

    with col1:
        # Display image
        st.image(
            st.session_state.current_path,
            use_container_width=True,
        )
        st.caption(st.session_state.current_name)
        
        # Progress indicator
        st.progress(
            (st.session_state.index + 1) / len(st.session_state.images)
        )
        st.caption(
            f"{st.session_state.index + 1} of {len(st.session_state.images)}"
        )

    with col2:
        # Get existing label data
        existing = st.session_state.labels.get(
            st.session_state.current_name, {}
        )
        desc = existing.get("description", "")

        # Labeling tips
        with st.expander("💡 Labeling Tips", expanded=True):
            st.markdown("""
            **Include these key details in your description:**
            
            1. **Impact Location** 🎯  
               Where the damage occurred (e.g., front left, rear right, center)
            
            2. **Damaged Part** 🔧  
               Which component is affected (e.g., handlebar, crash guard, fender, mirror, panel)
            
            3. **Severity Indicators** ⚠️  
               Evidence of damage (e.g., bent, scratched, cracked, dented, broken, shattered)
            
            **Example:** *"Front left handlebar bent, crash guard scratched on right side"*
            """)

        st.subheader("🚗 Vehicle Damage")

        # Labeling form
        with st.form(key="damage_form", clear_on_submit=False):
            side = st.radio(
                "Vehicle Side",
                ["front", "back", "left", "right", "none"],
                index=[
                    "front", "back", "left", "right", "none",
                ].index(st.session_state.current_side),
            )

            label = st.text_area(
                "Damage Description",
                value=desc,
                height=120,
                placeholder="Describe the damage including location, part, and severity...",
            )

            submitted = st.form_submit_button("💾 Save & Next")

            if submitted:
                if not label.strip():
                    st.warning("Description required")
                else:
                    save_label(
                        st.session_state.current_name,
                        label.strip(),
                        side,
                    )

                    st.session_state.index += 1
                    if st.session_state.index >= len(st.session_state.images):
                        st.session_state.index = len(st.session_state.images) - 1

                    st.rerun()


# =============================
# TAB 2: DATA PREVIEW
# =============================
with tab2:
    st.header("📊 Live Supabase Data")

    # Fetch all labeled data
    data = (
        supabase.table("image_labels")
        .select("*")
        .execute()
        .data
    )
    df = pd.DataFrame(data)

    if not df.empty:
        # Display metrics
        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric("Total Labeled", len(df))

        with c2:
            st.metric(
                "Total Images",
                len(st.session_state.all_images),
            )

        with c3:
            progress_pct = round(
                (len(df) / len(st.session_state.all_images)) * 100, 2
            )
            st.metric("Progress", f"{progress_pct}%")

        # Visualizations
        st.bar_chart(df["side"].value_counts())
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No labels yet")

    st.caption("⚡ Streamlit + Supabase + Google Drive")
