import re
from typing import List, Optional
from presidio_analyzer import PatternRecognizer, Pattern

class KrPhoneNumberRecognizer(PatternRecognizer):
    """
    한국 전화번호 인식기.
    지원 유형:
      1. 휴대전화번호: 010, 011, 016, 017, 018, 019 (예: 010-1234-5678, 01012345678)
      2. 서울 지역 유선전화: 02 (예: 02-123-4567, 02-1234-5678)
      3. 지방 지역 유선전화: 031~064 (예: 031-123-4567, 051-1234-5678)
      4. 인터넷전화 및 평생번호: 070, 080, 0502~0507
      5. 전국 대표번호 및 고객센터: 1588, 1577, 1544, 1566, 1600, 1670, 1688, 1800, 1811, 1899
      6. 국가번호 포함 국제 포맷: +82-10-1234-5678, +82-2-123-4567
    """

    PATTERNS = [
        # 하이픈/구분자 포함 휴대전화번호: 010-1234-5678, 010.1234.5678, 010 1234 5678
        Pattern(
            name="KR_PHONE_MOBILE_HYPHEN",
            regex=r"\b(?:(?:\+82|82)[-.\s]?0?|0)1[016789][-.\s]\d{3,4}[-.\s]\d{4}\b",
            score=0.85,
        ),
        # 10~11자리 연속된 숫자 휴대전화번호: 01012345678
        Pattern(
            name="KR_PHONE_MOBILE_CONTINUOUS",
            regex=r"\b(?:(?:\+82|82)0?|0)1[016789]\d{7,8}\b",
            score=0.6,
        ),
        # 서울 지역번호 유선전화 (02): 02-123-4567, 02-1234-5678
        Pattern(
            name="KR_PHONE_SEOUL_HYPHEN",
            regex=r"\b(?:(?:\+82|82)[-.\s]?0?|0)2[-.\s]\d{3,4}[-.\s]\d{4}\b",
            score=0.8,
        ),
        # 전국 시/도 지역 유선전화: 031, 032, 033, 041, 042, 043, 044, 051, 052, 053, 054, 055, 061, 062, 063, 064
        Pattern(
            name="KR_PHONE_REGIONAL_HYPHEN",
            regex=r"\b(?:(?:\+82|82)[-.\s]?0?|0)(?:3[1-3]|4[1-4]|5[1-5]|6[1-4])[-.\s]\d{3,4}[-.\s]\d{4}\b",
            score=0.8,
        ),
        # 인터넷전화(070), 수신자부담(080), 안심번호(050x)
        Pattern(
            name="KR_PHONE_VOIP_TOLLFREE",
            regex=r"\b(?:(?:\+82|82)[-.\s]?0?|0)(?:70|80|50[2-7])[-.\s]\d{3,4}[-.\s]\d{4}\b",
            score=0.8,
        ),
        # 전국 대표번호 및 고객센터 번호: 1588-1234, 1577-1234 등
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
        전화번호의 유효 자릿수를 검증합니다.
        """
        digits = re.sub(r"\D", "", pattern_text)
        # 한국 전화번호 유효 자릿수: 대표번호(8자리), 일반/휴대폰(9~11자리), 국가번호 포함(11~13자리)
        if len(digits) < 8 or len(digits) > 13:
            return False
        return True
