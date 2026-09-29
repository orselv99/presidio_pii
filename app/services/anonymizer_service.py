import logging
from typing import Dict, List, Optional, Any, Tuple
from presidio_anonymizer import AnonymizerEngine, DeanonymizeEngine
from presidio_anonymizer.entities import OperatorConfig, RecognizerResult, OperatorResult

from app.services.analyzer_service import AnalyzerService
from app.schemas.anonymizer_schemas import (
    OperatorConfigModel,
    AnonymizeResponse,
    AnonymizedItemDetail,
    DeanonymizePayload,
    DeanonymizePayloadItem,
    DeanonymizeResponse,
)

logger = logging.getLogger(__name__)

class AnonymizerService:
    _instance: Optional["AnonymizerService"] = None

    def __init__(self, analyzer_service: Optional[AnalyzerService] = None):
        self.analyzer_service = analyzer_service or AnalyzerService.get_instance()
        self.anonymizer = AnonymizerEngine()
        self.deanonymizer = DeanonymizeEngine()
        logger.info("AnonymizerService가 5대 비식별화 연산자 및 복원(Deanonymizer) 파이프라인과 함께 초기화되었습니다.")

    @classmethod
    def get_instance(cls) -> "AnonymizerService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _convert_operator_config(self, config_model: OperatorConfigModel) -> OperatorConfig:
        """API 연산자 설정 모델을 Presidio 내부 OperatorConfig 객체로 변환합니다."""
        op = config_model.operator.lower()
        params = dict(config_model.params or {})

        if op == "redact":
            return OperatorConfig("redact", {})
        elif op == "replace":
            new_val = params.get("new_value", "<REDACTED>")
            return OperatorConfig("replace", {"new_value": new_val})
        elif op == "mask":
            masking_char = params.get("masking_char", "*")
            chars_to_mask = int(params.get("chars_to_mask", 4))
            from_end = bool(params.get("from_end", True))
            return OperatorConfig("mask", {
                "masking_char": masking_char,
                "chars_to_mask": chars_to_mask,
                "from_end": from_end,
            })
        elif op == "hash":
            hash_type = params.get("hash_type", "sha256")
            hash_params = {"hash_type": hash_type}
            if "salt" in params and params["salt"]:
                hash_params["salt"] = params["salt"]
            return OperatorConfig("hash", hash_params)
        elif op == "encrypt":
            key = params.get("key", "1234567890123456")
            # AES 대칭키 길이는 반드시 16, 24, 32바이트여야 함
            if len(key.encode("utf-8")) not in (16, 24, 32):
                # 유효하지 않은 길이인 경우 32바이트로 패딩 또는 절삭
                key = (key + "0" * 32)[:32]
            return OperatorConfig("encrypt", {"key": key})
        else:
            # 기타 예외 시 대체 연산자로 폴백
            return OperatorConfig("replace", {"new_value": f"<{op.upper()}>"})

    def anonymize(
        self,
        text: str,
        language: str = "ko",
        operators_map: Optional[Dict[str, OperatorConfigModel]] = None,
        default_operator: Optional[OperatorConfigModel] = None,
        entities: Optional[List[str]] = None,
        score_threshold: Optional[float] = 0.4,
    ) -> AnonymizeResponse:
        """
        텍스트 내 개인정보(PII)를 검출하고 지정된 연산자(삭제, 대체, 마스킹, 해싱, 암호화)를 적용하여 비식별화합니다.
        """
        # 1단계: 텍스트에서 PII 위치 및 엔티티 탐지
        analyzer_results = self.analyzer_service.analyze(
            text=text,
            language=language,
            entities=entities,
            score_threshold=score_threshold,
        )

        # 위치 정렬을 위해 시작 인덱스 기준 오름차순 정렬
        sorted_analyzer_results = sorted(analyzer_results, key=lambda x: x.start)

        # 2단계: Presidio OperatorConfig 맵 구성
        presidio_operators: Dict[str, OperatorConfig] = {}
        encryption_key_used: Optional[str] = None
        has_encryption = False

        if operators_map:
            for ent_type, op_model in operators_map.items():
                presidio_operators[ent_type] = self._convert_operator_config(op_model)
                if op_model.operator.lower() == "encrypt":
                    has_encryption = True
                    if not encryption_key_used:
                        encryption_key_used = op_model.params.get("key", "1234567890123456")

        if default_operator:
            presidio_operators["DEFAULT"] = self._convert_operator_config(default_operator)
            if default_operator.operator.lower() == "encrypt":
                has_encryption = True
                if not encryption_key_used:
                    encryption_key_used = default_operator.params.get("key", "1234567890123456")

        # 연산자가 지정되지 않은 경우 기본값으로 <PII_REDACTED> 대체 연산자 적용
        if not presidio_operators:
            presidio_operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "<PII_REDACTED>"})

        # 3단계: 비식별화 실행
        anonymizer_result = self.anonymizer.anonymize(
            text=text,
            analyzer_results=sorted_analyzer_results,
            operators=presidio_operators,
        )

        anonymized_text = anonymizer_result.text

        # 4단계: 원문과 비식별화된 구간 간의 상세 매핑 구성
        # 비식별화 후 텍스트 위치 기준 오름차순 정렬
        items_sorted_by_anon_pos = sorted(anonymizer_result.items, key=lambda x: x.start)

        item_details: List[AnonymizedItemDetail] = []
        deanonymize_items: List[DeanonymizePayloadItem] = []

        # 엔티티 타입 및 순서에 맞춰 원래의 분석 결과와 매핑
        matched_results = list(sorted_analyzer_results)

        for item in items_sorted_by_anon_pos:
            item_text = anonymized_text[item.start:item.end] if hasattr(item, "start") else item.text
            op_name = item.operator if hasattr(item, "operator") else "unknown"
            ent_type = item.entity_type

            # 매칭되는 원본 분석 결과 검색
            orig_res = None
            for idx, candidate in enumerate(matched_results):
                if candidate.entity_type == ent_type:
                    orig_res = matched_results.pop(idx)
                    break

            if orig_res:
                orig_start = orig_res.start
                orig_end = orig_res.end
                orig_text = text[orig_start:orig_end]
            else:
                orig_start = 0
                orig_end = 0
                orig_text = ""

            item_details.append(
                AnonymizedItemDetail(
                    start=item.start,
                    end=item.end,
                    entity_type=ent_type,
                    operator=op_name,
                    anonymized_text=item_text,
                    original_text=orig_text,
                    original_start=orig_start,
                    original_end=orig_end,
                )
            )

            # 암호화 연산자가 적용된 경우 원문 복원(Deanonymize) 페이로드에 추가
            if op_name.lower() == "encrypt":
                deanonymize_items.append(
                    DeanonymizePayloadItem(
                        start=item.start,
                        end=item.end,
                        entity_type=ent_type,
                        operator=op_name,
                        text=item_text,
                    )
                )

        deanonymize_payload = None
        if has_encryption and deanonymize_items:
            deanonymize_payload = DeanonymizePayload(
                text=anonymized_text,
                items=deanonymize_items,
                encryption_key_used=encryption_key_used,
            )

        return AnonymizeResponse(
            success=True,
            original_text=text,
            anonymized_text=anonymized_text,
            total_anonymized=len(item_details),
            items=item_details,
            is_reversible=has_encryption and len(deanonymize_items) > 0,
            deanonymize_payload=deanonymize_payload,
        )

    def deanonymize(
        self,
        text: str,
        items: List[DeanonymizePayloadItem],
        encryption_key: str,
        operators: Optional[Dict[str, OperatorConfigModel]] = None,
    ) -> DeanonymizeResponse:
        """
        대칭키를 사용하여 암호화된 개인정보 영역을 원래의 텍스트로 복호화(Deanonymize)합니다.
        """
        # Presidio DeanonymizeEngine용 OperatorResult 리스트 생성
        presidio_entities: List[OperatorResult] = []
        for it in items:
            presidio_entities.append(
                OperatorResult(
                    start=it.start,
                    end=it.end,
                    entity_type=it.entity_type,
                    text=it.text,
                    operator=it.operator,
                )
            )

        # AES 키 길이 검증 및 보정 (16, 24, 32바이트)
        if len(encryption_key.encode("utf-8")) not in (16, 24, 32):
            encryption_key = (encryption_key + "0" * 32)[:32]

        presidio_operators: Dict[str, OperatorConfig] = {
            "DEFAULT": OperatorConfig("decrypt", {"key": encryption_key})
        }

        if operators:
            for ent_type, op_conf in operators.items():
                presidio_operators[ent_type] = self._convert_operator_config(op_conf)

        result = self.deanonymizer.deanonymize(
            text=text,
            entities=presidio_entities,
            operators=presidio_operators,
        )

        return DeanonymizeResponse(
            success=True,
            restored_text=result.text,
            restored_items_count=len(items),
        )
