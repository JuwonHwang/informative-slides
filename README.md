# informative-slides

발표자 없이 읽어도 이해되는 자료를 만드는 Claude Code 플러그인이다. 자료는 두 단계로 만든다. 먼저 내용의 순서와 설명을 정한 문서(마크다운)를 쓰고, 그 문서를 단일 HTML 슬라이드로 그린다. 연구 프로젝트를 목표에 맞춰 진행하는 스킬(goal, meet, wrapup)도 같은 규칙으로 자료를 만든다. 이 저장소는 [drive-project-forward](https://github.com/JuwonHwang/drive-project-forward)를 합친 것이다.

## 스킬

| 스킬 | 하는 일 | 만드는 파일 |
|---|---|---|
| [`informative-slides`](skills/informative-slides/) | 노트, 설계 문서, 실험 결과, 논문, 지금 대화에서 논의한 내용으로 문서와 덱을 만든다(절차 A). 다른 스킬이 쓴 문서를 덱으로 그리는 절차(절차 B)도 맡는다 | `.informative-slides/<주제>.md`·`.html` (git 추적 안 함) |
| [`slide-review`](skills/slide-review/) | 덱을 검수 화면에 띄워 요소를 클릭해 의견을 받고, 의견을 파일로 남긴다. 비율·크기를 바꿔 보고, HTML과 PDF(글꼴 포함, 단계마다 한 쪽)를 저장한다 | 덱 옆 `<덱>-feedback.md`·`.json` |
| [`goal`](skills/goal/) | 사용자에게 물어 연구의 배경, 목표, 달성 기준, 일정을 정한다. 연구를 시작할 때 한 번 쓴다 | `GOAL.md` |
| [`meet`](skills/meet/) | 미팅 전: 방법이 어떻게 동작하고 결과가 왜 그렇게 나왔는지 설명하는 문서와 덱. 미팅 뒤: 결정, 할 일, 미룬 질문을 미팅 노트에 쓰고, 사용자가 목표 자체를 바꿨을 때만 `GOAL.md`를 고친다 | `meetings/YYYY-MM-DD-slides.md`·`.html`, `meetings/YYYY-MM-DD-note.md` |
| [`wrapup`](skills/wrapup/) | 프로젝트 밖의 사람에게 보일 발표 문서와 덱. 듣는 사람, 발표 길이, 목적을 먼저 묻는다 | `wrapup/YYYY-MM-DD-<듣는 사람>.md`·`.html` |

## 규칙

모든 스킬이 플러그인 최상위의 규칙 파일 두 개를 함께 쓴다.

| 규칙 | 정하는 것 |
|---|---|
| [`rules/document.md`](rules/document.md) | 문서: 장의 순서와 장마다 질문·메시지·요소, 목적에서 필요한 것으로 내려가는 순서, 처리 과정 전체를 먼저 따라가기, 배경 개념은 쓰기 바로 앞에서, 개념은 보이는 것→규칙→수식→계산, 문제는 여러 장에 걸쳐, 선택지는 그림으로, 모든 주장에 근거, 값을 얻는 방법, 이름과 용어, 언어 하나 |
| [`rules/slides.md`](rules/slides.md) | 슬라이드: 장 하나의 형식, 분량, 의미 단위 줄바꿈, 논문 그림 수준의 그림, 요소별 표현(구조도, 전체 처리 과정, 부분 확대, 방법 단계, 개념, 수식, 수치 표, 전후 비교, 선택지, 문제 단계, 기능 현황 표), 단계와 움직임, 색, 템플릿 구성 요소, 확인 |

디자인 요소의 생김새는 디자인 카탈로그(`skills/informative-slides/assets/design/`)에 정해 두었고, 덱을 만드는 에이전트는 생김새 값을 장에 쓰지 않는다. 그래프는 그래프 부품(막대, 선, 점)에 데이터만 쓴다. 생김새를 바꾸려면 카탈로그의 값을 고치고 `python3 skills/informative-slides/scripts/design.py apply`로 템플릿에 반영한다. 슬라이드 규칙은 덱의 구성을 정하지 않는다. 장의 순서와 연결은 문서가 정하고, 슬라이드는 문서의 요소를 그린다. 문서와 덱은 사용자가 대화에 쓰는 언어 하나로 쓴다.

## 연구 프로젝트 진행 순서

1. `/informative-slides:goal`: `GOAL.md`를 만든다.
2. 미팅 전 `/informative-slides:meet`: 설명 문서와 덱을 만든다.
3. 미팅에서 사용자가 자료를 읽고 이해한 뒤 정한다.
4. 미팅 뒤 "미팅 정리해": `meet`이 미팅 노트를 쓴다. 다음 미팅 자료는 이 노트의 할 일을 리마인드로 확인한다.
5. 프로젝트를 공유할 때 `/informative-slides:wrapup`.

스킬은 결론을 내리거나 결정하지 않는다. 결정은 사용자가 한다. 커밋은 사용자가 요청할 때만 한다.

## 설치

Claude Code에서 다음을 실행한다.

```
/plugin marketplace add JuwonHwang/informative-slides
/plugin install informative-slides@informative-slides
```

저장소가 갱신되면 `/plugin marketplace update informative-slides`로 받는다. drive-project-forward를 설치했었다면 같은 이름의 스킬(goal, meet, wrapup)이 두 번 보이지 않게 `/plugin uninstall drive-project-forward@drive-project-forward`로 제거한다.

다른 코딩 에이전트에서는 저장소를 받은 뒤 요청에 "skills/informative-slides/SKILL.md를 읽고 그 절차를 따른다"를 붙인다.

## 필요한 것

- Python 3.9 이상: 표지 정보(`project_identity.py`), 검사(`check_deck.py`), 수식 넣기(`embed_math.py`), 검수 서버(`review_server.py`)
- Chrome, Chromium, Edge 중 하나: 화면 넘침과 그림 검사, PDF 생성

## 라이선스

MIT License(`LICENSE`). 다만 `skills/slide-review/assets/fonts/`의 Pretendard 글꼴은 SIL Open Font License 1.1을
따른다(`skills/slide-review/assets/fonts/LICENSE.txt`).
`skills/informative-slides/assets/vendor/mathjax-tex-svg.js`는 MathJax 3.2.2이며 Apache License 2.0을 따른다
(`skills/informative-slides/assets/vendor/MATHJAX-LICENSE.txt`). 수식이 있는 덱에는 이 파일이 들어간다.
