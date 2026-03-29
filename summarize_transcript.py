import re
import os
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

# ===== CONFIG =====
AZURE_OPENAI_ENDPOINT   = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY    = os.environ.get("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")
VTT_DIR        = "C:\\Users\\dungdon.pon\\Documents\\graph-api\\meeting"           # folder ที่เก็บไฟล์ .vtt
OUTPUT_DIR     = "C:\\Users\\dungdon.pon\\Documents\\graph-api"             # folder ที่จะ save ไฟล์ .txt
# ==================


def parse_vtt_string(content: str) -> str:
    """แปลง VTT content (string) เป็น plain text โดยตัด timestamp และ tag ออก"""
    lines = []
    for line in content.splitlines():
        if line.strip() in ("", "WEBVTT"):
            continue
        if re.match(r"^\d+$", line.strip()):
            continue
        if re.match(r"[\d:.]+ --> [\d:.]+", line):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def parse_vtt(vtt_path: str) -> str:
    """แปลง .vtt file เป็น plain text"""
    with open(vtt_path, encoding="utf-8") as f:
        content = f.read()
    return parse_vtt_string(content)


def summarize_with_azure_openai(transcript_text: str, meeting_name: str,
                                 endpoint: str = None, api_key: str = None,
                                 api_version: str = None, deployment: str = None) -> str:
    client = AzureOpenAI(
        azure_endpoint=endpoint or AZURE_OPENAI_ENDPOINT,
        api_key=api_key or AZURE_OPENAI_API_KEY,
        api_version=api_version or AZURE_OPENAI_API_VERSION,
    )

    prompt = f"""คุณคือผู้ช่วยสรุปผลการประชุม กรุณาสรุปจาก transcript ด้านล่างเป็นภาษาไทย โดยแบ่งเป็นหัวข้อดังนี้:

1. **ชื่อการประชุม**: {meeting_name}
2. **ประเด็นหลักที่หารือ**: สรุปเป็นข้อ ๆ
3. **มติ / ข้อสรุป**: สิ่งที่ตกลงกันได้
4. **Action Items**: งานที่ต้องทำต่อ (ระบุผู้รับผิดชอบถ้ามี)

--- Transcript ---
{transcript_text}
"""

    response = client.chat.completions.create(
        model=deployment or AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "คุณคือผู้ช่วย AI สำหรับสรุปผลการประชุม"},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


def process_vtt_file(vtt_path: str):
    meeting_name = os.path.splitext(os.path.basename(vtt_path))[0]
    print(f"Processing: {meeting_name}")

    transcript = parse_vtt(vtt_path)
    if not transcript.strip():
        print("  ไม่พบเนื้อหาใน transcript")
        return

    print(f"  Transcript length: {len(transcript)} chars — sending to Azure OpenAI...")
    summary = summarize_with_azure_openai(transcript, meeting_name)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{meeting_name}_summary.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(summary)

    print(f"  Saved -> {out_path}\n")


def main():
    # ถ้ามีไฟล์ .vtt ใน folder VTT_DIR ให้ process ทั้งหมด
    if os.path.isdir(VTT_DIR):
        vtt_files = [
            os.path.join(VTT_DIR, f)
            for f in os.listdir(VTT_DIR)
            if f.lower().endswith(".vtt")
        ]
    else:
        # ถ้าไม่มี folder ให้หาไฟล์ .vtt ใน directory ปัจจุบัน
        vtt_files = [f for f in os.listdir(".") if f.lower().endswith(".vtt")]

    if not vtt_files:
        print(f"ไม่พบไฟล์ .vtt ใน '{VTT_DIR}' หรือ directory ปัจจุบัน")
        return

    print(f"Found {len(vtt_files)} .vtt file(s)\n")
    for vtt_path in vtt_files:
        process_vtt_file(vtt_path)

    print("Done!")


if __name__ == "__main__":
    main()
