from app.services.structured_service import StructuredService
from app.services.test_data_service import TestDataService
from app.schemas.anonymizer_schemas import OperatorConfigModel

def test_structured_analyze_and_anonymize():
    struct_service = StructuredService.get_instance()
    test_data_service = TestDataService.get_instance()

    records = test_data_service.sample_structured["records"]
    assert len(records) > 0

    # Step 1: Analyze columns
    analysis = struct_service.analyze_table(data=records, language="ko")
    assert analysis.success
    assert analysis.total_columns > 0

    # Step 2: Anonymize with encryption and masking
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

    # Step 3: Deanonymize table
    deanon_resp = struct_service.deanonymize_table(
        anonymized_data=anon_resp.anonymized_data,
        column_keys={"주민등록번호": aes_key},
    )
    assert deanon_resp.success
    assert deanon_resp.restored_data[0]["주민등록번호"] == records[0]["주민등록번호"]

if __name__ == "__main__":
    test_structured_analyze_and_anonymize()
    print("All Structured tests passed successfully!")
