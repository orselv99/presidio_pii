from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class BoundingBoxItem(BaseModel):
    left: int = Field(..., description="바운딩 박스 X 시작 좌표 (left)")
    top: int = Field(..., description="바운딩 박스 Y 시작 좌표 (top)")
    width: int = Field(..., description="바운딩 박스 가로 크기 (width)")
    height: int = Field(..., description="바운딩 박스 세로 크기 (height)")
    entity_type: Optional[str] = Field(default="PII", description="탐지된 엔티티 종류")
    score: Optional[float] = Field(default=None, description="신뢰도 점수")
    text: Optional[str] = Field(default=None, description="바운딩 박스 영역 내 추출 텍스트")

class ImageRedactRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 인코딩된 이미지 문자열 (data:image/... 포함 또는 순수 base64)")
    redaction_type: str = Field(default="blackout", description="마스킹 유형: 'blackout' (검은 박스 블랙아웃) 또는 'blur' (가우시안 흐림 처리)", example="blackout")
    fill_color: Optional[List[int]] = Field(default=[0, 0, 0], description="블랙아웃 색상 [R, G, B] (기본값: [0, 0, 0] 검은색)", example=[0, 0, 0])
    blur_radius: Optional[int] = Field(default=15, description="블러 처리 시 가우시안 반경 (기본값: 15)", example=15)
    language: Optional[str] = Field(default="kor+eng", description="OCR 인식 언어 ('kor+eng', 'eng', 'kor')", example="kor+eng")
    entities: Optional[List[str]] = Field(default=None, description="마스킹할 엔티티 목록 (None시 전체)")
    score_threshold: Optional[float] = Field(default=0.4, description="탐지 임계값")

class ImageRedactResponse(BaseModel):
    success: bool = True
    redaction_type: str
    total_bboxes: int
    bboxes: List[BoundingBoxItem]
    redacted_image_base64: str = Field(..., description="마스킹 처리된 이미지 Data URI (data:image/png;base64,...)")

class DicomRedactResponse(BaseModel):
    success: bool = True
    redaction_type: str
    patient_name_anonymized: Optional[str] = None
    patient_id_anonymized: Optional[str] = None
    redacted_tags: List[str] = Field(..., description="가림 처리된 DICOM 메타데이터 태그 목록")
    pixel_bboxes_count: int
    pixel_bboxes: List[BoundingBoxItem]
    preview_original_base64: Optional[str] = Field(default=None, description="원본 DICOM 픽셀 슬라이스 미리보기 이미지")
    preview_redacted_base64: str = Field(..., description="마스킹된 DICOM 픽셀 슬라이스 미리보기 이미지")
    download_url: Optional[str] = Field(default=None, description="마스킹 처리된 .dcm 파일 다운로드 URL")
