import logging
from typing import List, Optional, Dict, Any
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer import Pattern, PatternRecognizer
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
        logger.info("한국어 및 영어 이중 언어 spaCy 모델과 한국어 개체명 태그 매핑을 적용하여 Presidio AnalyzerEngine 초기화 중...")
        # 한국어 spaCy 모델의 NER 태그(PS->PERSON, OG->ORGANIZATION, LC->LOCATION, DT->DATE_TIME)를 Presidio 표준 엔티티로 매핑
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

        # 1. Presidio 공식 내장 한국어 사전정의 인식기 등록 (ko 및 en 지원)
        # 주민등록번호, 사업자등록번호, 운전면허번호, 외국인등록번호, 여권번호
        for lang in ["ko", "en"]:
            self.engine.registry.add_recognizer(KrRrnRecognizer(supported_language=lang))
            self.engine.registry.add_recognizer(KrBrnRecognizer(supported_language=lang))
            self.engine.registry.add_recognizer(KrDriverLicenseRecognizer(supported_language=lang))
            self.engine.registry.add_recognizer(KrFrnRecognizer(supported_language=lang))
            self.engine.registry.add_recognizer(KrPassportRecognizer(supported_language=lang))

        # 2. 한국 전화번호 맞춤 인식기 등록 (ko 및 en 지원)
        # 휴대전화(010), 서울(02), 지역번호(031~064), 전국대표번호(1588/1577 등), 070 지원
        self.engine.registry.add_recognizer(KrPhoneNumberRecognizer(supported_language="ko"))
        self.engine.registry.add_recognizer(KrPhoneNumberRecognizer(supported_language="en"))

        # 3. 유연한 한국 주민등록번호 인식기 등록 (OCR 인식 시 하이픈 전후 공백 허용)
        rrn_flexible_pattern = Pattern(
            name="kr_rrn_flexible_pattern",
            regex=r"(?<!\d)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?:\s*[-—–]\s*|\s+)[1-4]\d{6}(?!\d)",
            score=0.85,
        )
        for lang in ["ko", "en"]:
            self.engine.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity="KR_RRN",
                    patterns=[rrn_flexible_pattern],
                    context=["주민등록번호", "주민번호", "주민", "생년월일", "RRN", "생년", "운전면허증", "면허증"],
                    supported_language=lang,
                )
            )

        # 4. 고정밀 한국 운전면허번호 인식기 등록 (12자리 고유 번호 체계)
        dl_flexible_pattern = Pattern(
            name="kr_driver_license_flexible_pattern",
            regex=r"\b\d{2}[-\s]\d{2}[-\s]\d{6}[-\s]\d{2}\b",
            score=0.85,
        )
        for lang in ["ko", "en"]:
            self.engine.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity="KR_DRIVER_LICENSE",
                    patterns=[dl_flexible_pattern],
                    context=["운전면허", "운전면허증", "면허", "면허번호", "driver", "license", "운전면허번호", "자동차운전면허증"],
                    supported_language=lang,
                )
            )

        # 5. 글로벌 여권 MRZ(Machine Readable Zone) 코드 인식기 등록 (ICAO Doc 9303 표준)
        mrz_patterns = [
            Pattern(
                name="passport_mrz_line1",
                regex=r"\b[PA-Z0-9][<K][A-Z0-9<K\s]{15,50}\b",
                score=0.95,
            ),
            Pattern(
                name="passport_mrz_line2",
                regex=r"\b[A-Z0-9]{7,10}[<K][0-9<K][A-Z0-9<K\s]{15,45}\b",
                score=0.95,
            ),
            Pattern(
                name="passport_mrz_generic",
                regex=r"\b[A-Z0-9<K]{1,10}[<K]{1,4}[A-Z0-9<K\s]{12,44}\b",
                score=0.90,
            ),
        ]
        for lang in ["ko", "en"]:
            self.engine.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity="PASSPORT",
                    patterns=mrz_patterns,
                    context=["passport", "passeport", "mrz", "icao", "canada", "korea", "travel"],
                    supported_language=lang,
                )
            )

        # 6. 국제 여권 번호 인식기 등록 (영문 1~2자 + 숫자 6~8자 및 문맥 기반)
        intl_passport_patterns = [
            Pattern(
                name="passport_number_international",
                regex=r"\b[A-Z]{1,2}[0-9]{6,8}\b",
                score=0.45,
            ),
            Pattern(
                name="passport_number_alphanumeric",
                regex=r"\b(?=[A-Z0-9]{8,9}\b)(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{8,9}\b",
                score=0.35,
            ),
        ]
        for lang in ["ko", "en"]:
            self.engine.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity="PASSPORT",
                    patterns=intl_passport_patterns,
                    context=[
                        "passport", "passeport", "passport no", "passport number",
                        "passeport no", "no de passeport", "document no", "여권",
                        "여권번호", "여권 no", "pass number", "nationality", "issuing country", "authority"
                    ],
                    supported_language=lang,
                )
            )

        # 7. 신분증 성명(Surname, Given names, Nom, Prénoms) 문맥 기반 성명 인식기 등록
        surname_pattern = Pattern(
            name="passport_surname",
            regex=r"(?i:(?:Surname|Nom|Sumame)[\s/:\-_a-z]*\s+)([A-Z]{2,20})\b",
            score=0.85,
        )
        given_name_pattern = Pattern(
            name="passport_given_name",
            regex=r"(?i:(?:Given\s*names?|Pr[ée]noms?)[\s/:\-_a-z]*\s+)([A-Z]{2,20})\b",
            score=0.85,
        )
        for lang in ["ko", "en"]:
            self.engine.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity="PERSON",
                    patterns=[surname_pattern, given_name_pattern],
                    supported_language=lang,
                )
            )

        logger.info(
            "공식 한국어 사전정의 인식기(KR_RRN, KR_BRN, KR_DRIVER_LICENSE, KR_FRN, KR_PASSPORT), "
            "KR_PHONE_NUMBER 및 향상된 RRN, 운전면허, 국제 여권/MRZ, 신분증 성명 인식기 등록 완료."
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
        입력 텍스트에 대해 개인정보(PII) 탐지를 실행합니다.
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
        """
        텍스트 내 PII를 분석하고 응답 스키마(AnalyzeResponse) 형태로 변환하여 반환합니다.
        """
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
