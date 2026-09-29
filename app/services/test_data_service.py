import os
import io
import base64
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

logger = logging.getLogger(__name__)

ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_assets"))
os.makedirs(ASSETS_DIR, exist_ok=True)

class TestDataService:
    _instance: Optional = None

    def __init__(self):
        self.sample_texts = self._init_sample_texts()
        self.sample_structured = self._init_sample_structured()
        self._ensure_sample_image()
        self._ensure_sample_dicom()

    @classmethod
    def get_instance(cls) -> "TestDataService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_sample_texts(self) -> Dict[str, Dict[str, Any]]:
        return {
            "customer_inquiry": {
                "title": "고객 상담 문의 및 본인인증 텍스트",
                "description": "한국인 고객의 성명, 주민등록번호, 휴대전화번호, 일반전화번호, 이메일, 주소가 포함된 상담 내역",
                "text": (
                    "안녕하세요. VIP 회원 홍길동(1990년생)입니다. "
                    "본인 확인을 위해 주민등록번호 900101-1234568 를 기재합니다. "
                    "휴대폰 연락처는 010-1234-5678 이며, 자택 유선전화는 02-555-4321 입니다. "
                    "안내장은 이메일 hong.gildong@privacystack.kr 또는 "
                    "주소 서울특별시 서초구 반포대로 58 로 발송 부탁드립니다. "
                    "대표번호 1588-1234 로 상담 신청 완료했습니다."
                ),
            },
            "hr_employee": {
                "title": "인사 및 급여 계좌 등록 텍스트",
                "description": "다수의 직원 주민번호, 연락처, 사번 및 은행 계좌 정보가 포함된 인사 기록",
                "text": (
                    "[신규 입사자 정보 등록]\n"
                    "1. 이름: 김철수, 주민번호: 880512-1098765, 연락처: 010-8765-4321, 이메일: kim.cs@company.com\n"
                    "2. 이름: 이영희, 주민번호: 951123-2876543, 연락처: 010-2345-6789, 이메일: lee.yh@company.com\n"
                    "3. 이름: 박지민, 주민번호: 010715-3987654, 연락처: 010-3456-7890, 이메일: park.jm@company.com\n"
                    "문의사항은 인사팀 직통 031-789-1234 또는 고객센터 1577-9988 로 연락주세요."
                ),
            },
            "medical_consult": {
                "title": "병원 진료 및 처방 기록",
                "description": "환자 인적사항, 주민번호, 담당의, 병원 대표번호가 포함된 의료 기록",
                "text": (
                    "[서울대학교병원 진료의뢰서]\n"
                    "환자명: 강동원 (남, 42세)\n"
                    "주민등록번호: 820315-1123456\n"
                    "보호자 연락처: 010-5678-1234\n"
                    "환자 등록번호: P-2026-9901\n"
                    "진료과: 심장혈관내과, 주치의: 최진혁 교수 (직통: 02-2072-0114)\n"
                    "상기 환자는 2026년 9월 28일 내원하여 혈압약 처방 완료함."
                ),
            },
        }

    def _init_sample_structured(self) -> Dict[str, Any]:
        records = [
            {
                "고객ID": "CUST-001",
                "고객명": "홍길동",
                "주민등록번호": "900101-1234568",
                "연락처": "010-1234-5678",
                "이메일": "hong@example.com",
                "거주도시": "서울특별시 강남구",
                "신용등급": "A+",
            },
            {
                "고객ID": "CUST-002",
                "고객명": "이순신",
                "주민등록번호": "850515-1987654",
                "연락처": "02-987-6543",
                "이메일": "lee.sunshin@naval.mil.kr",
                "거주도시": "부산광역시 해운대구",
                "신용등급": "AAA",
            },
            {
                "고객ID": "CUST-003",
                "고객명": "신사임당",
                "주민등록번호": "921020-2098765",
                "연락처": "010-3333-7777",
                "이메일": "saimdang@art.or.kr",
                "거주도시": "강원특별자치도 강릉시",
                "신용등급": "A",
            },
            {
                "고객ID": "CUST-004",
                "고객명": "세종대왕",
                "주민등록번호": "790515-1002003",
                "연락처": "044-200-1111",
                "이메일": "king.sejong@hangul.go.kr",
                "거주도시": "세종특별자치시 한솔동",
                "신용등급": "AAA",
            },
            {
                "고객ID": "CUST-005",
                "고객명": "유관순",
                "주민등록번호": "020301-4191919",
                "연락처": "010-1919-0301",
                "이메일": "yoo.ks@patriot.org",
                "거주도시": "충청남도 천안시 동남구",
                "신용등급": "A+",
            },
        ]
        df = pd.DataFrame(records)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        return {
            "records": records,
            "csv_string": csv_buffer.getvalue(),
        }

    def _get_fonts(self):
        """정확한 OCR 텍스트 인식을 위한 시스템 폰트 로드"""
        font_bold = None
        font_reg = None
        for name in ["malgunbd.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]:
            try:
                font_bold = ImageFont.truetype(name, 20)
                break
            except Exception:
                continue
        for name in ["malgun.ttf", "arial.ttf", "DejaVuSans.ttf"]:
            try:
                font_reg = ImageFont.truetype(name, 18)
                break
            except Exception:
                continue
        return font_bold, font_reg

    def _ensure_sample_image(self) -> str:
        """한글 및 영문 PII 텍스트가 포함된 현실적인 신분증 서식 이미지 생성"""
        img_path = os.path.join(ASSETS_DIR, "sample_korean_id.png")
        if not os.path.exists(img_path):
            font_bold, font_reg = self._get_fonts()

            # 고해상도 및 선명한 흰색 배경으로 정확한 OCR 지원
            img = Image.new("RGB", (820, 500), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)

            # 카드 상단 헤더
            draw.rectangle([0, 0, 820, 70], fill=(30, 58, 95))
            draw.text((30, 22), "REPUBLIC OF KOREA - VERIFICATION CERTIFICATE", fill=(255, 255, 255), font=font_bold)

            # 증명사진 영역
            draw.rectangle([40, 110, 180, 310], fill=(240, 243, 246), outline=(160, 174, 192), width=2)
            draw.text((75, 195), "[ PHOTO ]", fill=(100, 116, 139), font=font_bold)

            # 세부 인적사항 텍스트
            draw.text((220, 115), "성명 (Name): 홍길동", fill=(0, 0, 0), font=font_bold)
            draw.text((220, 165), "주민등록번호 (RRN): 900101-1234568", fill=(0, 0, 0), font=font_bold)
            draw.text((220, 215), "연락처 (Phone): 010-1234-5678", fill=(0, 0, 0), font=font_bold)
            draw.text((220, 265), "이메일 (Email): hong.gildong@privacy.kr", fill=(0, 0, 0), font=font_bold)
            draw.text((220, 315), "주소 (Address): 서울특별시 강남구 테헤란로 123", fill=(0, 0, 0), font=font_bold)

            # 하단 보안선 및 안내 문구
            draw.line([30, 420, 790, 420], fill=(203, 213, 225), width=2)
            draw.text((40, 445), "ISSUED BY PRIVACY SECURITY CENTER  *  CONFIDENTIAL", fill=(100, 116, 139), font=font_reg)

            img.save(img_path, format="PNG")
            logger.info(f"합성 테스트 이미지 생성 완료: {img_path}")
        return img_path

    def _ensure_sample_dicom(self) -> str:
        """환자 메타데이터와 번인(Burned-in) 스캔 텍스트가 포함된 유효한 의료용 DICOM 파일 생성"""
        dcm_path = os.path.join(ASSETS_DIR, "sample_medical_scan.dcm")
        if not os.path.exists(dcm_path):
            font_bold, font_reg = self._get_fonts()

            file_meta = FileMetaDataset()
            file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
            file_meta.MediaStorageSOPInstanceUID = generate_uid()
            file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

            ds = FileDataset(dcm_path, {}, file_meta=file_meta, preamble=b"\0" * 128)
            ds.PatientName = "HONG^GILDONG"
            ds.PatientID = "P-900101-12345"
            ds.PatientBirthDate = "19900101"
            ds.PatientSex = "M"
            ds.PatientAge = "036Y"
            ds.ReferringPhysicianName = "DR^KIM^MINSOO"
            ds.InstitutionName = "SEOUL MEDICAL IMAGING CENTER"
            ds.StudyDate = "20260929"
            ds.Modality = "OT"
            ds.Rows = 400
            ds.Columns = 400
            ds.BitsAllocated = 8
            ds.BitsStored = 8
            ds.HighBit = 7
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = "MONOCHROME2"
            ds.PixelRepresentation = 0

            # 번인(Burned-in) 텍스트 주석이 포함된 픽셀 슬라이스 생성
            img = Image.new("L", (400, 400), color=20)
            draw = ImageDraw.Draw(img)

            # 선명한 폰트로 인쇄된 환자 개인정보 텍스트
            draw.text((20, 20), "PATIENT: HONG GILDONG", fill=255, font=font_bold)
            draw.text((20, 50), "RRN: 900101-1234568", fill=255, font=font_bold)
            draw.text((20, 80), "TEL: 010-1234-5678", fill=255, font=font_bold)
            draw.text((20, 110), "DATE: 2026-09-29  MOD: CT", fill=255, font=font_reg)

            # 모의 의료 영상 해부학적 구조선
            draw.ellipse([100, 150, 300, 350], outline=170, width=4)
            draw.ellipse([140, 190, 260, 310], outline=120, width=2)
            draw.point([(200, 250)], fill=240)

            ds.PixelData = img.tobytes()
            ds.save_as(dcm_path)
            logger.info(f"합성 테스트 DICOM 파일 생성 완료: {dcm_path}")
        return dcm_path

    def get_sample_image_base64(self) -> str:
        img_path = self._ensure_sample_image()
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    def get_sample_dicom_bytes(self) -> bytes:
        dcm_path = self._ensure_sample_dicom()
        with open(dcm_path, "rb") as f:
            return f.read()

    def get_sample_dicom_path(self) -> str:
        return self._ensure_sample_dicom()

    def get_sample_image_path(self) -> str:
        return self._ensure_sample_image()
