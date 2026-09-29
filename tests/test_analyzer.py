from app.services.analyzer_service import AnalyzerService

def test_analyzer_korean_rrn_and_phone():
    service = AnalyzerService.get_instance()
    text = "홍길동 고객님의 주민번호는 900101-1234568 이며 연락처는 010-1234-5678, 이메일은 hong@example.com 입니다."
    results = service.analyze(text=text, language="ko")

    entity_types = {r.entity_type for r in results}
    assert "KR_RRN" in entity_types, f"KR_RRN not found in {entity_types}"
    assert any(t in entity_types for t in ["KR_PHONE_NUMBER", "PHONE_NUMBER"]), f"Phone not found in {entity_types}"
    assert "EMAIL_ADDRESS" in entity_types, f"Email not found in {entity_types}"

def test_analyzer_phone_variations():
    service = AnalyzerService.get_instance()
    # Test seoul landline, mobile, 1588 representative
    text = "서울지사: 02-123-4567, 휴대폰: 010-9876-5432, 고객센터: 1588-1234, 경기지사: 031-789-0123"
    results = service.analyze(text=text, language="ko")
    entities = [r.entity_type for r in results]
    assert len(entities) >= 3, f"Expected at least 3 phone numbers, found {len(entities)}"

if __name__ == "__main__":
    test_analyzer_korean_rrn_and_phone()
    test_analyzer_phone_variations()
    print("All Analyzer tests passed successfully!")
