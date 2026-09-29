import os
import io
import uuid
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from app.schemas.analyzer_schemas import AnalyzeRequest, AnalyzeResponse
from app.schemas.anonymizer_schemas import (
    AnonymizeRequest, AnonymizeResponse,
    DeanonymizeRequest, DeanonymizeResponse,
    OperatorConfigModel,
)
from app.schemas.image_schemas import (
    ImageRedactRequest, ImageRedactResponse,
    DicomRedactResponse, BoundingBoxItem,
)
from app.schemas.structured_schemas import (
    StructuredAnalyzeRequest, StructuredAnalyzeResponse,
    StructuredAnonymizeRequest, StructuredAnonymizeResponse,
    StructuredDeanonymizeRequest, StructuredDeanonymizeResponse,
)
from app.services.analyzer_service import AnalyzerService
from app.services.anonymizer_service import AnonymizerService
from app.services.image_redactor_service import ImageRedactorService
from app.services.structured_service import StructuredService
from app.services.test_data_service import TestDataService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("presidio_api")

TEMP_CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "temp_redacted"))
os.makedirs(TEMP_CACHE_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Microsoft Presidio 엔터프라이즈 API 서비스를 초기화합니다...")
    # 시작 시 서비스 사전 로드 및 초기화
    AnalyzerService.get_instance()
    AnonymizerService.get_instance()
    ImageRedactorService.get_instance()
    StructuredService.get_instance()
    TestDataService.get_instance()
    logger.info("모든 Presidio 서비스가 성공적으로 초기화되어 서비스 준비가 완료되었습니다.")
    yield
    logger.info("Presidio API 서비스를 종료합니다...")

app = FastAPI(
    title="Microsoft Presidio PII De-identification & Redaction Platform",
    description="""
    ## 차세대 개인정보 비식별화 및 복원 엔터프라이즈 솔루션 (Presidio FastAPI)
    
    ### 제공 핵심 기능:
    1. **Presidio Analyzer**: 한국 주민등록번호(KR_RRN) 및 한국 전화번호(KR_PHONE_NUMBER) 인식기 내장 PII 정밀 탐지.
    2. **Presidio Anonymizer & Deanonymizer**: 삭제(Redact), 대체(Replace), 마스킹(Mask), 해싱(Hash), 암호화(Encrypt) 5대 연산자 및 대칭키 기반 역복원 파이프라인.
    3. **Presidio Image Redactor**: 일반 이미지(PNG/JPG) 및 의료용 DICOM 영상의 개인정보 검은 박스(Blackout) 및 가우시안 흐림(Blur) 시각적 마스킹 처리.
    4. **Presidio Structured**: CSV, DataFrame, RDBMS 테이블 컬럼 단위 PII 자동 판별, 비식별화 및 복원.
    5. **Test Data Hub**: 각 기능별 안전하고 사실적인 검증용 데이터셋 생성 및 제공.
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 웹 리소스 마운트
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health", tags=["Health & Status"])
async def health_check():
    """API 서비스 헬스체크 및 탑재된 모델 상태 조회"""
    analyzer = AnalyzerService.get_instance()
    return {
        "status": "healthy",
        "service": "Presidio PII De-identification API",
        "supported_languages": analyzer.engine.supported_languages,
        "custom_recognizers": ["KrRrnRecognizer", "KrPhoneNumberRecognizer"],
        "operators_supported": ["redact", "replace", "mask", "hash", "encrypt"],
        "image_redaction_supported": ["blackout", "blur"],
        "medical_dicom_supported": True,
        "structured_data_supported": True,
    }


# =====================================================================
# 1. Presidio Analyzer API (한국 주민번호, 전화번호 인식기 추가 등록)
# =====================================================================
@app.post("/api/analyze", response_model=AnalyzeResponse, tags=["1. Analyzer"])
async def analyze_text(request: AnalyzeRequest):
    """
    텍스트 내 PII(개인정보)를 탐지합니다.
    - 한국 주민등록번호(KR_RRN) 인식기: 생년월일/성별 검증 및 유효성 체크섬(Pre-2020) 가중치 계산.
    - 한국 전화번호(KR_PHONE_NUMBER) 인식기: 휴대전화(010), 서울(02), 지역번호(031~064), 전국대표번호(1588/1577 등), 국제번호(+82) 통합 탐지.
    """
    try:
        service = AnalyzerService.get_instance()
        return service.analyze_to_response(
            text=request.text,
            language=request.language,
            entities=request.entities,
            score_threshold=request.score_threshold,
        )
    except Exception as e:
        logger.error(f"Error during text analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# 2. Presidio Anonymizer & Deanonymizer API (5대 연산자 및 복원 파이프라인)
# =====================================================================
@app.post("/api/anonymize", response_model=AnonymizeResponse, tags=["2. Anonymizer & Deanonymizer"])
async def anonymize_text(request: AnonymizeRequest):
    """
    텍스트 내 PII를 5가지 연산자(삭제, 대체, 마스킹, 해싱, 암호화)로 비식별화합니다.
    - 원문 복원이 필요한 경우 대칭키(AES) 기반 'encrypt' 연산자를 사용할 수 있습니다.
    - 응답에 비식별화 결과뿐 아니라 복원에 필요한 `deanonymize_payload` 및 엔티티 상세 데이터를 함께 반환합니다.
    """
    try:
        service = AnonymizerService.get_instance()
        return service.anonymize(
            text=request.text,
            language=request.language,
            operators_map=request.operators,
            default_operator=request.default_operator,
            entities=request.entities,
            score_threshold=request.score_threshold,
        )
    except Exception as e:
        logger.error(f"Error during anonymization: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/deanonymize", response_model=DeanonymizeResponse, tags=["2. Anonymizer & Deanonymizer"])
async def deanonymize_text(request: DeanonymizeRequest):
    """
    암호화(encrypt)된 엔티티가 포함된 텍스트를 대칭키(AES)를 이용하여 원문으로 복원(Deanonymization)합니다.
    - `/api/anonymize` 에서 전달받은 `deanonymize_payload`의 items와 암호화 키를 제공하면 원문이 복원됩니다.
    """
    try:
        service = AnonymizerService.get_instance()
        return service.deanonymize(
            text=request.text,
            items=request.items,
            encryption_key=request.encryption_key,
            operators=request.operators,
        )
    except Exception as e:
        logger.error(f"Error during deanonymization: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# 3. Presidio Image Redactor API (일반 이미지 및 의료용 DICOM 영상 가림 처리)
# =====================================================================
@app.post("/api/image/redact", response_model=ImageRedactResponse, tags=["3. Image Redactor"])
async def redact_image_json(request: ImageRedactRequest):
    """
    Base64 이미지를 전달받아 OCR(Tesseract kor+eng)로 민감정보를 검출하고,
    시각적으로 검은 박스(Blackout) 처리하거나 가우시안 흐림(Blur) 마스킹합니다.
    """
    try:
        service = ImageRedactorService.get_instance()
        redacted_img, bboxes, data_uri = service.redact_image(
            image_input=request.image_base64,
            redaction_type=request.redaction_type,
            fill_color=tuple(request.fill_color) if request.fill_color else (0, 0, 0),
            blur_radius=request.blur_radius,
            language=request.language,
            entities=request.entities,
            score_threshold=request.score_threshold,
        )
        return ImageRedactResponse(
            success=True,
            redaction_type=request.redaction_type,
            total_bboxes=len(bboxes),
            bboxes=bboxes,
            redacted_image_base64=data_uri,
        )
    except Exception as e:
        logger.error(f"Error during image redaction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/image/redact-upload", tags=["3. Image Redactor"])
async def redact_image_upload(
    file: UploadFile = File(..., description="마스킹 처리할 이미지 파일 (PNG, JPG 등)"),
    redaction_type: str = Form("blackout", description="'blackout' 또는 'blur'"),
    blur_radius: int = Form(15, description="블러 반경"),
    language: str = Form("kor+eng", description="OCR 언어"),
):
    """
    파일 업로드 형식(multipart/form-data)으로 일반 이미지를 전송받아 마스킹된 이미지를 파일 스트림으로 반환합니다.
    """
    try:
        service = ImageRedactorService.get_instance()
        file_bytes = await file.read()
        redacted_img, bboxes, data_uri = service.redact_image(
            image_input=file_bytes,
            redaction_type=redaction_type,
            blur_radius=blur_radius,
            language=language,
        )
        out_buf = io.BytesIO()
        redacted_img.save(out_buf, format="PNG")
        out_buf.seek(0)
        return StreamingResponse(
            out_buf,
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename=redacted_{file.filename}.png"},
        )
    except Exception as e:
        logger.error(f"Error during image upload redaction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/image/redact-dicom", response_model=DicomRedactResponse, tags=["3. Image Redactor"])
async def redact_dicom_file(
    file: UploadFile = File(..., description="의료용 DICOM (.dcm) 파일"),
    redaction_type: str = Form("blackout", description="'blackout' 또는 'blur'"),
    blur_radius: int = Form(15, description="블러 반경"),
    redact_metadata: bool = Form(True, description="환자명 등 메타데이터 헤더 태그 가림 처리 여부"),
    fill: str = Form("background", description="가림 색상 채우기 방식 ('background' 또는 'contrast')"),
):
    """
    의료용 DICOM 영상 데이터(.dcm)의 민감정보 가림 처리를 수행합니다.
    - 픽셀 데이터(Pixel Data) 내 인쇄된 환자명, 환자ID, 생년월일 등의 텍스트 영역을 OCR로 검출하여 블랙아웃/블러 처리.
    - DICOM 메타데이터 태그(PatientName, PatientID, PatientBirthDate 등) 비식별화.
    - 처리 전/후 픽셀 슬라이스 미리보기 이미지 및 마스킹된 DICOM 다운로드 링크 제공.
    """
    try:
        service = ImageRedactorService.get_instance()
        file_bytes = await file.read()
        redacted_dicom_bytes, bboxes, redacted_tags, orig_preview_b64, redacted_preview_b64 = (
            service.redact_dicom(
                dicom_bytes=file_bytes,
                redaction_type=redaction_type,
                blur_radius=blur_radius,
                redact_metadata=redact_metadata,
                fill=fill,
            )
        )

        file_id = str(uuid.uuid4())[:8]
        cached_filename = f"redacted_{file_id}_{file.filename}"
        cached_path = os.path.join(TEMP_CACHE_DIR, cached_filename)
        with open(cached_path, "wb") as f:
            f.write(redacted_dicom_bytes)

        download_url = f"/api/image/download-dicom/{cached_filename}"

        return DicomRedactResponse(
            success=True,
            redaction_type=redaction_type,
            patient_name_anonymized="ANONYMIZED^PATIENT" if redact_metadata else None,
            patient_id_anonymized="ANON-ID-001" if redact_metadata else None,
            redacted_tags=redacted_tags,
            pixel_bboxes_count=len(bboxes),
            pixel_bboxes=bboxes,
            preview_original_base64=orig_preview_b64,
            preview_redacted_base64=redacted_preview_b64,
            download_url=download_url,
        )
    except Exception as e:
        logger.error(f"Error during DICOM redaction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/image/download-dicom/{filename}", tags=["3. Image Redactor"])
async def download_redacted_dicom(filename: str):
    """마스킹 처리된 DICOM (.dcm) 파일 다운로드"""
    file_path = os.path.join(TEMP_CACHE_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="application/dicom", filename=filename)


# =====================================================================
# 4. Presidio Structured API (정형/반정형 테이블 컬럼 단위 탐지 및 익명화)
# =====================================================================
@app.post("/api/structured/analyze", response_model=StructuredAnalyzeResponse, tags=["4. Structured Data"])
async def analyze_structured_data(request: StructuredAnalyzeRequest):
    """
    정형/반정형 테이블 레코드(JSON)의 컬럼별 PII 엔티티 및 신뢰도를 자동 분석하고 권장 연산자를 제안합니다.
    """
    try:
        service = StructuredService.get_instance()
        return service.analyze_table(
            data=request.data,
            language=request.language,
            sample_size=request.sample_size,
        )
    except Exception as e:
        logger.error(f"Error during structured analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/structured/anonymize", response_model=StructuredAnonymizeResponse, tags=["4. Structured Data"])
async def anonymize_structured_data(request: StructuredAnonymizeRequest):
    """
    테이블 데이터의 컬럼별로 지정된 연산자(삭제, 대체, 마스킹, 해싱, 대칭키 암호화)를 적용하여 비식별화합니다.
    암호화가 적용된 컬럼의 경우 복원에 필요한 키 및 메타데이터를 함께 응답합니다.
    """
    try:
        service = StructuredService.get_instance()
        return service.anonymize_table(
            data=request.data,
            column_operators=request.column_operators,
            language=request.language,
        )
    except Exception as e:
        logger.error(f"Error during structured anonymization: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/structured/deanonymize", response_model=StructuredDeanonymizeResponse, tags=["4. Structured Data"])
async def deanonymize_structured_data(request: StructuredDeanonymizeRequest):
    """
    암호화(encrypt)된 테이블 컬럼을 대칭키를 사용하여 원문 테이블 데이터로 복원합니다.
    """
    try:
        service = StructuredService.get_instance()
        return service.deanonymize_table(
            anonymized_data=request.anonymized_data,
            column_keys=request.column_keys,
        )
    except Exception as e:
        logger.error(f"Error during structured deanonymization: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/structured/anonymize-csv", tags=["4. Structured Data"])
async def anonymize_csv_file(
    file: UploadFile = File(..., description="비식별화할 CSV 파일"),
    operators_json: str = Form(
        ...,
        description="컬럼별 연산자 설정 JSON 문자열 (예: {\"주민등록번호\": {\"operator\": \"mask\", \"params\": {\"chars_to_mask\": 7, \"from_end\": true}}})",
    ),
):
    """CSV 파일을 직접 업로드받아 비식별화된 CSV 파일 스트림으로 반환합니다."""
    try:
        import json
        service = StructuredService.get_instance()
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
        data_records = df.to_dict(orient="records")

        ops_dict = json.loads(operators_json)
        column_ops = {
            col: OperatorConfigModel(**conf) for col, conf in ops_dict.items()
        }

        resp = service.anonymize_table(data=data_records, column_operators=column_ops)
        csv_bytes = resp.csv_string.encode("utf-8-sig")

        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=anonymized_{file.filename}"},
        )
    except Exception as e:
        logger.error(f"Error during CSV anonymization: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# 5. Test Data Hub API (테스트 데이터 생성 및 제공)
# =====================================================================
@app.get("/api/test-data", tags=["5. Test Data Hub"])
async def get_test_data_catalog():
    """모든 기능별 사전 생성된 테스트 데이터 카탈로그 목록 조회"""
    service = TestDataService.get_instance()
    return {
        "text_scenarios": list(service.sample_texts.keys()),
        "structured_data": {"columns": list(service.sample_structured["records"][0].keys()), "total_rows": len(service.sample_structured["records"])},
        "image_sample_available": True,
        "dicom_sample_available": True,
    }


@app.get("/api/test-data/text/{scenario_key}", tags=["5. Test Data Hub"])
async def get_test_text(scenario_key: str):
    """사전 생성된 텍스트 시나리오 테스트 데이터 반환"""
    service = TestDataService.get_instance()
    if scenario_key not in service.sample_texts:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_key}' not found. Available: {list(service.sample_texts.keys())}")
    return service.sample_texts[scenario_key]


@app.get("/api/test-data/structured", tags=["5. Test Data Hub"])
async def get_test_structured_data():
    """사전 생성된 정형 고객 테이블 테스트 데이터 (JSON 및 CSV) 반환"""
    service = TestDataService.get_instance()
    return service.sample_structured


@app.get("/api/test-data/image", tags=["5. Test Data Hub"])
async def get_test_image_base64():
    """한국 신분증/확인서 시뮬레이션 테스트 이미지 (Base64) 반환"""
    service = TestDataService.get_instance()
    return {
        "title": "합성 한국 인증서 테스트 이미지",
        "description": "홍길동, 주민등록번호(900101-1234568), 휴대폰(010-1234-5678), 주소, 이메일이 포함된 이미지",
        "image_base64": service.get_sample_image_base64(),
    }


@app.get("/api/test-data/image-file", tags=["5. Test Data Hub"])
async def download_test_image_file():
    """합성 테스트 이미지 PNG 파일 직접 다운로드"""
    service = TestDataService.get_instance()
    path = service.get_sample_image_path()
    return FileResponse(path, media_type="image/png", filename="sample_korean_id.png")


@app.get("/api/test-data/dicom", tags=["5. Test Data Hub"])
async def download_test_dicom():
    """합성된 유효한 의료용 DICOM (.dcm) 샘플 파일 직접 다운로드"""
    service = TestDataService.get_instance()
    path = service.get_sample_dicom_path()
    return FileResponse(path, media_type="application/dicom", filename="sample_medical_scan.dcm")


# =====================================================================
# Web UI Dashboard (루트 경로)
# =====================================================================
@app.get("/", response_class=HTMLResponse, tags=["Dashboard UI"])
async def serve_dashboard():
    """인터랙티브 웹 대시보드 UI"""
    html_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Presidio Platform UI Loading...</h1>")
