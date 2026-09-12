# AI 기반 지식자산·교육·컨설팅 플랫폼 기획서

> 버전: v0.1  
> 목적: 지금까지 논의한 아이디어와 설계 원칙을 하나의 기준 문서로 정리하고, 이후 GitHub 기반 실행 프로젝트의 출발점으로 사용한다.

---

## 1. 프로젝트 한 줄 정의

이 프로젝트는 단순한 강의교안 저장소가 아니라,

> **개인의 지식·강의·컨설팅·연구·콘텐츠를 하나의 원본 지식체계로 관리하고, AI를 이용해 지속적으로 업데이트하며, 웹사이트·강의·퀴즈·책·제안서·영상 콘텐츠로 재구성하는 지식 운영 시스템**이다.

GitHub는 이 시스템의 **Source of Truth(원본 저장소)** 역할을 하고,  
웹사이트는 외부에 보여주는 **브랜딩 및 학습 인터페이스**,  
AI Harness는 내부의 **정리·추천·업데이트·콘텐츠 생성 엔진** 역할을 한다.

---

# 2. 프로젝트의 최종 그림

```text
Voice / Notes / Files / Research / Cases
                │
                ▼
             Inbox
                │
                ▼
        AI 정리·분류·추천
                │
                ▼
      Human Review & Approval
                │
                ▼
      Master Knowledge System
                │
      ┌─────────┼─────────┐
      ▼         ▼         ▼
   Learning   Consulting  Research
      │         │         │
      └─────────┼─────────┘
                ▼
         Content Studio
                │
      ┌─────────┼─────────┬─────────┐
      ▼         ▼         ▼         ▼
   Website    Lecture    Book     YouTube
      │         │         │         │
      └─────────┼─────────┴─────────┘
                ▼
         Public Brand Platform
```

---

# 3. 핵심 원칙

## 3.1 지식은 하나, 활용 방식은 여러 개

ODA 교재, 커머스 교재, 기술사업화 교재를 각각 별도로 만드는 방식은 지양한다.

대신 하나의 **Master Knowledge Base**를 만들고,  
필요한 상황마다 관련 지식 모듈을 조합해 강의·컨설팅·콘텐츠를 구성한다.

예:

```text
M001 문제 정의
M002 고객 정의
M003 고객 문제 검증
M004 가치제안
M005 비즈니스모델
M006 수익모델
M007 가격전략
M008 원가구조
M009 시장분석
M010 경쟁분석
...
M100 해외진출 전략
```

각 모듈은 독립적으로 관리한다.

---

## 3.2 분야는 별도 교재가 아니라 Domain Lens로 관리

현재 핵심 활동 분야는 다음 네 영역이다.

- Local
- Technology Startup / Technology Commercialization
- Commerce
- ODA / Global Entry

향후 추가될 수 있는 분야:

- Policy & Regulation
- Emerging Market Investment Regulation
- ODA Regulation
- Startup Internationalization Regulation

이 분야들은 별도 교재 폴더가 아니라,  
공통 지식을 해석하는 **Domain Lens**로 관리한다.

예:

```text
M002 고객 정의
├── Startup Lens
├── Commerce Lens
├── ODA Lens
├── Technology Commercialization Lens
└── Policy & Regulation Lens
```

---

# 4. 현재 강의·지식 주제

지금까지 강의·연구·컨설팅에서 반복적으로 다뤄온 핵심 주제는 다음과 같다.

## 4.1 핵심 주제

- 비즈니스모델
- 수익모델
- 사업계획서
- 가격관리
- 가격전략
- 원가관리
- 시장분석
- 고객분석
- 경쟁분석
- 기술사업화
- 창업
- 커머스
- ODA
- 해외진출

---

# 5. 지식 모듈 구조

각 지식 모듈은 가능한 한 같은 구조를 유지한다.

예:

```yaml
id: M007
title: 가격전략

domains:
  - startup
  - commerce
  - oda
  - technology-commercialization

topics:
  - pricing
  - revenue-model
  - unit-economics

level:
  - beginner
  - intermediate

content_type:
  - theory
  - framework
  - case
  - exercise
```

각 모듈 내부는 다음 구조를 기본으로 한다.

```text
1. 개념
2. 왜 중요한가
3. 핵심 프레임워크
4. 적용 프로세스
5. 체크리스트
6. 사례
7. 실습
8. 컨설팅 활용법
9. 관련 지식 모듈
10. 퀴즈
```

---

# 6. 강의는 Playlist 방식으로 구성

강의 자체를 독립적인 원본 교재로 관리하지 않는다.

강의는 Master Knowledge에서 필요한 모듈을 선택해 구성하는 **Learning Path / Playlist**로 관리한다.

예:

