from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

class OperatorConfigModel(BaseModel):
    operator: str = Field(..., description="연산자 종류: 'redact'(삭제), 'replace'(대체), 'mask'(마스킹), 'hash'(해싱), 'encrypt'(암호화)", example="mask")
    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="""
        연산자별 세부 파라미터:
        - redact: {}
        - replace: {"new_value": "<REDACTED>"}
        - mask: {"masking_char": "*", "chars_to_mask": 4, "from_end": True}
        - hash: {"hash_type": "sha256", "salt": "my_salt"} (지원: sha256, sha512, md5)
        - encrypt: {"key": "16_24_or_32_bytes_key"} (AES 대칭키)
        """,
        example={"masking_char": "*", "chars_to_mask": 4, "from_end": True}
    )

class AnonymizeRequest(BaseModel):
    text: str = Field(..., description="비식별화할 원문 텍스트", example="홍길동 고객님의 주민번호는 900101-1234568 이며 연락처는 010-1234-5678 입니다.")
    language: str = Field(default="ko", description="언어 코드 ('ko', 'en')", example="ko")
    # 엔티티별 연산자 매핑 또는 기본 연산자
    operators: Optional[Dict[str, OperatorConfigModel]] = Field(
        default=None,
        description="엔티티별 연산자 설정 (예: {'KR_RRN': {'operator': 'encrypt', 'params': {'key': '1234567890123456'}}, 'KR_PHONE_NUMBER': {'operator': 'mask', 'params': {'chars_to_mask': 4, 'from_end': True}}})",
    )
    default_operator: Optional[OperatorConfigModel] = Field(
        default=OperatorConfigModel(operator="replace", params={"new_value": "<PII_REDACTED>"}),
        description="개별 설정이 없는 엔티티에 적용될 기본 연산자"
    )
    # 텍스트 사전 분석이 없는 경우 직접 분석기 설정
    entities: Optional[List[str]] = Field(default=None, description="탐지할 PII 엔티티 목록 (None시 전체)")
    score_threshold: Optional[float] = Field(default=0.4, description="신뢰도 임계값")

class AnonymizedItemDetail(BaseModel):
    start: int = Field(..., description="비식별화된 텍스트 내 시작 인덱스")
    end: int = Field(..., description="비식별화된 텍스트 내 종료 인덱스")
    entity_type: str = Field(..., description="엔티티 종류")
    operator: str = Field(..., description="적용된 비식별화 연산자")
    anonymized_text: str = Field(..., description="변환된 텍스트 조각")
    original_text: str = Field(..., description="원본 텍스트 조각")
    original_start: int = Field(..., description="원본 텍스트 내 시작 인덱스")
    original_end: int = Field(..., description="원본 텍스트 내 종료 인덱스")

class DeanonymizePayloadItem(BaseModel):
    start: int
    end: int
    entity_type: str
    operator: str
    text: str

class DeanonymizePayload(BaseModel):
    text: str = Field(..., description="복원할 비식별화된 텍스트")
    items: List[DeanonymizePayloadItem] = Field(..., description="암호화된 엔티티 위치 및 메타데이터")
    encryption_key_used: Optional[str] = Field(default=None, description="암호화에 사용된 대칭키 (사용자 편의 및 복원용)")

class AnonymizeResponse(BaseModel):
    success: bool = True
    original_text: str
    anonymized_text: str
    total_anonymized: int
    items: List[AnonymizedItemDetail]
    is_reversible: bool = Field(..., description="원문 복원(Deanonymization) 가능 여부 (encrypt 연산자 포함 여부)")
    deanonymize_payload: Optional[DeanonymizePayload] = Field(
        default=None,
        description="복원(Deanonymizer) API 호출에 바로 사용할 수 있는 페이로드 및 메타데이터"
    )

class DeanonymizeRequest(BaseModel):
    text: str = Field(..., description="복원할 비식별화 텍스트", example="홍길동 고객님의 주민번호는 lFli7S1OsYXYkOgrURMPbNHaE96oUOUiSRtOtvVLSWU= 이며...")
    items: List[DeanonymizePayloadItem] = Field(..., description="비식별화 시 반환된 items 메타데이터")
    encryption_key: str = Field(..., description="복호화에 필요한 16/24/32 바이트 대칭키", example="1234567890123456")
    operators: Optional[Dict[str, OperatorConfigModel]] = Field(
        default=None,
        description="복호화 연산자 설정 (기본값: DEFAULT -> decrypt with encryption_key)"
    )

class DeanonymizeResponse(BaseModel):
    success: bool = True
    restored_text: str = Field(..., description="복원된 원문 텍스트")
    restored_items_count: int
