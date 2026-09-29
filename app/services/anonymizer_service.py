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
        logger.info("AnonymizerService initialized with 5 operators and Deanonymizer pipeline.")

    @classmethod
    def get_instance(cls) -> "AnonymizerService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _convert_operator_config(self, config_model: OperatorConfigModel) -> OperatorConfig:
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
            # AES key must be 16, 24, or 32 bytes
            if len(key.encode("utf-8")) not in (16, 24, 32):
                # pad or slice for safety if user gave invalid length
                key = (key + "0" * 32)[:32]
            return OperatorConfig("encrypt", {"key": key})
        else:
            # Fallback to replace
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
        # Step 1: Analyze text to find PII
        analyzer_results = self.analyzer_service.analyze(
            text=text,
            language=language,
            entities=entities,
            score_threshold=score_threshold,
        )

        # Sort analyzer results by start index ascending for accurate alignment
        sorted_analyzer_results = sorted(analyzer_results, key=lambda x: x.start)

        # Step 2: Build Presidio OperatorConfig mapping
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

        # If no operators provided at all, default to replace
        if not presidio_operators:
            presidio_operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "<PII_REDACTED>"})

        # Step 3: Anonymize
        anonymizer_result = self.anonymizer.anonymize(
            text=text,
            analyzer_results=sorted_analyzer_results,
            operators=presidio_operators,
        )

        anonymized_text = anonymizer_result.text

        # Step 4: Construct detailed mapping between original and anonymized spans
        # Note: Presidio returns items in reverse order of text appearance (from end to start)
        items_sorted_by_anon_pos = sorted(anonymizer_result.items, key=lambda x: x.start)

        item_details: List[AnonymizedItemDetail] = []
        deanonymize_items: List[DeanonymizePayloadItem] = []

        # Map each anonymized item back to its matching analyzer result
        # Because positions shift, we match by entity_type and original text
        matched_results = list(sorted_analyzer_results)

        for item in items_sorted_by_anon_pos:
            item_text = anonymized_text[item.start:item.end] if hasattr(item, "start") else item.text
            op_name = item.operator if hasattr(item, "operator") else "unknown"
            ent_type = item.entity_type

            # Find matching original result
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

            # If operator is encrypt, include in deanonymize payload
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
        Deanonymizes encrypted entities back to original text using symmetric key.
        """
        # Prepare OperatorResult list for Presidio DeanonymizeEngine
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

        # AES key length guarantee
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
