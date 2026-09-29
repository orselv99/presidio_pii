from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AnalyzeRequest(BaseModel):
    text: str = Field(..., description="분석할 텍스트", example="홍길동 고객님의 주민번호는 900101-1234568 이며 연락처는 010-1234-5678, 이메일은 hong@example.com 입니다.")
    language: str = Field(default="ko", description="분석 언어 코드 ('ko', 'en')", example="ko")
    entities: Optional[List[str]] = Field(default=None, description="탐지할 PII 엔티티 목록 (None인 경우 전체 탐지)", example=["KR_RRN", "KR_PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON"])
    score_threshold: Optional[float] = Field(default=0.4, description="신뢰도 임계값 (0.0 ~ 1.0)", example=0.4)
    return_decision_process: Optional[bool] = Field(default=False, description="탐지 결정 프로세스 세부정보 반환 여부")

class RecognizedEntityItem(BaseModel):
    entity_type: str = Field(..., description="탐지된 엔티티 종류 (예: KR_RRN, KR_PHONE_NUMBER, EMAIL_ADDRESS, PERSON 등)")
    start: int = Field(..., description="텍스트 내 시작 인덱스")
    end: int = Field(..., description="텍스트 내 종료 인덱스")
    score: float = Field(..., description="탐지 신뢰도 점수 (0.0 ~ 1.0)")
    text: str = Field(..., description="탐지된 원문 텍스트 조각")
    recognition_metadata: Optional[Dict[str, Any]] = Field(default=None, description="인식기 추가 정보 (패턴명, 컨텍스트 등)")

class AnalyzeResponse(BaseModel):
    success: bool = True
    language: str
    total_entities: int
    entities: List[RecognizedEntityItem]
