import google.genai as genai
from google.genai import types
from PIL import Image
import io
import pydantic
import streamlit as st

st.set_page_config(page_title="화력발전소 현장 안전수칙 판독 AI", layout="centered")

# API 키 로드 (스트림릿 Secrets 자동 연동)
API_KEY = ""
if "GEMINI_API_KEY" in st.secrets:
  API_KEY = st.secrets["GEMINI_API_KEY"]

st.title("⚡ 현장 안전수칙 판독 AI")
st.caption("화력발전소 현장 감독관용 | 법령 근거 및 시정조치 즉시 생성")

if not API_KEY:
  st.error(
      "⚠️ API 키가 설정되지 않았습니다. 우측 하단 [Manage app] ➔ Settings"
      " ➔ Secrets에 GEMINI_API_KEY를 설정해주세요."
  )
else:
  client = genai.Client(api_key=API_KEY)

  # 3단계 판독 스키마 정의
  class ViolationDetail(pydantic.BaseModel):
    hazard_name: str
    law_clause: str
    action_plan: str

  class SafetyAnalysisResult(pydantic.BaseModel):
    step1_is_work_scene: bool
    step1_description: str
    step2_has_violation: bool
    step2_description: str
    step3_violations: list[ViolationDetail]

  def compress_image(image_file, max_size_mb=3):
    img = Image.open(image_file)
    if img.mode in ("RGBA", "P"):
      img = img.convert("RGB")
    quality = 95
    while True:
      buffered = io.BytesIO()
      img.save(buffered, format="JPEG", quality=quality)
      size_mb = buffered.tell() / (1024 * 1024)
      if size_mb <= max_size_mb or quality <= 10:
        buffered.seek(0)
        return Image.open(buffered)
      quality -= 5

  tab1, tab2 = st.tabs(["📸 카메라 바로 촬영", "🖼️ 갤러리 사진 업로드"])
  target_file = None
  with tab1:
    cam_photo = st.camera_input("현장 작업 사진 촬영")
    if cam_photo:
      target_file = cam_photo
  with tab2:
    gallery_photo = st.file_uploader("스마트폰에서 사진 선택")
    if gallery_photo:
      target_file = gallery_photo

  if target_file is not None:
    compressed_img = compress_image(target_file)
    st.image(
        compressed_img,
        caption="분석 대상 사진 (전송 최적화 완료)",
        use_container_width=True,
    )

    if st.button(
        "🔍 3단계 안전 법령 정밀 판독", type="primary", use_container_width=True
    ):
      with st.spinner("AI가 1~3단계 순차 필터링 분석 중입니다..."):
        try:
          prompt = """
                        당신은 화력발전소 및 플랜트 현장의 안전을 책임지는 엄격한 안전관리 감독관입니다.
                        제공된 사진을 보고 반드시 아래의 3단계 순차적 필터링 로직을 엄격히 따라 분석하세요. 
                        존재하지 않는 위험요소를 억지로 지어내는 행위를 엄격히 금지합니다.

                        [1단계: 사진 속 작업 상황 판단 필터]
                        - 실제 현장 작업(화기, 고소, 비계, 중장비, 크레인/중량물, 컨베이어/기계 설비 정비, 밀폐공간 등)이 진행 중인지 판별하세요.
                        - 단순 서류, 풍경, 사무실, 음식 등 비작업 사진이면 step1_is_work_scene을 False로 설정하고 즉시 분석을 종료하세요.

                        [2단계: 안전수칙 위반 여부 심층 판단]
                        - 1단계가 작업 사진(True)일 때만 수행합니다.
                        - 사진 속 작업자의 보호구(안전모, 안전대 및 죔줄 체결 등)와 주변 환경(안전난간, 발끝막이판, 화재감시자, 불티비산방지포, 신호수, 협착방지 등)에서 [산업안전보건기준에 관한 규칙]을 '명백히 위반한 사항'이 있는지 검증하세요.
                        - 애매하거나 안전수칙을 잘 준수하고 있다면 억지로 지적하지 말고 step2_has_violation을 False로 설정하세요.

                        [3단계: 안전수칙 위반사항 확정 및 법령/개선대책 생성]
                        - 2단계에서 명백한 위반(True)이 확인된 경우에만 작성합니다.
                        - 각 위반 사항별로 (1) 위험요인 명칭, (2) 정확한 [산업안전보건기준에 관한 규칙] 조항 번호와 본문 핵심 내용(필요시 KOSHA GUIDE 병기), (3) 현장대리인/소장에게 즉시 지시할 조치 사항을 명확하고 간결하게 작성하세요.
                        """

          response = client.models.generate_content(
              model="gemini-3.8-flash",
              contents=[prompt, compressed_img],
              config=types.GenerateContentConfig(
                  response_mime_type="application/json",
                  response_schema=SafetyAnalysisResult,
                  temperature=0.1,
              ),
          )

          result: SafetyAnalysisResult = response.parsed
          st.markdown("---")

          if not result.step1_is_work_scene:
            st.warning("### 🚫 [판정 종료: 해당없음]")
            st.write(f"**사유:** {result.step1_description}")
          elif not result.step2_has_violation:
            st.success("### ✅ [판정 종료: 위험요소 없음 / 안전수칙 준수]")
            st.write(f"**작업 내용:** {result.step1_description}")
            st.write(f"**검증 결과:** {result.step2_description}")
          else:
            st.error(
                f"### 🚨 안전수칙 위반 적발 (총"
                f" {len(result.step3_violations)}건)"
            )
            for idx, v in enumerate(result.step3_violations, 1):
              st.markdown(
                  f"""
                            <div style="padding:15px; border-radius:8px; background-color:#ffebee; border-left:5px solid #c62828; margin-bottom:10px;">
                                <b>⚠️ 위반 {idx}. {v.hazard_name}</b><br>
                                <b>📖 관련 법령 및 기준:</b> {v.law_cluster if 'law_cluster' in v else v.law_clause}<br>
                                <b>👉 즉시 조치 요청사항:</b> {v.action_plan}
                            </div>
                            """,
                  unsafe_allow_html=True,
              )
            st.markdown("#### 📋 현장대리인 전달용 요약 텍스트")
            summary_text = f"[현장 안전점검 시정조치 요청]\n- 작업내용: {result.step1_description}\n\n"
            for idx, v in enumerate(result.step3_violations, 1):
              summary_text += f"{idx}. 위험요인: {v.hazard_name}\n   - 관련법령: {v.law_clause}\n   - 조치요청: {v.action_plan}\n\n"
            st.code(summary_text, language="text")
        except Exception as e:
          st.error(f"❌ 판독 중 오류가 발생했습니다. (오류 상세: {e})")
