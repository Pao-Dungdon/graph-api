import streamlit as st
import pandas as pd

from get_transcripts import (
    get_access_token, get_user_id, get_calendar_events,
    get_meeting_by_join_url, get_transcripts, get_transcript_content,
    TENANT_ID, CLIENT_ID, CLIENT_SECRET, TARGET_USER,
)
from summarize_transcript import parse_vtt_string, summarize_with_azure_openai, AZURE_OPENAI_API_KEY

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI สรุปผลการประชุม",
    page_icon="📋",
    layout="wide",
)

# ─── Password protection ─────────────────────────────────────────────────────
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "AIT3C@ai")

if not st.session_state.get("authenticated"):
    st.title("📋 ระบบ AI สรุปผลการประชุม")
    pwd = st.text_input("กรุณาใส่รหัสผ่าน", type="password")
    if st.button("เข้าสู่ระบบ"):
        if pwd == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("รหัสผ่านไม่ถูกต้อง")
    st.stop()

# ─── ค่า config ที่ซ่อนไว้ (ไม่แสดงใน UI) ───────────────────────────────────
# อ่านจาก st.secrets (Streamlit Cloud) ก่อน แล้ว fallback ไป os.environ
tenant_id        = st.secrets.get("TENANT_ID",        TENANT_ID)
client_id        = st.secrets.get("CLIENT_ID",        CLIENT_ID)
client_secret    = st.secrets.get("CLIENT_SECRET",    CLIENT_SECRET)
azure_openai_key = st.secrets.get("AZURE_OPENAI_API_KEY", AZURE_OPENAI_API_KEY)
azure_endpoint   = st.secrets.get("AZURE_OPENAI_ENDPOINT",   "")
azure_api_ver    = st.secrets.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
azure_deployment = st.secrets.get("AZURE_OPENAI_DEPLOYMENT",  "gpt-5-mini")

# ─── Header ─────────────────────────────────────────────────────────────────
st.title("📋 ระบบ AI สรุปผลการประชุม")
st.caption("จาก Microsoft Teams · ขับเคลื่อนด้วย Azure OpenAI")
st.divider()

# ─── Step 1: ดึงรายการประชุม ────────────────────────────────────────────────
st.subheader("ขั้นที่ 1 — ดึงรายการประชุมจาก Teams")

col1, col2, col3 = st.columns([3, 1, 1], vertical_alignment="bottom")
with col1:
    _default_user = st.secrets.get("TARGET_USER", TARGET_USER)
    target_user = st.text_input(
        "Email ผู้ใช้",
        value=_default_user,
        placeholder="name@company.com",
    )
with col2:
    days_back = st.number_input("ดึงย้อนหลัง (วัน)", min_value=1, max_value=365, value=30)
with col3:
    fetch_btn = st.button("🔗 ดึงรายการประชุม", use_container_width=True)

if fetch_btn:
    try:
        with st.spinner("กำลังเชื่อมต่อและดึงรายการประชุม..."):
            token   = get_access_token(tenant_id, client_id, client_secret)
            user_id = get_user_id(token, target_user)
            events  = get_calendar_events(token, target_user, days_back)

        meetings_with_transcript = []
        progress = st.progress(0, text="กำลังตรวจสอบ transcript...")
        for i, event in enumerate(events):
            join_url = event.get("onlineMeeting", {}).get("joinUrl", "")
            if not join_url:
                continue
            try:
                meeting = get_meeting_by_join_url(token, user_id, join_url)
                if not meeting:
                    continue
                transcripts = get_transcripts(token, user_id, meeting["id"])
                if transcripts:
                    meetings_with_transcript.append({
                        **event,
                        "_meeting_id":    meeting["id"],
                        "_transcript_id": transcripts[0]["id"],
                    })
            except Exception:
                continue
            progress.progress((i + 1) / len(events), text=f"ตรวจสอบแล้ว {i+1}/{len(events)}")
        progress.empty()

        st.session_state.token   = token
        st.session_state.user_id = user_id
        st.session_state.events  = meetings_with_transcript
        st.session_state.pop("summary", None)
    except Exception as e:
        st.error(f"เชื่อมต่อไม่สำเร็จ: {e}")

if "events" in st.session_state:
    events = st.session_state.events
    if not events:
        st.info("ไม่พบการประชุมในช่วงที่เลือก")
    else:
        st.success(f"พบ {len(events)} การประชุมที่มี transcript")
        df = pd.DataFrame([
            {
                "ชื่อการประชุม": e.get("subject", "(ไม่มีชื่อ)"),
                "วันที่เริ่ม":   e.get("start", {}).get("dateTime", "")[:16].replace("T", " "),
            }
            for e in events
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()

        # ─── Step 2: เลือกและสรุป ───────────────────────────────────────────
        st.subheader("ขั้นที่ 2 — สรุปผลการประชุมด้วย AI")

        meeting_labels = [
            f"{e.get('start', {}).get('dateTime', '')[:10]}  |  {e.get('subject', '(ไม่มีชื่อ)')}"
            for e in events
        ]
        selected_idx = st.selectbox(
            "เลือกการประชุม",
            range(len(events)),
            format_func=lambda i: meeting_labels[i],
        )

        summarize_btn = st.button("✨ สรุปผลการประชุมด้วย AI")

        if summarize_btn:
            selected_event = events[selected_idx]
            subject       = selected_event.get("subject", "การประชุม")
            meeting_id    = selected_event["_meeting_id"]
            transcript_id = selected_event["_transcript_id"]
            # ดึง token ใหม่เสมอ เพราะอาจหมดอายุหลังจากดึงรายการประชุม
            user_id       = st.session_state.user_id

            try:
                with st.spinner("กำลังดึง transcript จาก Teams..."):
                    token = get_access_token(tenant_id, client_id, client_secret)
                    vtt_content = get_transcript_content(token, user_id, meeting_id, transcript_id)
                    plain_text  = parse_vtt_string(vtt_content)

                with st.spinner("กำลังสรุปด้วย Azure OpenAI..."):
                    summary = summarize_with_azure_openai(
                        plain_text, subject,
                        endpoint=azure_endpoint,
                        api_key=azure_openai_key,
                        api_version=azure_api_ver,
                        deployment=azure_deployment,
                    )
                    st.session_state.summary      = summary
                    st.session_state.summary_name = subject

            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")

# ─── Step 3: แสดงผล ─────────────────────────────────────────────────────────
if "summary" in st.session_state:
    st.divider()
    st.subheader("ขั้นที่ 3 — ผลสรุปการประชุม")

    st.markdown(st.session_state.summary)

    st.download_button(
        label="⬇️ ดาวน์โหลด .txt",
        data=st.session_state.summary.encode("utf-8"),
        file_name=f"{st.session_state.summary_name}_summary.txt",
        mime="text/plain",
    )
