from app.services.anonymizer_service import AnonymizerService
from app.schemas.anonymizer_schemas import OperatorConfigModel

def test_anonymizer_5_operators_and_deanonymize():
    service = AnonymizerService.get_instance()
    text = "홍길동의 주민번호는 900101-1234568 이고 전화번호는 010-1234-5678, 이메일은 test@example.com 입니다."
    aes_key = "1234567890123456"

    # Operators: KR_RRN -> encrypt, KR_PHONE_NUMBER -> mask, EMAIL_ADDRESS -> replace
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

    # Test Deanonymization (restoration)
    deanon_resp = service.deanonymize(
        text=resp.deanonymize_payload.text,
        items=resp.deanonymize_payload.items,
        encryption_key=aes_key,
    )
    assert deanon_resp.success
    assert "900101-1234568" in deanon_resp.restored_text, "Failed to restore original RRN!"

if __name__ == "__main__":
    test_anonymizer_5_operators_and_deanonymize()
    print("All Anonymizer and Deanonymizer tests passed successfully!")
