# informative-slides

발표자 없이 읽어도 이해되는 HTML 슬라이드를 만들고, 사람이 요소별로 검수하는 에이전트 스킬 두 개이다.
Claude Code를 기준으로 만들었고, 다른 코딩 에이전트에서도 SKILL.md를 읽게 해서 쓸 수 있다.

| 스킬 | 하는 일 |
|---|---|
| [`informative-slides`](skills/informative-slides/) | 노트, 설계 문서, 실험 결과를 한국어·영어 전환이 되는 단일 HTML 덱으로 만든다. 장마다 명사구 제목, 메시지 한 문장, 근거(구조도, 확대 상세도, 표), 출처를 둔다. 순서가 있는 설명은 단계로 나눠 보인다 |
| [`slide-review`](skills/slide-review/) | 덱을 검수 화면에 띄워 요소를 클릭해 의견을 받고, 의견을 파일로 남긴다. 비율·크기를 바꿔 보고, HTML과 PDF(글꼴 포함, 단계마다 한 쪽)를 저장한다 |

## 설치

Claude Code 플러그인으로 설치한다. Claude Code에서 다음을 실행한다.

```
/plugin marketplace add JuwonHwang/informative-slides
/plugin install informative-slides@informative-slides
```

설치하면 두 스킬이 `informative-slides:informative-slides`, `informative-slides:slide-review`로 등록된다.
저장소가 갱신되면 `/plugin marketplace update informative-slides`로 받는다.

다른 코딩 에이전트에서는 저장소를 받은 뒤 요청에 "skills/informative-slides/SKILL.md를 읽고 그 절차를 따른다"를 붙인다.

## 필요한 것

- Python 3.9 이상: 검사 스크립트(`check_deck.py`)와 검수 서버(`review_server.py`)
- Chrome, Chromium, Edge 중 하나: 화면 넘침 검사와 PDF 생성

## 라이선스

MIT License(`LICENSE`). 다만 `skills/slide-review/assets/fonts/`의 Pretendard 글꼴은 SIL Open Font License 1.1을
따른다(`skills/slide-review/assets/fonts/LICENSE.txt`).
`skills/informative-slides/assets/template.html`은 [drive-project-forward](https://github.com/JuwonHwang/drive-project-forward)의
슬라이드 템플릿과 `slides/RULES.md`를 기반으로 한다.
