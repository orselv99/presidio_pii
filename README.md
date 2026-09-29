# Microsoft Presidio Enterprise PII De-identification Platform

FastAPI 기반의 **차세대 개인정보 비식별화 및 복원 엔터프라이즈 솔루션**입니다.  
비정형 텍스트, 이미지(OCR), 의료용 DICOM 영상, 정형 테이블(CSV/DataFrame/RDBMS)에 이르는 전방위 PII(개인식별정보) 탐지 및 가역적/비가역적 비식별화 파이프라인을 제공합니다.

---

## 📁 파일 구조 (Project File Structure)

```
d:\.repo\.private0\noname00\
├── .dockerignore                     # Docker 빌드 제외 패턴
├── .gitignore                        # Git 버전 관리 제외 패턴
├── DESIGN.md                         # Swiss Technical Editorial Rationalism 디자인 시스템 가이드
├── Dockerfile                        # Tesseract OCR & Spacy 다국어 모델 포함 컨테이너 이미지 빌드 명세
├── docker-compose.yml                # 원클릭 컨테이너 오케스트레이션 구성
├── README.md                         # 프로젝트 기술 문서 및 파일 구조 설명서
├── requirements.txt                  # Python 종속성 패키지 명세
├── run.py                            # FastAPI 로컬 개발 서버 구동 엔트리포인트
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI 메인 애플리케이션 및 라우터 엔드포인트
│   ├── schemas/                      # Pydantic v2 요청/응답 데이터 모델
│   │   ├── __init__.py
│   │   ├── analyzer_schemas.py       # PII 탐지 요청/응답 스키마
│   │   ├── anonymizer_schemas.py     # 5대 연산자 비식별화 및 역복원 스키마
│   │   ├── image_schemas.py          # 이미지/DICOM 마스킹 스키마
│   │   └── structured_schemas.py     # 정형 테이블 컬럼 탐지/익명화/복원 스키마
│   ├── services/                     # 코어 비즈니스 로직 및 Presidio 엔진 래퍼
│   │   ├── __init__.py
│   │   ├── analyzer_service.py       # Presidio Analyzer (공식 한국어 사전정의 인식기 + Spacy ko/en)
│   │   ├── anonymizer_service.py     # 5대 연산자(삭제, 대체, 마스킹, 해싱, AES 암호화) & Deanonymizer
│   │   ├── image_redactor_service.py # 이미지/DICOM OCR 추출 및 블랙아웃/블러 시각적 가림 처리
│   │   ├── kr_phone_recognizer.py    # 한국 전화번호 맞춤 인식기 (010, 02, 지역번호, 1588 등)
│   │   ├── structured_service.py     # CSV/DataFrame 정형 데이터 컬럼 분석 및 비식별화/복원
│   │   └── test_data_service.py      # 안전한 합성 텍스트, 이미지, DICOM, CSV 테스트 데이터 생성기
│   ├── static/                       # Swiss Technical 테마 웹 대시보드 정적 에셋
│   │   ├── index.html                # 반응형 웹 대시보드 마스터 템플릿
│   │   ├── css/
│   │   │   └── style.css             # Editorial Rationalism 스타일시트 (0px radius, hairline grid)
│   │   └── js/
│   │       └── app.js                # 인터랙티브 대시보드 클라이언트 로직
│   └── test_assets/                  # 생성된 합성 테스트 에셋 (.png, .dcm)
├── tessdata/                         # Tesseract OCR 한국어(kor), 영어(eng), OSD 모델 바이너리
└── tests/                            # 모듈별 단위 및 종단간 검증 테스트 스위트
    ├── test_analyzer.py              # Analyzer 인식기 테스트
    ├── test_anonymizer.py            # Anonymizer 5대 연산자 및 Deanonymizer 복원 테스트
    ├── test_image_redactor.py        # 이미지 및 의료 DICOM 마스킹 테스트
    └── test_structured.py            # 정형 테이블 컬럼 분석 및 역복원 테스트
```

---

## 🚀 주요 기능

### 1. Presidio Analyzer (한국 개인정보 인식기 특화)
- **공식 사전정의 인식기 (Predefined Recognizers) 연동**:
  - `KrRrnRecognizer`: 주민등록번호 (`KR_RRN`)
  - `KrBrnRecognizer`: 사업자등록번호 (`KR_BRN`)
  - `KrDriverLicenseRecognizer`: 운전면허번호 (`KR_DRIVER_LICENSE`)
  - `KrFrnRecognizer`: 외국인등록번호 (`KR_FRN`)
  - `KrPassportRecognizer`: 여권번호 (`KR_PASSPORT`)
