---
name: Editorial Rationalism (Swiss Technical)
modes: [light, dark]

# 시맨틱 컬러 토큰: 라이트와 다크 모드 1:1 매핑
colors:
  light:
    surface-canvas: '#efece6'      # 배경 (웜 페이퍼)
    surface-card: '#f6f5f1'        # 모듈/카드 기본 면
    surface-subtle: '#e8e5de'      # 헤더 띠, 호버, 2차 박스
    surface-muted: '#ddd9d0'       # 인셋 패널, 비활성 면
    surface-inverse: '#1c1d22'     # 반전 버튼/배지
    border-strong: '#2d3139'       # 1px 외곽 구조선, 메인 분할선
    border-subtle: '#d0ccc2'       # 내부 셀 구분선
    text-primary: '#1c1d22'        # 본문/타이틀 (차콜 블랙)
    text-secondary: '#4b5160'      # 보조 메타데이터
    text-muted: '#757c8d'          # 비활성/플레이스홀더
    text-inverse: '#f6f5f1'        # 반전 요소 내부 텍스트
    accent-spec: '#c45a72'         # 런타임/디버그/강조 인디케이터
  dark:
    surface-canvas: '#121316'      # 배경 (딥 매트 차콜)
    surface-card: '#1a1b20'        # 모듈/카드 기본 면
    surface-subtle: '#202227'      # 호버/강조 영역
    surface-muted: '#26282f'       # 인셋 패널, 모달
    surface-inverse: '#e2e4e9'     # 반전 버튼/배지
    border-strong: '#3a3d47'       # 1px 외곽 구조선, 포커스선
    border-subtle: '#26282f'       # 내부 행 구분선
    text-primary: '#ededed'        # 본문/타이틀 (소프트 오프화이트)
    text-secondary: '#9b9ea8'      # 보조 메타데이터
    text-muted: '#636672'          # 비활성/플레이스홀더
    text-inverse: '#121316'        # 반전 요소 내부 텍스트
    accent-spec: '#c45a72'         # 런타임/디버그/강조 인디케이터

typography:
  display-hero:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 52px
    letterSpacing: -0.03em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 38px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  label-mono:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.06em
  label-mono-xs:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.08em

spacing:
  gutter: 1px                      # 선 맞춤 기준 거터
  margin: 1.5rem
  margin-mobile: 1rem
  space-xs: 0.25rem                # 4px
  space-sm: 0.5rem                 # 8px
  space-md: 1rem                   # 16px
  space-lg: 1.5rem                 # 24px
  space-xl: 2.5rem                 # 40px
---

## System Guidelines

### 1. Visual Language & Orthogonality
- **Zero Border-Radius:** 모든 버튼, 인풋, 패널, 모달의 곡률은 예외 없이 `0px`를 유지합니다.
- **Hairline Grid Architecture:** 여백(Gap) 대신 인접 면들이 맞닿는 `1px solid` 보더(`border-strong` / `border-subtle`)를 교차시켜 테크니컬 브루탈리즘 그리드를 형성합니다.
- **Planar Depth:** 그림자(Drop-shadow) 및 블러(Blur)는 사용하지 않습니다. 깊이감은 베이스(`surface-canvas`) 위에 카드(`surface-card`), 호버 상태(`surface-subtle`)의 평면 명도 차이로만 부여합니다.

### 2. Typographic Rules
- **Display & Headings:** `Inter` 서체를 적용하고, Swiss Modernism 스타일의 밀도감을 위해 `-0.01em ~ -0.03em`의 좁은 자간(Tight tracking)을 유지합니다.
- **Technical Mono:** `JetBrains Mono`는 메타데이터, 섹션 인덱스(`SEC_01 //`), 타임스탬프, 수치 표시에 사용하며 대문자 표기 및 `+0.06em ~ +0.08em`의 넓은 자간을 적용합니다.

### 3. Unified Component Behaviors (Theme-Agnostic)
- **Primary Button:** `surface-inverse` 배경에 `text-inverse` 텍스트. 클릭/호버 시 순간적인 명도 반전 또는 내부 1px 인셋 테두리 적용.
- **Secondary / Outline Button:** `surface-card` 배경에 `border-strong` 외곽선, `text-primary` 텍스트. 호버 시 `surface-subtle`로 면 전환.
- **Checkboxes & Radios:** 14px × 14px의 완전한 정사각형(0px radius). 선택 시 `surface-inverse`로 채워지며 내부에 6px 크기의 사각 핍(Pip) 노출.
- **Cards & Data Tables:** 상단 헤더 스트립은 `surface-subtle`로 본문과 1px 라인 분할. 데이터 행 호버 시 `surface-subtle`로 라인 전체 하이라이트.