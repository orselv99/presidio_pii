import re
from typing import List, Optional
from presidio_analyzer import PatternRecognizer, Pattern

class KrPhoneNumberRecognizer(PatternRecognizer):
    """
    Korean Phone Number Recognizer.
    Supports:
      1. Mobile numbers: 010, 011, 016, 017, 018, 019 (e.g., 010-1234-5678, 01012345678)
      2. Seoul landlines: 02 (e.g., 02-123-4567, 02-1234-5678)
      3. Regional landlines: 031~064 (e.g., 031-123-4567, 051-1234-5678)
      4. VoIP & Services: 070, 080, 0502~0507
      5. Representative & Customer Service numbers: 1588, 1577, 1544, 1566, 1600, 1670, 1688, 1800, 1811, 1899
      6. International format: +82-10-1234-5678, +82-2-123-4567
    """

    PATTERNS = [
        # Mobile with hyphen/separator: 010-1234-5678, 010.1234.5678, 010 1234 5678
        Pattern(
            name="KR_PHONE_MOBILE_HYPHEN",
            regex=r"\b(?:(?:\+82|82)[-.\s]?0?|0)1[016789][-.\s]\d{3,4}[-.\s]\d{4}\b",
            score=0.85,
        ),
        # Mobile continuous 10-11 digits: 01012345678
        Pattern(
            name="KR_PHONE_MOBILE_CONTINUOUS",
            regex=r"\b(?:(?:\+82|82)0?|0)1[016789]\d{7,8}\b",
            score=0.6,
        ),
        # Seoul landline with hyphen: 02-123-4567, 02-1234-5678
        Pattern(
            name="KR_PHONE_SEOUL_HYPHEN",
            regex=r"\b(?:(?:\+82|82)[-.\s]?0?|0)2[-.\s]\d{3,4}[-.\s]\d{4}\b",
            score=0.8,
        ),
        # Regional landlines: 031, 032, 033, 041, 042, 043, 044, 051, 052, 053, 054, 055, 061, 062, 063, 064
        Pattern(
            name="KR_PHONE_REGIONAL_HYPHEN",
            regex=r"\b(?:(?:\+82|82)[-.\s]?0?|0)(?:3[1-3]|4[1-4]|5[1-5]|6[1-4])[-.\s]\d{3,4}[-.\s]\d{4}\b",
            score=0.8,
        ),
        # VoIP & Toll-free numbers: 070, 080, 050x
        Pattern(
            name="KR_PHONE_VOIP_TOLLFREE",
            regex=r"\b(?:(?:\+82|82)[-.\s]?0?|0)(?:70|80|50[2-7])[-.\s]\d{3,4}[-.\s]\d{4}\b",
            score=0.8,
        ),
        # Nationwide representative/customer service numbers: 1588-1234, 1577-1234, etc.
        Pattern(
            name="KR_PHONE_REPRESENTATIVE",
            regex=r"\b(?:1588|1577|1544|1566|1600|1670|1688|1800|1811|1899)[-.\s]\d{4}\b",
            score=0.75,
        ),
    ]

    CONTEXT = [
        "전화번호", "전화", "휴대폰", "핸드폰", "연락처", "모바일", "폰번호",
        "대표번호", "고객센터", "문의전화", "팩스", "fax",
        "tel", "hp", "phone", "call", "contact", "mobile"
    ]

    def __init__(
        self,
        supported_language: str = "ko",
        supported_entities: Optional[List[str]] = None,
    ):
        supported_entities = supported_entities or ["KR_PHONE_NUMBER"]
        super().__init__(
            supported_entity=supported_entities[0],
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )

    def validate_result(self, pattern_text: str) -> bool:
        """
        Validate phone number structure.
        """
        digits = re.sub(r"\D", "", pattern_text)
        # Standard Korean numbers are 8 digits (representative), 9-11 digits (landline/mobile), or with country code 11-13 digits
        if len(digits) < 8 or len(digits) > 13:
            return False
        return True
