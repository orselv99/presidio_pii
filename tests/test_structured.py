from app.services.structured_service import StructuredService
from app.services.test_data_service import TestDataService
from app.schemas.anonymizer_schemas import OperatorConfigModel

def test_structured_analyze_and_anonymize():
    """정형 데이터 컬럼 분석, 비식별화 및 대칭키 복원 테스트"""
    struct_service = StructuredService.get_instance()
    test_data_service = TestDataService.get_instance()

    records = test_data_service.sample_structured["records"]
    assert len(records) > 0

    # 1단계: 컬럼 분석
    analysis = struct_service.analyze_table(data=records, language="ko")
    assert analysis.success
    assert analysis.total_columns > 0

    # 2단계: 암호화 및 마스킹 적용 비식별화
    aes_key = "1234567890123456"
    col_ops = {
        "주민등록번호": OperatorConfigModel(operator="encrypt", params={"key": aes_key}),
        "연락처": OperatorConfigModel(operator="mask", params={"chars_to_mask": 4, "from_end": True}),
        "고객명": OperatorConfigModel(operator="replace", params={"new_value": "<고객명>"}),
    }
    anon_resp = struct_service.anonymize_table(data=records, column_operators=col_ops)
    assert anon_resp.success
    assert len(anon_resp.anonymized_data) == len(records)
    assert anon_resp.csv_string is not None

    # 3단계: 테이블 복원(Deanonymization)
    deanon_resp = struct_service.deanonymize_table(
        anonymized_data=anon_resp.anonymized_data,
        column_keys={"주민등록번호": aes_key},
    )
    assert deanon_resp.success
    assert deanon_resp.restored_data[0]["주민등록번호"] == records[0]["주민등록번호"]

if __name__ == "__main__":
    test_structured_analyze_and_anonymize()
    print("모든 Structured 테스트가 성공적으로 통과되었습니다!")
