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
        logger.info("StructuredService initialized for tabular and CSV/RDBMS data.")

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
        Analyzes columns of tabular records and determines PII types and confidence scores.
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

        # Sample rows up to sample_size
        sampled_df = df.head(sample_size)

        for col in df.columns:
            col_str = str(col)
            # Collect non-null, stringified samples
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

            # Analyze sample values
            for val in col_samples[:20]:
                val = val.strip()
                if not val:
                    continue
                # Also include column name as context
                results = self.analyzer_service.analyze(
                    text=f"{col_str}: {val}",
                    language=language,
                    score_threshold=0.3,
                )
                for r in results:
                    # Filter out matches that match only the column name itself
                    if r.end > len(col_str) + 1:
                        entity_scores.setdefault(r.entity_type, []).append(r.score)

            if entity_scores:
                # Find most frequent and highest scoring entity
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

            # Recommend appropriate operator for detected entity
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
        Anonymizes tabular data column by column using specified operators.
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

            # Apply operator to each value in the column
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
                    # Use Presidio Anonymizer AES encryption engine
                    key = params.get("key", "1234567890123456")
                    resp = self.anonymizer_service.anonymize(
                        text=val_str,
                        language=language,
                        default_operator=OperatorConfigModel(operator="encrypt", params={"key": key}),
                    )
                    return resp.anonymized_text
                return val_str

            df[col] = df[col].apply(apply_op)

        # Convert back to list of dicts
        anonymized_records = df.to_dict(orient="records")

        # Convert to CSV string with UTF-8
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
        Deanonymizes encrypted columns back to original tabular data using column AES keys.
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
                    # Construct Presidio Deanonymize entity payload for the full cell
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
                    logger.warning(f"Failed to decrypt cell value '{val_str}' in column '{col}': {e}")
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
