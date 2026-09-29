from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from .anonymizer_schemas import OperatorConfigModel

class ColumnAnalysisResult(BaseModel):
    column_name: str
    detected_entity: Optional[str] = Field(default=None, description="탐지된 주요 PII 엔티티 (예: KR_RRN, KR_PHONE_NUMBER, EMAIL_ADDRESS, PERSON 등)")
    confidence_score: float = Field(default=0.0, description="탐지 신뢰도 점수")
    sample_values: List[str] = Field(default_factory=list, description="컬럼 샘플 데이터")

class StructuredAnalyzeRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(
        ...,
        description="테이블 레코드 목록 (JSON 리스트 또는 CSV 변환 데이터)",
        example=[
            {"고객명": "홍길동", "주민번호": "900101-1234568", "연락처": "010-1234-5678", "이메일": "hong@example.com"},
            {"고객명": "이순신", "주민번호": "850515-1987654", "연락처": "02-987-6543", "이메일": "lee@test.co.kr"}
        ]
    )
    language: str = Field(default="ko", description="분석 언어")
    sample_size: int = Field(default=50, description="컬럼 판별에 사용할 샘플 행 개수")

class StructuredAnalyzeResponse(BaseModel):
    success: bool = True
    total_columns: int
    total_rows: int
    columns: List[ColumnAnalysisResult]
    recommended_operators: Dict[str, OperatorConfigModel] = Field(
        ...,
        description="탐지된 엔티티에 따른 추천 비식별화 연산자 매핑"
    )

class StructuredAnonymizeRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(..., description="비식별화할 테이블 레코드 목록")
    column_operators: Dict[str, OperatorConfigModel] = Field(
        ...,
        description="컬럼별 적용할 연산자 매핑 (예: {'주민번호': {'operator': 'mask', 'params': {'chars_to_mask': 7, 'from_end': True}}, '연락처': {'operator': 'encrypt', 'params': {'key': '1234567890123456'}}})"
    )
    language: str = Field(default="ko", description="언어")

class ColumnRestorationMetadata(BaseModel):
    column_name: str
    operator: str
    key_used: Optional[str] = None

class StructuredAnonymizeResponse(BaseModel):
    success: bool = True
    total_rows: int
    anonymized_data: List[Dict[str, Any]]
    csv_string: Optional[str] = Field(default=None, description="CSV 형식 변환 문자열")
    restoration_metadata: Optional[List[ColumnRestorationMetadata]] = Field(
        default=None,
        description="암호화된 컬럼 복원에 필요한 메타데이터"
    )

class StructuredDeanonymizeRequest(BaseModel):
    anonymized_data: List[Dict[str, Any]] = Field(..., description="복원할 테이블 레코드 목록")
    column_keys: Dict[str, str] = Field(
        ...,
        description="복호화할 컬럼명 및 16/24/32 바이트 대칭키 (예: {'연락처': '1234567890123456'})"
    )

class StructuredDeanonymizeResponse(BaseModel):
    success: bool = True
    total_rows: int
    restored_data: List[Dict[str, Any]]
    csv_string: Optional[str] = Field(default=None, description="복원된 CSV 형식 문자열")
