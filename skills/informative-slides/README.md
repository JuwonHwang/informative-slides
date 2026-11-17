# informative-slides 스킬

발표자 없이 읽어도 이해되는 자료를 두 단계로 만든다. 먼저 내용의 순서와 설명을 정한 문서(마크다운)를 쓰고, 그 문서를 단일 HTML 슬라이드로 그린다. 절차는 `SKILL.md`, 규칙은 플러그인 최상위의 `rules/document.md`(문서)와 `rules/slides.md`(슬라이드)에 있다.

- 절차 A: 원자료나 지금 대화에서 문서와 덱을 만든다. 파일은 프로젝트 루트의 `.informative-slides/`에 두고, 이 폴더는 git 추적에서 뺀다.
- 절차 B: 문서 하나를 덱으로 그린다. `meet`과 `wrapup`도 이 절차를 쓴다.

## 구성

```
informative-slides/
├── SKILL.md                      # 절차 A, 절차 B, 저장 위치, 전달
├── assets/template.html          # 슬라이드 골격(장 없음): CSS와 스크립트. 그림·확대도, 그래프 부품(막대·선·점), 강조 상자, 단계와 움직임, 선택지 패널, 절 구분 장, 화면 비율, 인쇄, 넘침 확인
├── assets/layouts/               # 장 배치 10개의 예(표지, 프로젝트 소개, 요약, 전체 처리 과정, 방법 설명, 표, 절 구분, 확대, 선택지, 마무리). 배치마다 파일 하나, 목록은 index.md
├── assets/elements/              # 디자인 요소 20개의 예. 요소마다 파일 하나(장 하나와 그 장의 그림 원본), 목록은 index.md
├── assets/design/                # 디자인 카탈로그(catalog.json: 요소 20개, 성질, 선택된 값)
├── assets/vendor/                # MathJax 3.2.2 (TeX 수식 렌더러)와 라이선스
├── scripts/design.py             # 디자인 카탈로그의 값을 템플릿 CSS의 design:begin 블록에 쓴다(apply)
├── scripts/project_identity.py   # 프로젝트 루트와 저장 폴더, 표지 정보(프로젝트 이름·한 줄 설명·색, 발표자·소속)
├── scripts/embed_math.py         # 수식이 있는 덱에 MathJax를 넣는다
└── scripts/check_deck.py         # 제목·메시지·분량·출처·약어·기호 검사, 렌더링한 넘침·그림 검사
```

## 덱 사용

- 브라우저로 연다. `→`·`Space`는 다음 단계나 다음 장, `←`는 이전이다.
- 오른쪽 아래 장 번호를 누르거나 `G`를 누르면 장 목록(번호와 제목)이 열린다. 숫자를 치고 `Enter`를 누르면 그 장으로 간다.
- 화면 비율은 덱의 `<html data-ratio="16:9">`에서 정한다.
- 검수와 PDF: 덱을 만드는 스킬은 검수 화면을 열지 않는다. 사용자가 요청하면 `slide-review` 스킬이 검수 화면을 연다. 요소를 클릭해 의견을 달고, 비율과 크기를 바꿔 보고, `HTML 저장`과 `PDF 저장`(글꼴 포함, 단계마다 한 쪽)을 한다.
- 브라우저 인쇄(`Cmd/Ctrl+P`)도 장·단계마다 한 쪽으로 나오지만, Safari는 쪽 크기 지정을 무시해 장이 잘린다.
