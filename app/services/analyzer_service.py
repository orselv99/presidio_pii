import logging
from typing import List, Optional, Dict, Any
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    KrRrnRecognizer,
    KrBrnRecognizer,
    KrDriverLicenseRecognizer,
    KrFrnRecognizer,
    KrPassportRecognizer,
)

from .kr_phone_recognizer import KrPhoneNumberRecognizer
from app.schemas.analyzer_schemas import RecognizedEntityItem, AnalyzeResponse

logger = logging.getLogger(__name__)

class AnalyzerService:
    _instance: Optional["AnalyzerService"] = None

    def __init__(self):
        logger.info("Initializing Presidio AnalyzerEngine with bilingual (ko, en) Spacy models & Korean NER mapping...")
        # Configure Spacy NLP engine with English and Korean models and mapping for Korean NER tags (PS->PERSON, LC->LOCATION, OG->ORGANIZATION)
        nlp_configuration = {
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "en", "model_name": "en_core_web_lg"},
                {"lang_code": "ko", "model_name": "ko_core_news_lg"},
            ],
            "ner_model_configuration": {
                "model_to_presidio_entity_mapping": {
                    "PS": "PERSON",
                    "OG": "ORGANIZATION",
                    "LC": "LOCATION",
                    "DT": "DATE_TIME",
                    "PER": "PERSON",
                    "PERSON": "PERSON",
                    "LOC": "LOCATION",
                    "GPE": "LOCATION",
                    "ORG": "ORGANIZATION",
                },
                "low_confidence_score_multiplier": 0.4,
            },
        }
        provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
        nlp_engine = provider.create_engine()

        self.engine = AnalyzerEngine(
            nlp_engine=nlp_engine,
            supported_languages=["ko", "en"],
        )

        # 1. Presidio 공식 내장 한국어 사전정의 인식기 (ko 및 en 모두 등록)
        # 한국 주민번호, 사업자번호, 운전면허, 외국인등록번호, 여권번호
        for lang in ["ko", "en"]:
            self.engine.registry.add_recognizer(KrRrnRecognizer(supported_language=lang))
            self.engine.registry.add_recognizer(KrBrnRecognizer(supported_language=lang))
            self.engine.registry.add_recognizer(KrDriverLicenseRecognizer(supported_language=lang))
            self.engine.registry.add_recognizer(KrFrnRecognizer(supported_language=lang))
            self.engine.registry.add_recognizer(KrPassportRecognizer(supported_language=lang))

        # 2. 한국 전화번호 맞춤 인식기 (ko 및 en 모두 등록)
        # 휴대전화(010), 서울(02), 지역번호(031~064), 전국대표번호(1588/1577 등), 070 지원
        self.engine.registry.add_recognizer(KrPhoneNumberRecognizer(supported_language="ko"))
        self.engine.registry.add_recognizer(KrPhoneNumberRecognizer(supported_language="en"))

        logger.info(
            "Presidio AnalyzerEngine initialized with official Korean recognizers "
            "(KR_RRN, KR_BRN, KR_DRIVER_LICENSE, KR_FRN, KR_PASSPORT) and KR_PHONE_NUMBER (ko & en)."
        )

    @classmethod
    def get_instance(cls) -> "AnalyzerService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def analyze(
        self,
        text: str,
        language: str = "ko",
        entities: Optional[List[str]] = None,
        score_threshold: Optional[float] = 0.4,
        return_decision_process: bool = False,
    ) -> List[RecognizerResult]:
        """
        Executes PII analysis on text.
        """
        if language not in ("ko", "en"):
            language = "ko"

        results = self.engine.analyze(
            text=text,
            language=language,
            entities=entities,
            score_threshold=score_threshold,
            return_decision_process=return_decision_process,
        )
        return results

    def analyze_to_response(
        self,
        text: str,
        language: str = "ko",
        entities: Optional[List[str]] = None,
        score_threshold: Optional[float] = 0.4,
    ) -> AnalyzeResponse:
        results = self.analyze(
            text=text,
            language=language,
            entities=entities,
            score_threshold=score_threshold,
        )

        entity_items: List[RecognizedEntityItem] = []
        for res in results:
            entity_items.append(
                RecognizedEntityItem(
                    entity_type=res.entity_type,
                    start=res.start,
                    end=res.end,
                    score=round(res.score, 4),
                    text=text[res.start:res.end],
                    recognition_metadata={
                        "analysis_explanation": res.analysis_explanation.to_dict()
                        if res.analysis_explanation
                        else None
                    },
                )
            )

        return AnalyzeResponse(
            success=True,
            language=language,
            total_entities=len(entity_items),
            entities=entity_items,
        )
