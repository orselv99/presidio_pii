from app.services.image_redactor_service import ImageRedactorService
from app.services.test_data_service import TestDataService

def test_image_redactor_blackout_and_blur():
    img_service = ImageRedactorService.get_instance()
    test_data_service = TestDataService.get_instance()

    img_b64 = test_data_service.get_sample_image_base64()

    # Test blackout
    redacted_img, bboxes, data_uri = img_service.redact_image(
        image_input=img_b64,
        redaction_type="blackout",
    )
    assert len(bboxes) > 0, "No bounding boxes detected in test image"
    assert data_uri.startswith("data:image/png;base64,")

    # Test blur
    redacted_img_blur, bboxes_blur, data_uri_blur = img_service.redact_image(
        image_input=img_b64,
        redaction_type="blur",
        blur_radius=15,
    )
    assert len(bboxes_blur) > 0

def test_dicom_redactor():
    img_service = ImageRedactorService.get_instance()
    test_data_service = TestDataService.get_instance()

    dcm_bytes = test_data_service.get_sample_dicom_bytes()
    redacted_bytes, bboxes, redacted_tags, orig_preview, redacted_preview = img_service.redact_dicom(
        dicom_bytes=dcm_bytes,
        redaction_type="blackout",
        redact_metadata=True,
    )
    assert len(redacted_bytes) > 0
    assert len(redacted_tags) > 0, "No DICOM tags were redacted"
    assert "PatientName" in redacted_tags
    assert orig_preview.startswith("data:image/png;base64,")
    assert redacted_preview.startswith("data:image/png;base64,")

if __name__ == "__main__":
    test_image_redactor_blackout_and_blur()
    test_dicom_redactor()
    print("All Image and DICOM Redactor tests passed successfully!")
