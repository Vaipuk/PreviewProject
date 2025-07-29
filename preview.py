import io
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from dateutil import parser  # pip install python-dateutil

# ── 1) Service‑Account auth (no user login) ─────────────────────────────────
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

@st.cache_resource(show_spinner=False)
def authenticate_drive():
    svc_info = st.secrets["gcp_service_account"]
    creds    = service_account.Credentials.from_service_account_info(
                  svc_info,
                  scopes=SCOPES
               )
    return build('drive', 'v3', credentials=creds)

drive_service = authenticate_drive()

# ── 2) Locate “Outputs” folder (most recently modified if duplicates) ────────
@st.cache_data(show_spinner=False)
def get_outputs_folder_id():
    resp = drive_service.files().list(
        q=(
            "name = 'Outputs' "
            "and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        ),
        fields="files(id,name,modifiedTime)"
    ).execute()
    outs = resp.get('files', [])
    if not outs:
        st.error("Could not find a folder named 'Outputs'.")
        st.stop()
    latest = max(outs, key=lambda f: parser.isoparse(f['modifiedTime']))
    return latest['id']

outputs_folder_id = get_outputs_folder_id()

# ── 3) Download helpers ───────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, max_entries=100)
def download_video(file_id: str) -> bytes:
    buf = io.BytesIO()
    req = drive_service.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()

@st.cache_data(show_spinner=False, max_entries=100)
def download_text(file_id: str) -> str:
    buf = io.BytesIO()
    req = drive_service.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    text = buf.getvalue().decode('utf-8', errors='ignore')
    # collapse into one line
    return ' '.join(text.split())

# ── 4) Category ↔ folder mapping & models ─────────────────────────────────────
category_folders = {
    'Causal Reasoning':            list(range(10001, 10006)),
    'Object Interaction':          list(range(10006, 10011)),
    'Human Actions / Gestures':    list(range(10011, 10016)),
    'Animal Behavior':             list(range(10016, 10021)),
    'Scene Changes / Environment': list(range(10021, 10026)),
    'Tool/Instrument Use':         list(range(10026, 10031)),
    'Emotive/Facial Expressions':  list(range(10031, 10036)),
    'Abstract / Conceptual':       list(range(10036, 10041)),
    'Macro / Micro':               list(range(10041, 10046)),
    'Complex Multi-Agent':         list(range(10046, 10051)),
}

models = [
    'Luma Labs Ray-2',
    'Runway Gen-4',
    'Kling AI',
    'Google Veo 3',
    'ByteDance Seedance'
]
normalized_models = {m.lower(): m for m in models}

# ── 5) Sidebar filters + Search button ───────────────────────────────────────
st.sidebar.title("Filters")
sel_cats       = st.sidebar.multiselect(
    "Choose categories",
    options=list(category_folders.keys()),
    default=list(category_folders.keys())
)
sel_models     = st.sidebar.multiselect(
    "Choose model(s)",
    options=models,
    default=models
)
search_clicked = st.sidebar.button(" Search ")

if not search_clicked:
    st.sidebar.info("Select filters, then click **Search** to load videos.")
    st.stop()

if not sel_cats or not sel_models:
    st.sidebar.error("You must select at least one category and one model.")
    st.stop()

st.write(f"**Showing:** Categories = {', '.join(sel_cats)} • Models = {', '.join(sel_models)}")

# ── 6) Fetch & render videos + prompt text ────────────────────────────────────
found_any = False

for folder_no in (n for c in sel_cats for n in category_folders[c]):
    # find all subfolders named "100XX"
    qf = (
        f"'{outputs_folder_id}' in parents "
        f"and name = '{folder_no}' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    resp = drive_service.files().list(
        q=qf,
        fields="files(id,name,modifiedTime)"
    ).execute()
    matches = resp.get('files', [])
    if not matches:
        continue

    # pick latest if duplicates
    latest = max(matches, key=lambda f: parser.isoparse(f['modifiedTime']))
    folder_id = latest['id']

    # list all children
    resp2 = drive_service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id,name)"
    ).execute()
    all_files = resp2.get('files', [])

    # pull the .txt prompt
    txt_name = f"{folder_no}.txt"
    txt_id   = next((f['id'] for f in all_files if f['name']==txt_name), None)
    prompt   = download_text(txt_id) if txt_id else None

    # collect matching videos
    vids = []
    prefix = f"{folder_no}_"
    for f in all_files:
        name = f['name']
        if not name.lower().endswith('.mp4'):
            continue
        raw = name[:-4]
        suffix = raw.split('_',1)[1] if '_' in raw else raw.lstrip('0123456789_')
        norm = suffix.lower().strip()
        if norm in normalized_models and normalized_models[norm] in sel_models:
            vids.append({'id':f['id'],'title':name,'model':normalized_models[norm]})

    # render
    if vids:
        found_any = True
        st.subheader(f"Prompt {folder_no}")
        for v in vids:
            video_bytes = download_video(v['id'])
            st.markdown(f"**{v['model']}** — `{v['title']}`")
            st.video(video_bytes)
            if prompt:
                st.markdown(f"Prompt : {prompt}")

if not found_any:
    st.warning("No videos found. Check your folder numbers, names, and model filters.")
