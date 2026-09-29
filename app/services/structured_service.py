import io
import re
import csv
import logging
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from collections import Counter

from presidio_anonymizer.entities import OperatorConfig
from app.services.analyzer_service import AnalyzerService
from app.services.anonymizer_service import AnonymizerService
from app.schemas.anonymizer_schemas import OperatorConfigModel
from app.schemas.structured_schemas import (
    ColumnAnalysisResult,
    StructuredAnalyzeResponse,
    StructuredAnonymizeResponse,
    StructuredDeanonymizeResponse,
    ColumnRestorationMetadata,
)

logger = logging.getLogger(__name__)

class StructuredService:
    _instance: Optional["StructuredService"] = None

    def __init__(
        self,
        analyzer_service: Optional[AnalyzerService] = None,
        anonymizer_service: Optional[AnonymizerService] = None,
    ):
        self.analyzer_service = analyzer_service or AnalyzerService.get_instance()
        self.anonymizer_service = anonymizer_service or AnonymizerService.get_instance()
        logger.info("StructuredService가 정형(CSV/RDBMS) 데이터 처리를 위해 초기화되었습니다.")

    @classmethod
    def get_instance(cls) -> "StructuredService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def analyze_table(
        self,
        data: List[Dict[str, Any]],
        language: str = "ko",
        sample_size: int = 50,
    ) -> StructuredAnalyzeResponse:
        """
        테이블 형태의 레코드 열(Column)을 표본 분석하여 PII 유형과 신뢰도 점수를 판정합니다.
        """
        if not data:
            return StructuredAnalyzeResponse(
                success=True,
                total_columns=0,
                total_rows=0,
                columns=[],
                recommended_operators={},
            )

        df = pd.DataFrame(data)
        columns_result: List[ColumnAnalysisResult] = []
        recommended_ops: Dict[str, OperatorConfigModel] = {}

        # 지정된 sample_size 크기만큼 상위 행 추출
        sampled_df = df.head(sample_size)

        for col in df.columns:
            col_str = str(col)
            # 결측값을 제외한 문자열 표본 수집
            col_samples = sampled_df[col].dropna().astype(str).tolist()
            if not col_samples:
                columns_result.append(
                    ColumnAnalysisResult(
                        column_name=col_str,
                        detected_entity=None,
                        confidence_score=0.0,
                        sample_values=[],
                    )
                )
                continue

            entity_scores: Dict[str, List[float]] = {}

            # 표본 데이터 값 분석 (최대 20개 샘플)
            for val in col_samples[:20]:
                val = val.strip()
                if not val:
                    continue
                # 열 이름을 문맥(Context)으로 함께 전달
                results = self.analyzer_service.analyze(
                    text=f"{col_str}: {val}",
                    language=language,
                    score_threshold=0.3,
                )
                for r in results:
                    # 열 이름 자체에만 매칭된 결과는 필터링
                    if r.end > len(col_str) + 1:
                        entity_scores.setdefault(r.entity_type, []).append(r.score)

            if entity_scores:
                # 빈도수 및 신뢰도 총합 기준 최적의 엔티티 결정
                best_entity = max(entity_scores.keys(), key=lambda e: (len(entity_scores[e]), sum(entity_scores[e])))
                avg_score = round(sum(entity_scores[best_entity]) / len(entity_scores[best_entity]), 4)
            else:
                best_entity = None
                avg_score = 0.0

            columns_result.append(
                ColumnAnalysisResult(
                    column_name=col_str,
                    detected_entity=best_entity,
                    confidence_score=avg_score,
                    sample_values=[str(s) for s in col_samples[:3]],
                )
            )

            # 탐지된 PII 유형에 적합한 추천 연산자 매핑
            if best_entity:
                if best_entity == "KR_RRN":
                    recommended_ops[col_str] = OperatorConfigModel(
                        operator="mask",
                        params={"masking_char": "*", "chars_to_mask": 7, "from_end": True},
                    )
                elif best_entity in ("KR_PHONE_NUMBER", "PHONE_NUMBER"):
                    recommended_ops[col_str] = OperatorConfigModel(
                        operator="mask",
                        params={"masking_char": "*", "chars_to_mask": 4, "from_end": True},
                    )
                elif best_entity == "EMAIL_ADDRESS":
                    recommended_ops[col_str] = OperatorConfigModel(
                        operator="mask",
                        params={"masking_char": "*", "chars_to_mask": 6, "from_end": False},
                    )
                elif best_entity == "PERSON":
                    recommended_ops[col_str] = OperatorConfigModel(
                        operator="replace",
                        params={"new_value": "<고객명>"},
                    )
                else:
                    recommended_ops[col_str] = OperatorConfigModel(
                        operator="replace",
                        params={"new_value": f"<{best_entity}>"},
                    )

        return StructuredAnalyzeResponse(
            success=True,
            total_columns=len(columns_result),
            total_rows=len(df),
            columns=columns_result,
            recommended_operators=recommended_ops,
        )

    def anonymize_table(
        self,
        data: List[Dict[str, Any]],
        column_operators: Dict[str, OperatorConfigModel],
        language: str = "ko",
    ) -> StructuredAnonymizeResponse:
        """
        지정된 열별 연산자를 적용하여 정형 테이블 데이터를 비식별화합니다.
        """
        if not data:
            return StructuredAnonymizeResponse(
                success=True,
                total_rows=0,
                anonymized_data=[],
                csv_string="",
                restoration_metadata=[],
            )

        df = pd.DataFrame(data).copy()
        restoration_meta: List[ColumnRestorationMetadata] = []

        for col, op_model in column_operators.items():
            if col not in df.columns:
                continue

            op_type = op_model.operator.lower()
            params = dict(op_model.params or {})

            if op_type == "encrypt":
                key = params.get("key", "1234567890123456")
                restoration_meta.append(
                    ColumnRestorationMetadata(column_name=col, operator="encrypt", key_used=key)
                )

            # 열 내의 각 셀 값에 연산자 적용
            def apply_op(val):
                if pd.isna(val) or val == "":
                    return val
                val_str = str(val)

                if op_type == "redact":
                    return ""
                elif op_type == "replace":
                    return params.get("new_value", "<REDACTED>")
                elif op_type == "mask":
                    m_char = params.get("masking_char", "*")
                    c_mask = int(params.get("chars_to_mask", 4))
                    from_end = bool(params.get("from_end", True))
                    if len(val_str) <= c_mask:
                        return m_char * len(val_str)
                    if from_end:
                        return val_str[:-c_mask] + (m_char * c_mask)
                    else:
                        return (m_char * c_mask) + val_str[c_mask:]
                elif op_type == "hash":
                    import hashlib
                    h_type = params.get("hash_type", "sha256").lower()
                    salt = params.get("salt", "")
                    target = (val_str + salt).encode("utf-8")
                    if h_type == "md5":
                        return hashlib.md5(target).hexdigest()
                    elif h_type == "sha512":
                        return hashlib.sha512(target).hexdigest()
                    else:
                        return hashlib.sha256(target).hexdigest()
                elif op_type == "encrypt":
                    # Presidio Anonymizer AES 대칭키 암호화 엔진 사용
                    key = params.get("key", "1234567890123456")
                    resp = self.anonymizer_service.anonymize(
                        text=val_str,
                        language=language,
                        default_operator=OperatorConfigModel(operator="encrypt", params={"key": key}),
                    )
                    return resp.anonymized_text
                return val_str

            df[col] = df[col].apply(apply_op)

        # 딕셔너리 리스트로 변환
        anonymized_records = df.to_dict(orient="records")

        # UTF-8 CSV 문자열로 변환
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_str = csv_buffer.getvalue()

        return StructuredAnonymizeResponse(
            success=True,
            total_rows=len(df),
            anonymized_data=anonymized_records,
            csv_string=csv_str,
            restoration_metadata=restoration_meta if restoration_meta else None,
        )

    def deanonymize_table(
        self,
        anonymized_data: List[Dict[str, Any]],
        column_keys: Dict[str, str],
    ) -> StructuredDeanonymizeResponse:
        """
        열별 AES 대칭키를 사용하여 암호화된 정형 데이터를 원래의 원문 데이터로 복원(Deanonymize)합니다.
        """
        if not anonymized_data:
            return StructuredDeanonymizeResponse(
                success=True,
                total_rows=0,
                restored_data=[],
                csv_string="",
            )

        df = pd.DataFrame(anonymized_data).copy()

        for col, key in column_keys.items():
            if col not in df.columns:
                continue

            def decrypt_val(val):
                if pd.isna(val) or not str(val).strip():
                    return val
                val_str = str(val).strip()
                try:
                    # 셀 전체 값에 대한 Presidio Deanonymize 엔티티 페이로드 구성
                    from app.schemas.anonymizer_schemas import DeanonymizePayloadItem
                    payload_item = DeanonymizePayloadItem(
                        start=0,
                        end=len(val_str),
                        entity_type="PII",
                        operator="encrypt",
                        text=val_str,
                    )
                    resp = self.anonymizer_service.deanonymize(
                        text=val_str,
                        items=[payload_item],
                        encryption_key=key,
                    )
                    return resp.restored_text
                except Exception as e:
                    logger.warning(f"열 '{col}'의 셀 값 '{val_str}' 복호화 실패: {e}")
                    return val_str

            df[col] = df[col].apply(decrypt_val)

        restored_records = df.to_dict(orient="records")

        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_str = csv_buffer.getvalue()

        return StructuredDeanonymizeResponse(
            success=True,
            total_rows=len(df),
            restored_data=restored_records,
            csv_string=csv_str,
        )
