from app.services.analyzer_service import AnalyzerService

def test_analyzer_korean_rrn_and_phone():
    """한국 주민등록번호, 전화번호, 이메일 탐지 테스트"""
    service = AnalyzerService.get_instance()
    text = "홍길동 고객님의 주민번호는 900101-1234568 이며 연락처는 010-1234-5678, 이메일은 hong@example.com 입니다."
    results = service.analyze(text=text, language="ko")

    entity_types = {r.entity_type for r in results}
    assert "KR_RRN" in entity_types, f"KR_RRN 미검출: {entity_types}"
    assert any(t in entity_types for t in ["KR_PHONE_NUMBER", "PHONE_NUMBER"]), f"전화번호 미검출: {entity_types}"
    assert "EMAIL_ADDRESS" in entity_types, f"이메일 미검출: {entity_types}"

def test_analyzer_phone_variations():
    """서울 지역번호, 휴대전화, 1588 대표번호, 지방 지역번호 등 다양한 전화번호 탐지 테스트"""
    service = AnalyzerService.get_instance()
    text = "서울지사: 02-123-4567, 휴대폰: 010-9876-5432, 고객센터: 1588-1234, 경기지사: 031-789-0123"
    results = service.analyze(text=text, language="ko")
    entities = [r.entity_type for r in results]
    assert len(entities) >= 3, f"최소 3개 이상의 전화번호가 검출되어야 함 (현재: {len(entities)})"

if __name__ == "__main__":
    test_analyzer_korean_rrn_and_phone()
    test_analyzer_phone_variations()
    print("모든 Analyzer 테스트가 성공적으로 통과되었습니다!")
