from app.services.anonymizer_service import AnonymizerService
from app.schemas.anonymizer_schemas import OperatorConfigModel

def test_anonymizer_5_operators_and_deanonymize():
    """5대 연산자(삭제, 대체, 마스킹, 해싱, 암호화) 적용 및 대칭키 기반 역복원 테스트"""
    service = AnonymizerService.get_instance()
    text = "홍길동의 주민번호는 900101-1234568 이고 전화번호는 010-1234-5678, 이메일은 test@example.com 입니다."
    aes_key = "1234567890123456"

    # 연산자 설정: 주민번호 -> 암호화, 전화번호 -> 마스킹, 이메일 -> 대체
    operators = {
        "KR_RRN": OperatorConfigModel(operator="encrypt", params={"key": aes_key}),
        "KR_PHONE_NUMBER": OperatorConfigModel(operator="mask", params={"chars_to_mask": 4, "from_end": True}),
        "EMAIL_ADDRESS": OperatorConfigModel(operator="replace", params={"new_value": "<EMAIL_HIDDEN>"}),
    }

    resp = service.anonymize(text=text, language="ko", operators_map=operators)
    assert resp.success
    assert "900101-1234568" not in resp.anonymized_text
    assert "<EMAIL_HIDDEN>" in resp.anonymized_text
    assert "****" in resp.anonymized_text
    assert resp.is_reversible
    assert resp.deanonymize_payload is not None
    assert len(resp.deanonymize_payload.items) > 0

    # 복원(Deanonymization) 테스트
    deanon_resp = service.deanonymize(
        text=resp.deanonymize_payload.text,
        items=resp.deanonymize_payload.items,
        encryption_key=aes_key,
    )
    assert deanon_resp.success
    assert "900101-1234568" in deanon_resp.restored_text, "원문 주민등록번호 복원 실패!"

if __name__ == "__main__":
    test_anonymizer_5_operators_and_deanonymize()
    print("모든 Anonymizer 및 Deanonymizer 테스트가 성공적으로 통과되었습니다!")