- **한국 전화번호 인식기 (`KR_PHONE_NUMBER`) 탑재 (`app/services/kr_phone_recognizer.py`)**:
  - 휴대전화(`010`, `011`, `016~019`).
  - 서울 유선(`02`) 및 전국 지역번호(`031~064`).
  - 대표번호/고객센터(`1588`, `1577`, `1544`, `1566`, `1600` 등).
  - 인터넷전화(`070`), 수신자부담(`080`), 평생번호(`050x`).
  - 국제전화 접두사(`+82`, `82`).

### 2. Presidio Anonymizer & Deanonymizer (5대 연산자 및 역복원 파이프라인)
- **지원 연산자 (총 5종)**:
  1. **삭제 (Redact)**: 탐지된 개인정보를 원문에서 완전 제거.
  2. **대체 (Replace)**: `<KR_RRN>`, `<고객명>` 등 지정 라벨로 치환.
  3. **마스킹 (Mask)**: `*` 등 문자로 마스킹 (글자 수, 시작/끝 방향 지정).
  4. **해싱 (Hash)**: SHA256 / SHA512 / MD5 암호화 해싱 (Salt 지원).
  5. **대칭키 암호화 (Encrypt)**: AES-128 / AES-256 대칭키 기반 가역적 암호화.
- **원문 복원 (Deanonymizer)**:
  - 비식별화 API(`POST /api/anonymize`) 호출 시 암호화된 엔티티의 위치, 연산자, 대칭키 정보가 담긴 `deanonymize_payload` 제공.
  - 복원 API(`POST /api/deanonymize`)에 해당 페이로드를 전달하면 **100% 무손실로 원문 텍스트가 복원**됩니다.

### 3. Presidio Image Redactor (일반 이미지 및 의료용 DICOM)
- **Tesseract OCR 연동**: 한국어 + 영어 (`kor+eng`) 광학 문자 인식.
- **시각적 마스킹 처리 2종**:
  - **검은 박스 블랙아웃 (Blackout)**: 솔리드 박스 채우기.
  - **가우시안 흐림 (Blur)**: 개인정보 Bounding Box 좌표 영역에 부드러운 가우시안 블러 적용.
- **의료용 DICOM (.dcm) 지원**:
  - 픽셀 데이터(Pixel Data) 내 인쇄(Burned-in)된 환자명, 환자ID, 생년월일 영역 검출 및 가림 처리.
  - DICOM 메타데이터 기반 `phi_list` 추출 및 `ko`/`en` 양방향 거부 목록(Deny-List) 자동 등록.
  - 의료 표준 라벨(`PATIENT:`, `RRN:`, `TEL:`, `DATE:`, `MOD: CT` 등)에 대한 허용 목록(Allow-List) 적용으로 라벨 오탐 방지 및 원문 보존.
  - 배경색 동기화(`fill="background"`)로 스캔 픽셀과 이질감 없는 자연스러운 블랙아웃 마스킹 제공.
  - DICOM 헤더 메타데이터 태그(`PatientName`, `PatientID`, `PatientBirthDate` 등) 비식별화.
  - 처리 전/후 픽셀 슬라이스 미리보기 및 마스킹된 `.dcm` 바이너리 다운로드.

### 4. Presidio Structured (정형/반정형 테이블 데이터)
- CSV, Pandas DataFrame, RDBMS 테이블 레코드 지원.
- 컬럼 단위 PII 자동 판별 및 신뢰도 점수 산출.
- 컬럼별 독립적인 비식별화 연산자(마스킹, 대체, 암호화 등) 적용.
- 암호화된 컬럼에 대한 원문 역복원(Deanonymize) 파이프라인 지원.

### 5. Test Data Hub (테스트 데이터 팩토리)
- 각 기능별 검증용 데이터셋 생성 및 API 제공:
  - 한국어 비정형 텍스트 (고객상담, 인사급여, 병원진료).
  - OCR 테스트용 합성 한국 신분증 PNG 이미지.
  - 실제 규격 의료용 합성 DICOM (`sample_medical_scan.dcm`) 파일.
  - 고객 정보 정형 테이블 데이터셋 (JSON/CSV).

---

## 🛠️ 실행 방법

### 로컬 환경에서 실행
```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 서버 실행 (포트 8000)
python run.py
```

### Docker 환경에서 실행
```bash
# Docker Compose 빌드 및 백그라운드 실행
docker compose up --build -d

# 로그 확인
docker compose logs -f
```

브라우저에서 접속:
- **인터랙티브 웹 대시보드**: [http://localhost:8000](http://localhost:8000)
- **Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 테스트 실행

```bash
$env:PYTHONPATH = "."
python tests/test_analyzer.py
python tests/test_anonymizer.py
python tests/test_image_redactor.py
python tests/test_structured.py
```