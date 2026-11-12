import io
from typing import List, Optional
from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel, Field
import streamlit as st

# 1. 모바일 최적화 페이지 설정 (스마트폰 화면 맞춤)
st.set_page_config(
    page_title="화력발전소 현장 안전 감독 AI", page_icon="⚡", layout="centered"
)

# 모바일 화면에서 글자나 표가 가로로 튀어나가지 않도록 막아주는 반응형 카드 CSS
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 600px;
    }
    .violation-card {
        background-color: #fff5f5;
        border-left: 5px solid #e53e3e;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        word-break: keep-all;
        overflow-wrap: break-word;
    }
    .card-title {
        color: #c53030;
        font-weight: bold;
        font-size: 1.1rem;
        margin-bottom: 8px;
    }
    .card-law {
        background-color: #ffffff;
        padding: 10px;
        border-radius: 5px;
        font-size: 0.9rem;
        color: #2d3748;
        border: 1px solid #feb2b2;
        margin-bottom: 8px;
    }
    .card-action {
        font-size: 0.95rem;
        color: #2b6cb0;
        font-weight: 600;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 🔑 API 키 자동 로드 (스트림릿 비밀 금고 연동)
# 코드에 키를 직접 노출하지 않아 구글의 키 정지(차단)를 완벽히 방지합니다.
# ==========================================
API_KEY = ""
if "GEMINI_API_KEY" in st.secrets:
  API_KEY = st.secrets["GEMINI_API_KEY"]
if not API_KEY:
  API_KEY = st.sidebar.text_input(
      "🔑 Google AI Studio API 키 입력",
      type="password",
      help="여기에 키를 입력하세요",
  )


# ==========================================
# 2. 3단계 필터링 강제 데이터 구조 (Pydantic Schema)
# ==========================================
class ViolationDetail(BaseModel):
  hazard_name: str = Field(
      description="위험요인 명칭 (예: 고소작업 중 안전대 미체결)"
  )
  law_clause: str = Field(
      description="관련 법령 조항 및 본문 핵심 내용 (산업안전보건기준에 관한"
      " 규칙 제OO조 본문 포함 및 KOSHA GUIDE 명시)"
  )
  action_plan: str = Field(
      description="현장대리인/현장소장에게 즉시 요구할 구체적 조치 사항"
  )


class SafetyAnalysisResult(BaseModel):
  # 1단계 필터
  step1_is_work_scene: bool = Field(
      description="1단계: 실제 작업(화기, 고소, 중장비, 중량물, 설비정비 등)이"
      " 진행 중인 사진이면 True, 비작업 사진이면 False"
  )
  step1_description: str = Field(
      description="1단계 판별 사유 (어떤 작업인지 요약, 비작업 사진이면"
      " '해당없음' 사유)"
  )

  # 2단계 필터
  step2_has_violation: Optional[bool] = Field(
      description="2단계: 1단계가 True일 때만 판별. 산업안전보건기준에 관한"
      " 규칙을 명백히 위반한 사항이 있으면 True, 안전수칙을 모두"
      " 준수했으면 False. (1단계가 False면 null)"
  )
  step2_description: Optional[str] = Field(
      description="2단계 검증 요약 (위반 여부 판단 근거)"
  )

  # 3단계 결과 생성
  step3_violations: Optional[List[ViolationDetail]] = Field(
      description="3단계: 1단계와 2단계가 모두 True일 때만 생성. 발견된 명백한"
      " 위반사항 리스트 (없으면 빈 리스트)"
  )


# ==========================================
# 3. 고해상도 이미지 자동 압축 함수 (전송 지연 단축)
# ==========================================
def compress_image(uploaded_file, max_size=1024):
  image = Image.open(uploaded_file)
  if image.mode in ("RGBA", "P"):
    image = image.convert("RGB")
  image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
  buf = io.BytesIO()
  image.save(buf, format="JPEG", quality=80)
  buf.seek(0)
  return Image.open(buf)


# ==========================================
# 4. 앱 화면(UI) 구성
# ==========================================
st.title("⚡ 현장 안전수칙 판독 AI")
st.caption("화력발전소 현장 감독관용 | 법령 근거 및 시정조치 즉시 생성")

tab1, tab2 = st.tabs(["📸 카메라 바로 촬영", "🖼️ 갤러리 사진 업로드"])

with tab1:
  cam_photo = st.camera_input("현장 작업을 촬영하세요")

with tab2:
  gallery_photo = st.file_uploader(
      "스마트폰에서 사진 선택" )

target_file = cam_photo if cam_photo is not None else gallery_photo

if target_file is not None:
  compressed_img = compress_image(target_file)
  st.image(
      compressed_img,
      caption="분석 대상 사진 (전송 최적화 완료)",
      use_container_width=True,
  )

  if st.button("🔍 3단계 안전 법령 정밀 판독", type="primary", use_container_width=True):
    if not API_KEY:
      st.error(
          "⚠️ API 키가 설정되지 않았습니다. Streamlit Cloud의 Secrets 설정이나"
          " 좌측 사이드바에 키를 입력해주세요."
      )
    else:
      with st.spinner("1단계~3단계 순차 필터링 분석 중..."):
        try:
          client = genai.Client(api_key=API_KEY)

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

          # [1단계 결과] 비작업 사진인 경우
          if not result.step1_is_work_scene:
            st.warning("### 🚫 [판정 종료: 해당없음]")
            st.write(f"**사유:** {result.step1_description}")
            st.info(
                "실제 현장 작업이 진행 중인 사진이 아니므로 분석을 즉시"
                " 중단했습니다."
            )

          # [2단계 결과] 작업 사진이지만 위반 사항이 없는 경우
          elif not result.step2_has_violation:
            st.success("### ✅ [판정 종료: 위험요소 없음 / 안전수칙 준수]")
            st.write(f"**작업 내용:** {result.step1_description}")
            st.write(f"**검증 결과:** {result.step2_description}")
            st.info(
                "사진상에서 산업안전보건기준에 관한 규칙을 명백히 위반한 사항이"
                " 발견되지 않았습니다."
            )

          # [3단계 결과] 명백한 안전수칙 위반이 발견된 경우
          else:
            st.error(
                f"### 🚨 안전수칙 위반 적발 (총"
                f" {len(result.step3_violations)}건)"
            )
            st.caption(f"작업 상황: {result.step1_description}")

            for idx, v in enumerate(result.step3_violations, 1):
              st.markdown(
                  f"""
                            <div class="violation-card">
                                <div class="card-title">⚠️ 위반 {idx}. {v.hazard_name}</div>
                                <div class="card-law">
                                    <b>📖 관련 법령 및 기준:</b><br>{v.law_clause}
                                </div>
                                <div class="card-action">
                                    👉 <b>즉시 조치 요청사항:</b><br>{v.action_plan}
                                </div>
                            </div>
                            """,
                  unsafe_allow_html=True,
              )

            st.markdown("#### 📋 현장대리인/소장 전달용 요약 텍스트 (복사해서 사용)")
            summary_text = f"[현장 안전점검 시정조치 요청]\n- 작업내용: {result.step1_description}\n\n"
            for idx, v in enumerate(result.step3_violations, 1):
              summary_text += f"{idx}. 위험요인: {v.hazard_name}\n   - 관련법령: {v.law_clause}\n   - 조치요청: {v.action_plan}\n\n"
            st.code(summary_text, language="text")

        except Exception as e:
          st.error(
              f"❌ 판독 중 오류가 발생했습니다. API 키가 정확한지 확인해주세요."
              f" (오류 상세: {e})"
          )