## 스타트업 비즈니스모델 3시간

```text
M001 문제정의
M002 고객정의
M003 고객검증
M004 가치제안
M005 비즈니스모델
M006 수익모델
```

## ODA 사업모델 6시간

```text
M001 문제정의
M002 고객·수혜자·구매자
M004 가치제안
M005 비즈니스모델
M006 수익모델
M023 이해관계자 분석
M031 지속가능성
M042 PDM
```

## 커머스 가격전략 4시간

```text
M002 고객
M006 수익모델
M007 가격전략
M008 원가
M021 채널
M027 CAC
M028 재구매율
M029 재고회전
```

---

# 7. 컨설팅 구조

교육과 컨설팅을 분리하지 않고 동일한 지식 원본을 사용한다.

컨설팅 영역에서는 각 지식 모듈을 다음 형태로 확장한다.

```text
Consulting
├── Process
├── Methodology
├── Framework
├── Diagnostic Checklist
├── Interview Guide
├── Workshop Guide
├── Proposal Template
├── Output Template
└── Case Study
```

즉,

> 지식 → 방법론 → 진단 → 워크숍 → 산출물 → 사례

의 흐름을 만든다.

---

# 8. 교육 시스템

웹사이트 방문자는 무료 학습 콘텐츠를 이용할 수 있다.

기본 학습 흐름은 다음과 같다.

```text
학습 등록
   ↓
교재 학습
   ↓
실습
   ↓
퀴즈
   ↓
점수 확인
   ↓
보너스 콘텐츠
```

보너스 콘텐츠 예:

- 전자책
- 템플릿
- 심화 교안
- 강의자료
- 체크리스트
- 무료 미니 강의

---

# 9. Quiz 시스템

Quiz는 게임 자체가 목적이 아니라  
**학습 확인과 재학습 유도**를 위한 장치로 사용한다.

초기에는 단순하게 시작한다.

- 객관식
- O/X
- 빈칸 채우기
- 개념 매칭

향후 확장:

- 사례형 문제
- 의사결정 시뮬레이션
- 컨설팅 케이스
- AI 대화형 퀴즈
- 레벨 시스템
- 점수 및 배지

예:

```text
Chapter
   ↓
AI 핵심개념 추출
   ↓
Quiz 생성
   ↓
Human Review
   ↓
웹 Quiz
```

---

# 10. Lead Generation

학습 시스템은 개인 브랜딩과 잠재 고객 관리에도 활용한다.

단, 일반적인 회원가입보다 **학습 등록** 개념을 사용한다.

수집 가능한 기본 정보:

- 이름
- 이메일
- 소속
- 직무
- 관심 분야
- 학습 목적

관심 분야 예:

- Startup
- Commerce
- ODA
- Global Entry
- Technology Commercialization
- Pricing

개인정보 수집 목적과 마케팅 수신 동의는 분리한다.

---

# 11. GitHub와 웹사이트

GitHub는 내부적으로 지식의 원본을 관리한다.

웹사이트는 외부에서 이를 보여주는 브랜드 플랫폼이다.

```text
GitHub
= Knowledge Source

Website
= Public Interface
```

웹사이트에서는 단순한 자기소개보다

> “나는 어떤 문제를 어떤 방법론으로 해결하는가”

를 보여주는 것이 핵심이다.

---

# 12. 다국어 전략

초기 언어:

- 한국어
- 영어

향후 확장 가능 언어:

- 일본어
- 스페인어
- 프랑스어
- 기타

원칙:

```text
Korean = Master Content
English = First Translation
Other Languages = Localized Versions
```

한국어를 원본으로 유지하고,  
영문은 가능한 한 자동화하되 최종 검수를 거친다.

---

# 13. AI 업데이트 시스템

이 플랫폼의 핵심은 **정적 교재가 아니라 계속 진화하는 교재**다.

AI가 수행할 수 있는 역할:

- 최신 논문 탐색
- 신규 사례 탐색
- 산업 변화 탐색
- 신규 정책 탐색
- 기존 콘텐츠와 연결
- 업데이트 후보 제안
- 퀴즈 생성
- 번역
- 요약
- 사례화
- 강의안 재구성

중요한 원칙:

> AI는 자동 반영하지 않는다.

기본 Workflow:

```text
Research
   ↓
AI 분석
   ↓
Update Proposal
   ↓
Human Review
   ↓
Approve / Reject
   ↓
GitHub Update
```

즉,

> AI Suggestion + Human Approval

구조를 유지한다.

---

# 14. Voice Inbox

새로운 아이디어나 학습 내용을 즉시 저장할 수 있어야 한다.

사용 흐름:

