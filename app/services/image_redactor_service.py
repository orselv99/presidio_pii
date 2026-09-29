import os
import io
import re
import base64
import logging
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import cv2

# Tesseract OCR 설정 확인 및 환경 변수 등록
TESSDATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tessdata"))
if os.path.exists(TESSDATA_DIR):
    os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR

TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
import pytesseract
if os.path.exists(TESSERACT_EXE):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE

import pydicom
from pydicom.dataset import FileDataset
from presidio_analyzer import PatternRecognizer
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
        logger.info("ImageRedactorService가 한글 OCR 및 의료용 DICOM 지원과 함께 초기화되었습니다.")

    @classmethod
    def get_instance(cls) -> "ImageRedactorService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _decode_base64_image(self, b64_str: str) -> Image.Image:
        """base64 인코딩 문자열(data URI 접두사 포함)을 PIL Image 객체로 디코딩합니다."""
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        img_bytes = base64.b64decode(b64_str)
        return Image.open(io.BytesIO(img_bytes)).convert("RGB")

    def _encode_image_to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """PIL Image 객체를 base64 data URI 문자열로 인코딩합니다."""
        buf = io.BytesIO()
        image.save(buf, format=format)
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/{format.lower()};base64,{encoded}"

    def redact_image(
        self,
        image_input: Any,  # PIL Image, bytes, 또는 base64 str
        redaction_type: str = "blackout",  # "blackout" 또는 "blur"
        fill_color: Tuple[int, int, int] = (0, 0, 0),
        blur_radius: int = 15,
        language: str = "kor+eng",
        entities: Optional[List[str]] = None,
        score_threshold: Optional[float] = 0.4,
    ) -> Tuple[Image.Image, List[BoundingBoxItem], str]:
        """
        이미지에서 다각도(정방향 및 90도 회전) 및 고대비(Otsu 이진화) 전처리 OCR 텍스트를 추출하고,
        한국어/영어 PII(여권 번호, MRZ, 주민번호, 운전면허번호, 성명, 주소 등) 바운딩 박스를 정밀 검출하여 가림 처리를 적용합니다.
        """
        if isinstance(image_input, str):
            image = self._decode_base64_image(image_input)
        elif isinstance(image_input, bytes):
            image = Image.open(io.BytesIO(image_input)).convert("RGB")
        elif isinstance(image_input, Image.Image):
            image = image_input.convert("RGB")
        else:
            raise ValueError("지원하지 않는 이미지 입력 포맷입니다.")

        w_orig, h_orig = image.size
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
                "PASSPORT",
                "ORGANIZATION",
                "DATE_TIME",
            ]

        raw_boxes: List[Tuple[int, int, int, int, str, float]] = []
        langs_to_check = ["ko", "en"] if ("kor" in language.lower() or "ko" in language.lower()) else [language]

        # 1차 패스: 원본 정방향 이미지에 대해 이중 언어(ko, en) Presidio 분석
        for l in langs_to_check:
            ocr_lang = "kor+eng" if l == "ko" else "eng"
            try:
                res = self.image_analyzer.analyze(
                    image=image,
                    ocr_kwargs={"lang": ocr_lang},
                    language=l,
                    entities=entities,
                    score_threshold=threshold,
                )
                for r in res:
                    if r.score is not None and r.score < threshold:
                        continue
                    raw_boxes.append((int(r.left), int(r.top), int(r.width), int(r.height), r.entity_type, r.score))
            except Exception as e:
                logger.warning(f"정방향 이미지 {l} 언어 분석 중 예외 발생: {e}")

        # 2차 패스: 여권 등 워터마크/문양 배경의 인식률 향상을 위한 Otsu 이진화 전처리 분석
        try:
            np_img = np.array(image)
            gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            otsu_pil = Image.fromarray(otsu)

            for l in langs_to_check:
                ocr_lang = "kor+eng" if l == "ko" else "eng"
                res_otsu = self.image_analyzer.analyze(
                    image=otsu_pil,
                    ocr_kwargs={"lang": ocr_lang},
                    language=l,
                    entities=entities,
                    score_threshold=threshold,
                )
                for r in res_otsu:
                    if r.score is not None and r.score < threshold:
                        continue
                    raw_boxes.append((int(r.left), int(r.top), int(r.width), int(r.height), r.entity_type, r.score))
        except Exception as e:
            logger.warning(f"Otsu 전처리 이미지 분석 중 예외 발생: {e}")

        # 3차 패스: 모바일 스크린샷 내 90도 회전된 신분증 카드(운전면허증 등) 검출을 위한 90도 회전 분석 및 좌표 역변환
        try:
            rot90_pil = image.rotate(90, expand=True)
            for l in langs_to_check:
                ocr_lang = "kor+eng" if l == "ko" else "eng"
                res_rot = self.image_analyzer.analyze(
                    image=rot90_pil,
                    ocr_kwargs={"lang": ocr_lang},
                    language=l,
                    entities=entities,
                    score_threshold=threshold,
                )
                for r in res_rot:
                    if r.score is not None and r.score < threshold:
                        continue
                    # 90도 반시계방향 회전 역변환 공식 적용:
                    # x_orig = W_orig - (y_rot + h_rot)
                    # y_orig = x_rot
                    x_orig = w_orig - (int(r.top) + int(r.height))
                    y_orig = int(r.left)
                    w_box = int(r.height)
                    h_box = int(r.width)
                    raw_boxes.append((x_orig, y_orig, w_box, h_box, r.entity_type, r.score))
        except Exception as e:
            logger.warning(f"회전 이미지 분석 중 예외 발생: {e}")

        # 4차 패스: 문서 서식 레이아웃 기반 도메인 특화 보호 규칙 적용
        # A. 여권 MRZ(기계판독영역) 대역 완벽 보호:
        # 하단 35% 영역(y > 0.65 * H)에서 PASSPORT 또는 MRZ 엔티티 발견 시 하단 MRZ 전체 대역 커버
        mrz_candidates = [b for b in raw_boxes if b[4] in ["PASSPORT", "KR_PASSPORT"] and b[1] > 0.65 * h_orig]
        if mrz_candidates:
            min_top = min(b[1] for b in mrz_candidates)
            start_y = min(min_top - 10, int(0.72 * h_orig))
            start_y = max(int(0.65 * h_orig), start_y)
            raw_boxes.append((
                int(0.02 * w_orig),
                start_y,
                int(0.96 * w_orig),
                int(h_orig - start_y - 4),
                "PASSPORT_MRZ",
                0.99
            ))

        # B. 한국 운전면허증 카드 레이아웃 보호:
        # 면허번호와 주민등록번호 사이에 위치하는 운전면허 명의인 성명 영역 자동 보호
        dl_boxes = [b for b in raw_boxes if b[4] == "KR_DRIVER_LICENSE"]
        rrn_boxes = [b for b in raw_boxes if b[4] in ["KR_RRN", "DATE_TIME"] and b[2] < 120 and b[3] > 250]
        if dl_boxes and rrn_boxes:
            dl_b = dl_boxes[0]
            rrn_b = rrn_boxes[0]
            name_x1 = min(dl_b[0], rrn_b[0]) + min(dl_b[2], rrn_b[2])
            name_x2 = max(dl_b[0], rrn_b[0])
            name_y1 = min(dl_b[1], rrn_b[1])
            name_h = max(dl_b[3], rrn_b[3])
            raw_boxes.append((
                int(name_x1 - 10),
                int(name_y1),
                int(abs(name_x2 - name_x1) + 20),
                int(name_h),
                "PERSON",
                0.95
            ))

        # 바운딩 박스 정제, 화면 범위 초과 및 극단적 크기 노이즈 필터링
        filtered_boxes: List[Tuple[int, int, int, int, str, float]] = []
        for b in raw_boxes:
            x, y, w, h, ent_type, score = b
            if w < 8 or h < 8:
                continue
            if w > 0.98 * w_orig and h > 0.98 * h_orig:
                continue
            x = max(0, min(w_orig - 1, x))
            y = max(0, min(h_orig - 1, y))
            w = min(w_orig - x, w)
            h = min(h_orig - y, h)
            filtered_boxes.append((x, y, w, h, ent_type, score))

        # 인접/중복 박스 병합 처리
        merged_boxes: List[Tuple[int, int, int, int, str, float]] = []
        seen = [False] * len(filtered_boxes)

        for i in range(len(filtered_boxes)):
            if seen[i]:
                continue
            x1, y1, w1, h1, e1, s1 = filtered_boxes[i]
            r1, b1 = x1 + w1, y1 + h1

            for j in range(i + 1, len(filtered_boxes)):
                if seen[j]:
                    continue
                x2, y2, w2, h2, e2, s2 = filtered_boxes[j]
                r2, b2 = x2 + w2, y2 + h2

                # 포함 관계 검사
                if x1 <= x2 and y1 <= y2 and r1 >= r2 and b1 >= b2:
                    seen[j] = True
                    continue
                if x2 <= x1 and y2 <= y1 and r2 >= r1 and b2 >= b1:
                    x1, y1, r1, b1 = x2, y2, r2, b2
                    w1, h1 = r1 - x1, b1 - y1
                    e1 = e2
                    s1 = max(s1 or 0, s2 or 0)
                    seen[j] = True
                    continue

                # 동일 라인 상 인접 단어 박스 병합
                horiz_overlap = max(0, min(r1, r2) - max(x1, x2))
                vert_overlap = max(0, min(b1, b2) - max(y1, y2))

                is_adjacent_h = (vert_overlap > min(h1, h2) * 0.5) and (abs(x2 - r1) < 20 or abs(x1 - r2) < 20)
                is_adjacent_v = (horiz_overlap > min(w1, w2) * 0.5) and (abs(y2 - b1) < 20 or abs(y1 - b2) < 20)

                if is_adjacent_h or is_adjacent_v:
                    x1 = min(x1, x2)
                    y1 = min(y1, y2)
                    r1 = max(r1, r2)
                    b1 = max(b1, b2)
                    w1, h1 = r1 - x1, b1 - y1
                    s1 = max(s1 or 0, s2 or 0)
                    seen[j] = True

            merged_boxes.append((x1, y1, w1, h1, e1, s1))
            seen[i] = True

        bboxes: List[BoundingBoxItem] = []
        for mb in merged_boxes:
            bboxes.append(
                BoundingBoxItem(
                    left=mb[0],
                    top=mb[1],
                    width=mb[2],
                    height=mb[3],
                    entity_type=mb[4],
                    score=round(mb[5], 4) if mb[5] is not None else None,
                )
            )

        redacted_image = image.copy()
        draw = ImageDraw.Draw(redacted_image)

        # 텍스트 주변 잔여 글자 노출을 완전히 방지하기 위한 안전 여백 패딩 적용
        pad_x = 5
        pad_y = 4

        for box in bboxes:
            x1 = max(0, box.left - pad_x)
            y1 = max(0, box.top - pad_y)
            x2 = min(w_orig, box.left + box.width + pad_x)
            y2 = min(h_orig, box.top + box.height + pad_y)

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
        """DICOM 픽셀 데이터를 미리보기용 8비트 RGB PIL Image로 변환합니다."""
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
        fill: str = "background",
        language: str = "kor+eng",
    ) -> Tuple[bytes, List[BoundingBoxItem], List[str], str, str]:
        """
        의료용 DICOM 파일의 번인(Burned-in) 텍스트 픽셀과 민감한 헤더 메타데이터 태그를 가림 처리합니다.
        """
        ds_orig = pydicom.dcmread(io.BytesIO(dicom_bytes))
        orig_preview = self._dicom_to_preview_image(ds_orig)
        orig_preview_b64 = self._encode_image_to_base64(orig_preview)

        # DICOM 메타데이터에서 PHI 목록을 추출하여 한국어/영어 양방향 인식기 등록
        meta, is_name, is_pat = self.dicom_redactor._get_text_metadata(ds_orig)
        phi_list = self.dicom_redactor._make_phi_list(meta, is_name, is_pat)
        ko_deny = PatternRecognizer(supported_entity="PERSON", deny_list=phi_list, supported_language="ko")
        en_deny = PatternRecognizer(supported_entity="PERSON", deny_list=phi_list, supported_language="en")

        # 표준 의료 영상 태그 라벨 오인식을 방지하기 위한 허용 목록(Allow List)
        allow_list = [
            "PATIENT", "Patient", "patient", "RRN", "TEL", "Tel", "DATE", "Date",
            "MOD", "Mod", "CT", "MR", "XR", "NAME", "SEX", "AGE", "DOB",
            "환자", "성명", "주민등록번호", "연락처", "전화", "HOSPITAL", "CENTER"
        ]

        ocr_kwargs = {"lang": language}
        ds_redacted, bboxes_dict_list = self.dicom_redactor.redact_and_return_bbox(
            image=ds_orig,
            fill=fill,
            ocr_kwargs=ocr_kwargs,
            ad_hoc_recognizers=[ko_deny, en_deny],
            language="ko",
            allow_list=allow_list,
        )

        # 바운딩 박스 중복 제거 및 구체적 엔티티 타입 우선 매핑
        bboxes: List[BoundingBoxItem] = []
        seen_boxes: Dict[Tuple[int, int, int, int], BoundingBoxItem] = {}

        for b in bboxes_dict_list:
            box_key = (int(b.get("left", 0)), int(b.get("top", 0)), int(b.get("width", 0)), int(b.get("height", 0)))
            ent_type = b.get("entity_type", "PII")

            if box_key in seen_boxes:
                existing = seen_boxes[box_key]
                if existing.entity_type in ["PERSON", "DATE_TIME"] and ent_type not in ["PERSON", "DATE_TIME"]:
                    existing.entity_type = ent_type
                continue

            item = BoundingBoxItem(
                left=box_key[0],
                top=box_key[1],
                width=box_key[2],
                height=box_key[3],
                entity_type=ent_type,
            )
            seen_boxes[box_key] = item
            bboxes.append(item)

        # DICOM 헤더 메타데이터 태그 비식별화
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

        # 블러 또는 블랙아웃 시각화 처리
        if redaction_type.lower() == "blur":
            redacted_preview = orig_preview.copy()
            for b in bboxes:
                x1, y1 = max(0, b.left - 4), max(0, b.top - 3)
                x2, y2 = min(redacted_preview.width, b.left + b.width + 4), min(redacted_preview.height, b.top + b.height + 3)
                if x2 > x1 and y2 > y1:
                    crop_box = (x1, y1, x2, y2)
                    cropped = redacted_preview.crop(crop_box)
                    blurred_crop = cropped.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                    redacted_preview.paste(blurred_crop, crop_box)

            # 8비트 그레이스케일 단일 슬라이스인 경우 픽셀 데이터에도 블러 반영
            if ds_redacted.BitsAllocated == 8 and len(ds_redacted.pixel_array.shape) == 2:
                ds_redacted.PixelData = np.array(redacted_preview.convert("L")).tobytes()
        else:
            redacted_preview = self._dicom_to_preview_image(ds_redacted)

        redacted_preview_b64 = self._encode_image_to_base64(redacted_preview)

        out_buf = io.BytesIO()
        ds_redacted.save_as(out_buf)
        redacted_dicom_bytes = out_buf.getvalue()

        return redacted_dicom_bytes, bboxes, redacted_tags, orig_preview_b64, redacted_preview_b64
