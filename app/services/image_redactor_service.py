import os
import io
import re
import base64
import logging
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image, ImageDraw, ImageFilter
import numpy as np

# Ensure Tesseract OCR configuration
TESSDATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tessdata"))
if os.path.exists(TESSDATA_DIR):
    os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR

TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
import pytesseract
if os.path.exists(TESSERACT_EXE):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE

import pydicom
from pydicom.dataset import FileDataset
from presidio_image_redactor import (
    ImageRedactorEngine,
    ImageAnalyzerEngine,
    DicomImageRedactorEngine,
)

from app.services.analyzer_service import AnalyzerService
from app.schemas.image_schemas import BoundingBoxItem, ImageRedactResponse, DicomRedactResponse

logger = logging.getLogger(__name__)

class ImageRedactorService:
    _instance: Optional["ImageRedactorService"] = None

    def __init__(self, analyzer_service: Optional[AnalyzerService] = None):
        self.analyzer_service = analyzer_service or AnalyzerService.get_instance()
        self.image_analyzer = ImageAnalyzerEngine(analyzer_engine=self.analyzer_service.engine)
        self.image_redactor = ImageRedactorEngine(image_analyzer_engine=self.image_analyzer)
        self.dicom_redactor = DicomImageRedactorEngine(image_analyzer_engine=self.image_analyzer)
        logger.info("ImageRedactorService initialized with Korean OCR & DICOM support.")

    @classmethod
    def get_instance(cls) -> "ImageRedactorService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _decode_base64_image(self, b64_str: str) -> Image.Image:
        """Decodes a base64 string (including data URI prefix) into a PIL Image."""
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        img_bytes = base64.b64decode(b64_str)
        return Image.open(io.BytesIO(img_bytes)).convert("RGB")

    def _encode_image_to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """Encodes a PIL Image into a base64 data URI string."""
        buf = io.BytesIO()
        image.save(buf, format=format)
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/{format.lower()};base64,{encoded}"

    def redact_image(
        self,
        image_input: Any,  # PIL Image, bytes, or base64 str
        redaction_type: str = "blackout",  # "blackout" or "blur"
        fill_color: Tuple[int, int, int] = (0, 0, 0),
        blur_radius: int = 15,
        language: str = "kor+eng",
        entities: Optional[List[str]] = None,
        score_threshold: Optional[float] = 0.4,
    ) -> Tuple[Image.Image, List[BoundingBoxItem], str]:
        """
        Extracts OCR text, identifies PII bounding boxes, and applies blackout or blur.
        """
        if isinstance(image_input, str):
            image = self._decode_base64_image(image_input)
        elif isinstance(image_input, bytes):
            image = Image.open(io.BytesIO(image_input)).convert("RGB")
        elif isinstance(image_input, Image.Image):
            image = image_input.convert("RGB")
        else:
            raise ValueError("Unsupported image input format.")

        ocr_lang = "kor+eng" if "kor" in language.lower() or "ko" in language.lower() else language
        ocr_kwargs = {"lang": ocr_lang}

        threshold = score_threshold if score_threshold is not None else 0.4

        if entities is None:
            entities = [
                "KR_RRN",
                "KR_PHONE_NUMBER",
                "EMAIL_ADDRESS",
                "PERSON",
                "LOCATION",
                "KR_BRN",
                "KR_DRIVER_LICENSE",
                "KR_PASSPORT",
            ]

        # Text Analyzer in Presidio expects ISO language code 'ko' or 'en'
        # By passing language='ko', Presidio checks Korean recognizers (KR_RRN, KR_PHONE) and global recognizers
        ocr_results = self.image_analyzer.analyze(
            image=image,
            ocr_kwargs=ocr_kwargs,
            language="ko",
            entities=entities,
            score_threshold=threshold,
        )

        bboxes: List[BoundingBoxItem] = []
        seen_boxes = set()

        for res in ocr_results:
            # Filter low-confidence false positives
            if res.score is not None and res.score < threshold:
                continue

            box_key = (int(res.left), int(res.top), int(res.width), int(res.height))
            if box_key in seen_boxes:
                continue
            seen_boxes.add(box_key)

            bboxes.append(
                BoundingBoxItem(
                    left=int(res.left),
                    top=int(res.top),
                    width=int(res.width),
                    height=int(res.height),
                    entity_type=res.entity_type,
                    score=round(res.score, 4) if res.score is not None else None,
                    text=res.text if hasattr(res, "text") else None,
                )
            )

        redacted_image = image.copy()
        draw = ImageDraw.Draw(redacted_image)

        # Apply padding to ensure complete visual coverage
        pad_x = 4
        pad_y = 3

        for box in bboxes:
            x1 = max(0, box.left - pad_x)
            y1 = max(0, box.top - pad_y)
            x2 = min(image.width, box.left + box.width + pad_x)
            y2 = min(image.height, box.top + box.height + pad_y)

            if x2 <= x1 or y2 <= y1:
                continue

            if redaction_type.lower() == "blur":
                crop_box = (x1, y1, x2, y2)
                cropped = redacted_image.crop(crop_box)
                blurred_crop = cropped.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                redacted_image.paste(blurred_crop, crop_box)
            else:
                color_tuple = tuple(fill_color) if isinstance(fill_color, list) else fill_color
                draw.rectangle([x1, y1, x2, y2], fill=color_tuple)

        data_uri = self._encode_image_to_base64(redacted_image, format="PNG")
        return redacted_image, bboxes, data_uri

    def _dicom_to_preview_image(self, ds: FileDataset) -> Image.Image:
        """Converts DICOM pixel data to an 8-bit RGB PIL Image for preview."""
        pixel_array = ds.pixel_array
        if pixel_array.dtype != np.uint8:
            norm = pixel_array.astype(float)
            norm = (norm - norm.min()) / (norm.max() - norm.min() + 1e-8) * 255.0
            pixel_array = norm.astype(np.uint8)

        if len(pixel_array.shape) == 2:
            img = Image.fromarray(pixel_array).convert("RGB")
        else:
            img = Image.fromarray(pixel_array).convert("RGB")
        return img

    def redact_dicom(
        self,
        dicom_bytes: bytes,
        redaction_type: str = "blackout",
        blur_radius: int = 15,
        redact_metadata: bool = True,
        fill: str = "contrast",
        language: str = "kor+eng",
    ) -> Tuple[bytes, List[BoundingBoxItem], List[str], str, str]:
        """
        Redacts both burned-in pixel text and sensitive header metadata tags in DICOM files.
        """
        ds_orig = pydicom.dcmread(io.BytesIO(dicom_bytes))
        orig_preview = self._dicom_to_preview_image(ds_orig)
        orig_preview_b64 = self._encode_image_to_base64(orig_preview)

        ocr_kwargs = {"lang": language}
        ds_redacted, bboxes_dict_list = self.dicom_redactor.redact_and_return_bbox(
            image=ds_orig,
            fill=fill,
            ocr_kwargs=ocr_kwargs,
            language="ko",
        )

        bboxes: List[BoundingBoxItem] = []
        for b in bboxes_dict_list:
            bboxes.append(
                BoundingBoxItem(
                    left=int(b.get("left", 0)),
                    top=int(b.get("top", 0)),
                    width=int(b.get("width", 0)),
                    height=int(b.get("height", 0)),
                    entity_type=b.get("entity_type", "PII"),
                )
            )

        redacted_tags = []
        if redact_metadata:
            tags_to_anonymize = [
                ("PatientName", "ANONYMIZED^PATIENT"),
                ("PatientID", "ANON-ID-001"),
                ("PatientBirthDate", "19000101"),
                ("PatientSex", "O"),
                ("PatientAge", "000Y"),
                ("PatientAddress", "REDACTED_ADDRESS"),
                ("OtherPatientIDs", "REDACTED"),
                ("ReferringPhysicianName", "REDACTED^PHYSICIAN"),
                ("InstitutionName", "ANONYMIZED_HOSPITAL"),
                ("StudyDate", "20000101"),
                ("AccessionNumber", "ACC-000000"),
            ]

            for tag_name, anon_val in tags_to_anonymize:
                if hasattr(ds_redacted, tag_name) and getattr(ds_redacted, tag_name):
                    setattr(ds_redacted, tag_name, anon_val)
                    redacted_tags.append(tag_name)

        redacted_preview = self._dicom_to_preview_image(ds_redacted)

        if redaction_type.lower() == "blur":
            for b in bboxes:
                x1, y1 = max(0, b.left - 4), max(0, b.top - 3)
                x2, y2 = min(redacted_preview.width, b.left + b.width + 4), min(redacted_preview.height, b.top + b.height + 3)
                if x2 > x1 and y2 > y1:
                    crop_box = (x1, y1, x2, y2)
                    cropped = redacted_preview.crop(crop_box)
                    blurred_crop = cropped.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                    redacted_preview.paste(blurred_crop, crop_box)

        redacted_preview_b64 = self._encode_image_to_base64(redacted_preview)

        out_buf = io.BytesIO()
        ds_redacted.save_as(out_buf)
        redacted_dicom_bytes = out_buf.getvalue()

        return redacted_dicom_bytes, bboxes, redacted_tags, orig_preview_b64, redacted_preview_b64
