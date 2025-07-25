import streamlit as st
import pandas as pd
import os
from datetime import datetime
from io import BytesIO

# --- Google API Imports ---
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- Google Credentials Setup ---
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
CREDS_FILE = "credentials.json"  # Local file path
SPREADSHEET_ID = "1UGrGEtWy5coI7nduIY8J8Vjh9S0Ahej7ekDG_4nl-SQ"
DRIVE_FOLDER_ID = "1l6N7Gfd8T1V8t3hR2OuLn5CDtBuzjsKu"

credentials = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPE)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
drive_service = build("drive", "v3", credentials=credentials)

# --- Input File ---
input_file = "IDF_ACCT_ID.csv"
df = pd.read_csv(input_file)

if st.session_state.get("form_submitted"):
    st.success("✅ Your response was submitted successfully.")
    if st.button("🔄 Fill another form"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    st.stop()

st.title("Supervisor Field Survey – IDF Cases")
st.caption("Please fill this form after on-site verification of IDF accounts.")

acct_id_input = st.text_input("**ENTER ACCT_ID**", max_chars=10)
if acct_id_input and (not acct_id_input.isdigit() or not (1 <= len(acct_id_input) <= 10)):
    st.error("❌ ACCT_ID should be numeric and 1 to 10 digits only.")
    st.stop()

if acct_id_input:
    match = df[df["ACCT_ID"].astype(str) == acct_id_input.strip()]
    if not match.empty:
        st.success("✅ ACCT_ID matched. Details below:")

        fields = {
            "ZONE": match.iloc[0]["ZONE"],
            "CIRCLE": match.iloc[0]["CIRCLE"],
            "DIVISION": match.iloc[0]["DIVISION"],
            "SUB-DIVISION": match.iloc[0]["SUB-DIVISION"]
        }

        cols = st.columns(len(fields))
        for col, (label, value) in zip(cols, fields.items()):
            col.markdown(f"<b>{label}:</b><br>{value}", unsafe_allow_html=True)

        st.markdown("---")

        remark_options = {
            "OK": ["METER SERIAL NUMBER", "METER IMAGE", "READING", "DEMAND"],
            "DEFECTIVE METER": ["METER SERIAL NUMBER", "METER IMAGE"],
            "LINE DISCONNECTED": ["METER SERIAL NUMBER", "METER IMAGE"],
            "NO METER AT SITE": ["PREMISES IMAGE"],
            "METER MIS MATCH": ["METER SERIAL NUMBER", "METER IMAGE", "METER READING", "DEMAND"],
            "HOUSE LOCK": ["PREMISES IMAGE"],
            "METER CHANGE NOT ADVISE": ["METER SERIAL NUMBER", "METER IMAGE", "METER READING", "DEMAND"],
            "PDC": ["METER IMAGE", "PREMISES IMAGE", "DOCUMENT RELATED TO PDC"]
        }

        required_remark_map = {
            "OK": "BILL REVISION REQUIRED",
            "DEFECTIVE METER": "METER REPLACEMENT REQUIRED",
            "LINE DISCONNECTED": "NEED RECONNECTION AFTER PAYMENT",
            "NO METER AT SITE": "PD/METER INSTALLATION",
            "METER MIS MATCH": "NEED METER NUMBER UPDATION",
            "PDC": "MASTER UPDATION REQUIRED"
        }

        selected_remark = st.selectbox("Select REMARK", [""] + list(remark_options.keys()))

        if selected_remark:
            mobile_no = ""
            if selected_remark != "HOUSE LOCK":
                mobile_no = st.text_input("**ENTER CONSUMER MOBILE NUMBER**", max_chars=10)

            required_remark = required_remark_map.get(selected_remark, "")
            if required_remark:
                st.markdown(f"📝 **Required Remark:** `{required_remark}`")

            st.markdown("#### Enter Required Details:")

            input_data = {
                "MOBILE_NO": mobile_no if selected_remark != "HOUSE LOCK" else "",
                "REQUIRED_REMARK": required_remark,
                "METER_SERIAL_NUMBER": "",
                "READING": "",
                "DEMAND": ""
            }

            captured_images = {}
            missing_fields = []
            uploaded_drive_links = {}

            for field in remark_options[selected_remark]:
                if "IMAGE" in field.upper() or "DOCUMENT" in field.upper():
                    captured_images[field] = st.camera_input(f"Capture {field}")
                else:
                    value = st.text_input(f"{field}")
                    if not value:
                        missing_fields.append(field)
                    input_data[field.replace(" ", "_").upper()] = value

            if selected_remark != "HOUSE LOCK" and (not mobile_no.isdigit() or len(mobile_no) != 10):
                st.warning("📵 Valid mobile number is required.")
                missing_fields.append("MOBILE_NO")

            for field, image in captured_images.items():
                if not image:
                    missing_fields.append(field)

            if missing_fields:
                st.warning(f"⚠ Please fill required fields: {', '.join(missing_fields)}")
            else:
                if st.button("✅ Submit"):
                    # Upload images to Drive
                    for field, image in captured_images.items():
                        filename = f"{acct_id_input}_{field.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                        media = MediaIoBaseUpload(BytesIO(image.getbuffer()), mimetype="image/png")
                        uploaded = drive_service.files().create(
                            body={"name": filename, "parents": [DRIVE_FOLDER_ID]},
                            media_body=media,
                            fields="id"
                        ).execute()
                        file_id = uploaded.get("id")
                        drive_link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
                        uploaded_drive_links[field.replace(" ", "_").upper()] = drive_link

                    row_data = [
                        acct_id_input,
                        selected_remark,
                        fields["ZONE"],
                        fields["CIRCLE"],
                        fields["DIVISION"],
                        fields["SUB-DIVISION"],
                        input_data["MOBILE_NO"],
                        input_data["REQUIRED_REMARK"],
                        input_data.get("METER_SERIAL_NUMBER", ""),
                        input_data.get("READING", ""),
                        input_data.get("DEMAND", ""),
                        uploaded_drive_links.get("METER_IMAGE", ""),
                        uploaded_drive_links.get("PREMISES_IMAGE", ""),
                        uploaded_drive_links.get("DOCUMENT_RELATED_TO_PDC", "")
                    ]

                    sheet.append_row(row_data)
                    st.session_state["form_submitted"] = True
                    st.rerun()
        else:
            st.info("Please select a remark to continue.")
    else:
        st.error("❌ ACCT_ID not found. Please check and try again.")
