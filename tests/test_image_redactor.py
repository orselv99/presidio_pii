from app.services.image_redactor_service import ImageRedactorService
from app.services.test_data_service import TestDataService

def test_image_redactor_blackout_and_blur():
    """일반 신분증 서식 이미지 블랙아웃 및 블러 마스킹 테스트"""
    img_service = ImageRedactorService.get_instance()
    test_data_service = TestDataService.get_instance()

    img_b64 = test_data_service.get_sample_image_base64()

    # 블랙아웃 테스트
    redacted_img, bboxes, data_uri = img_service.redact_image(
        image_input=img_b64,
        redaction_type="blackout",
    )
    assert len(bboxes) > 0, "테스트 이미지에서 바운딩 박스가 검출되지 않았습니다."
    assert data_uri.startswith("data:image/png;base64,")

    # 블러 테스트
    redacted_img_blur, bboxes_blur, data_uri_blur = img_service.redact_image(
        image_input=img_b64,
        redaction_type="blur",
        blur_radius=15,
    )
    assert len(bboxes_blur) > 0

def test_dicom_redactor():
    """의료용 DICOM (.dcm) 파일 번인 텍스트 및 헤더 태그 가림 처리 테스트"""
    img_service = ImageRedactorService.get_instance()
    test_data_service = TestDataService.get_instance()

    dcm_bytes = test_data_service.get_sample_dicom_bytes()
    redacted_bytes, bboxes, redacted_tags, orig_preview, redacted_preview = img_service.redact_dicom(
        dicom_bytes=dcm_bytes,
        redaction_type="blackout",
        redact_metadata=True,
    )
    assert len(redacted_bytes) > 0
    assert len(redacted_tags) > 0, "가림 처리된 DICOM 태그가 없습니다."
    assert "PatientName" in redacted_tags
    assert orig_preview.startswith("data:image/png;base64,")
    assert redacted_preview.startswith("data:image/png;base64,")

def test_foreigner_passport_redaction():
    """외국인 여권 서식 이미지(sample_foreigner_passport.jpg) 여권번호, 성명, MRZ 가림 처리 테스트"""
    import os
    from PIL import Image

    img_service = ImageRedactorService.get_instance()
    passport_path = os.path.join(os.path.dirname(__file__), "..", "app", "test_assets", "sample_foreigner_passport.jpg")
    if os.path.exists(passport_path):
        img = Image.open(passport_path)
        redacted_img, bboxes, data_uri = img_service.redact_image(
            image_input=img,
            redaction_type="blackout",
            language="kor+eng",
        )
        assert len(bboxes) >= 3, f"외국인 여권에서 충분한 PII 바운딩 박스가 검출되지 않았습니다: {len(bboxes)}"
        has_passport_or_mrz = any(b.entity_type in ["PASSPORT", "PASSPORT_MRZ", "KR_PASSPORT"] for b in bboxes)
        assert has_passport_or_mrz, "여권 번호 또는 MRZ 기계판독영역이 검출되지 않았습니다."
        assert data_uri.startswith("data:image/png;base64,")

def test_korean_driverid_redaction():
    """한국 모바일 운전면허증 이미지(sample_korean_driverid.png) 면허번호, 주민번호, 성명, 주소 가림 처리 테스트"""
    import os
    from PIL import Image

    img_service = ImageRedactorService.get_instance()
    driverid_path = os.path.join(os.path.dirname(__file__), "..", "app", "test_assets", "sample_korean_driverid.png")
    if os.path.exists(driverid_path):
        img = Image.open(driverid_path)
        redacted_img, bboxes, data_uri = img_service.redact_image(
            image_input=img,
            redaction_type="blackout",
            language="kor+eng",
        )
        assert len(bboxes) >= 3, f"한국 운전면허증에서 충분한 PII 바운딩 박스가 검출되지 않았습니다: {len(bboxes)}"
        has_driver_license = any(b.entity_type == "KR_DRIVER_LICENSE" for b in bboxes)
        assert has_driver_license, "운전면허번호가 검출되지 않았습니다."
        assert data_uri.startswith("data:image/png;base64,")

if __name__ == "__main__":
    test_image_redactor_blackout_and_blur()
    test_dicom_redactor()
    test_foreigner_passport_redaction()
    test_korean_driverid_redaction()
    print("모든 Image 및 DICOM Redactor 테스트가 성공적으로 통과되었습니다!")