```text
Voice Input
   ↓
Speech to Text
   ↓
AI Summary
   ↓
Knowledge Classification
   ↓
Related Module Recommendation
   ↓
Human Review
   ↓
Knowledge Base Update
```

예:

음성 입력:

> “오늘 컨설팅을 해보니 초기 스타트업 가격 문제는 가격 자체보다 고객 세그먼트가 제대로 나뉘지 않은 것이 더 큰 문제였다.”

AI 추천:

```text
관련 모듈
- M002 고객 세분화
- M007 가격전략

Domain
- Startup
- Commerce

Content Type
- Consulting Insight

추천
- M007 Consulting Insight 추가
```

---

# 15. Content Studio

외부에 공개하기 전 개인적으로 사용하는 비공개 콘텐츠 작업 공간을 둔다.

Content Studio에서 만드는 산출물:

- 블로그
- 뉴스레터
- YouTube Script
- Shorts
- SNS
- 전자책
- 강의자료
- 제안서
- 보고서
- Case Study
- 연구노트
- 강의 슬라이드

구조:

```text
Knowledge Hub
      ↓
Content Studio
      ↓
Draft
      ↓
Review
      ↓
Publish
```

---

# 16. 연구 및 박사과정 확장

장기적으로 다음 연구 분야를 포함할 수 있도록 구조를 열어둔다.

- 스타트업 해외진출 규제
- 개도국 투자유치 규제
- ODA 관련 법제
- 국제개발협력 정책
- Emerging Market Regulation
- Startup Internationalization Regulation

현재는 외부에 공개하지 않는다.

내부 구조만 준비한다.

예:

```text
Research
└── Policy & Regulation
    ├── Private Notes
    ├── Research Questions
    ├── Papers
    ├── Cases
    └── Future Publication
```

향후 연구가 충분히 축적되고 공개가 적절한 시점에  
Knowledge Hub와 Website에 연결한다.

---

# 17. 공개 영역과 비공개 영역 분리

이 프로젝트의 핵심 IP 보호 원칙이다.

## Public Layer

외부 공개 가능:

- 교재
- 일부 템플릿
- 강의 콘텐츠
- 웹사이트
- 사례 일부
- Quiz
- 공개 자료
- 다운로드 자료

## Private Engine Layer

비공개:

- AGENTS
- SKILL
- Harness
- Workflow
- Prompt Library
- 자동화 규칙
- AI Orchestration
- Content Studio
- 연구노트
- 미공개 아이디어
- 업데이트 엔진
- 내부 평가 기준
- 생성 Pipeline

원칙:

> 공개 저장소에는 결과물을 공개하고, 핵심 생성 엔진과 운영 로직은 비공개로 유지한다.

---

# 18. 개인 계정과 회사 계정

이 시스템은 장기적인 개인 지식자산, 강의, 연구, 책, 컨설팅, 브랜딩과 연결된다.

따라서 원본은 개인 계정에서 관리하는 것을 기본으로 한다.

회사 계정은 다음 용도로 제한할 수 있다.

- 회사 프로젝트
- 회사 협업
- 회사용 결과물
- 조직 내부 문서

개인 Knowledge System의 원본은 회사 퇴사 여부와 관계없이 유지되어야 한다.

---

# 19. 콘텐츠 상태관리

모든 지식과 콘텐츠는 상태값을 가진다.

```text
IDEA
  ↓
DRAFT
  ↓
REVIEW
  ↓
APPROVED
  ↓
PUBLISHED
```

또는 필요 시:

```text
PRIVATE
RESEARCH
ARCHIVED
```

상태 관리를 통해 비공개 연구와 공개 콘텐츠를 명확하게 구분한다.

---

# 20. GitHub 기본 구조 초안

```text
knowledge-platform/
│
├── README.md
│
├── docs/
│
│   ├── knowledge/
│   ├── methodology/
│   ├── consulting/
│   ├── learning/
│   └── cases/
│
├── knowledge/
│   ├── M001-problem-definition/
│   ├── M002-customer-definition/
│   ├── M003-customer-validation/
│   └── ...
│
├── domains/
│   ├── startup/
│   ├── technology-commercialization/
│   ├── commerce/
│   ├── oda-global-entry/
│   └── policy-regulation/
│
├── learning-paths/
│   ├── startup-bm/
│   ├── oda-business-model/
│   └── commerce-pricing/
│
├── consulting/
│   ├── process/
│   ├── frameworks/
│   ├── checklists/
│   ├── interview-guides/
│   └── workshop-guides/
│
├── quizzes/
│
├── templates/
│
├── examples/
│
├── resources/
│
└── public/
```

실제 운영에서는 Public Repository와 Private Repository를 분리하는 것이 바람직하다.

---

# 21. Public / Private Repository 구조

## Public Repository

