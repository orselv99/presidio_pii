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

if __name__ == "__main__":
    test_image_redactor_blackout_and_blur()
    test_dicom_redactor()
    print("모든 Image 및 DICOM Redactor 테스트가 성공적으로 통과되었습니다!")