```text
knowledge-public/
```

포함:

- 공개 교재
- 공개 사례
- Quiz
- Web
- 일부 Template
- Learning Path

## Private Repository

```text
knowledge-engine/
```

포함:

- Harness
- Agents
- Skills
- Prompt
- Automation
- Content Studio
- Research
- Internal Framework
- Voice Inbox
- Update Pipeline

---

# 22. 시스템 전체 아키텍처

```text
                     PRIVATE

 Voice / Notes / Research / Files
                │
                ▼
             INBOX
                │
                ▼
          AI PROCESSING
                │
                ▼
        REVIEW / APPROVAL
                │
                ▼
        MASTER KNOWLEDGE
                │
       ┌────────┼────────┐
       ▼        ▼        ▼
    DOMAIN   CONSULTING  RESEARCH
       │        │        │
       └────────┼────────┘
                ▼
         CONTENT STUDIO
                │
                ▼
           PUBLISHING
                │
────────────────────────────────────
                     PUBLIC
                │
       ┌────────┼────────┬─────────┐
       ▼        ▼        ▼         ▼
   Website   Course    Quiz      Ebook
       │
       ├── Korean
       └── English
```

---

# 23. 참고한 GitHub 구조

이번 기획 과정에서 다음 저장소를 참고했다.

## AI Harness 교재 구조 참고

https://github.com/5throck/intro-to-ai-harness.git

참고 요소:

- README 중심 진입
- Chapter 기반 교재 구조
- GitHub 기반 공개
- 온라인 핸드북 방식

## TeachMe 자동 교재 생성 구조 참고

https://github.com/beret21/teachme.git

참고 방향:

- 입력 자료를 학습 콘텐츠로 재구성
- 교재 생성 자동화
- Quiz 등 학습 요소 연계

단, 최종 시스템은 해당 Repository를 그대로 복제하는 것이 아니라  
개인의 지식자산·컨설팅·연구·브랜딩까지 통합하는 형태로 확장한다.

---

# 24. 핵심 아키텍처 결정

현재까지 가장 중요한 결정은 다음과 같다.

> **분야별 교재를 여러 개 만드는 것이 아니라 하나의 Master Knowledge Base를 만들고, Domain Lens와 Learning Path를 통해 필요한 콘텐츠를 조합한다.**

이를 통해:

- 콘텐츠 중복 감소
- 업데이트 용이
- AI 자동화 용이
- 강의 재구성 용이
- 컨설팅 활용 용이
- 다국어 확장 용이
- 신규 연구 분야 확장 용이

라는 장점을 얻는다.

---

# 25. 다음 실행 단계

## Phase 1. 기존 자산 수집

가장 먼저 기존 Startup Master Note를 중심으로 모든 지식자산을 수집한다.

대상:

- 강의교안
- PPT
- PDF
- Word
- Markdown
- 컨설팅 자료
- 책 원고
- 사례
- 체크리스트
- Framework
- 영상 원고
- 음성 메모

---

## Phase 2. Knowledge Module 분해

Startup Master Note를 50~150개 정도의 독립적인 Knowledge Module로 분해한다.

예:

```text
M001 문제 정의
M002 고객 정의
M003 고객 세분화
M004 고객 문제 검증
M005 가치제안
...
```

---

## Phase 3. Metadata

각 Module에 다음 Metadata를 부여한다.

- Domain
- Topic
- Level
- Content Type
- Status
- Related Module

---

## Phase 4. GitHub 구축

- Private Knowledge Engine
- Public Knowledge Repository
- Website Repository

구조를 구축한다.

---

## Phase 5. Website

초기 웹사이트:

```text
Home
About
Knowledge
Courses
Consulting
Cases
Quiz
Resources
Contact
```

언어:

```text
한국어 | English
```

---

## Phase 6. AI Automation

AI가 다음 작업을 지원하도록 한다.

- 음성 Inbox
- 자동 분류
- Module 추천
- Update Proposal
- 번역
- Quiz 생성
- 콘텐츠 재가공
- 최신 논문/사례 추천

---

# 26. 최종 목표

이 시스템의 최종 목표는 다음과 같다.

> **개인의 경험과 지식이 사라지지 않고 하나의 구조 안에 축적되며, AI의 도움을 받아 계속 발전하고, 필요할 때마다 강의·컨설팅·책·연구·웹·영상·Quiz로 즉시 변환되는 개인 지식 운영체제를 구축한다.**

이 시스템은 단순한 GitHub Repository가 아니다.

```text
Knowledge Base
+
Consulting System
+
Learning Platform
+
Content Studio
+
Research Repository
+
Brand Website
+
AI Harness
```

를 결합한 장기 지식자산 플랫폼이다.
