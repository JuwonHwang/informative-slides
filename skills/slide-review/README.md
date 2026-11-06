# slide-review

HTML 슬라이드 덱을 검수 화면에 띄워 요소별 의견을 받는 에이전트 스킬이다. 어느 도구로 만든 덱이든
`<section>`으로 장이 나뉘고 `←`/`→`로 넘어가면 검수할 수 있다.

## 설치

`informative-slides` 플러그인에 함께 들어 있다. 저장소 루트의 [README](../../README.md)대로 설치하면
`informative-slides:slide-review`로 등록된다.

다른 코딩 에이전트에서는 요청에 "skills/slide-review/SKILL.md를 읽고 그 절차로 검수 화면을 열어라"를 붙인다.

## 직접 실행

```bash
python3 skills/slide-review/scripts/review_server.py <덱 폴더> --open <덱.html>
```

- 요소를 클릭해 의견을 단다. 같은 요소를 다시 클릭하면 상위 블록이 선택된다.
- 의견은 입력하는 대로 `<덱 이름>-feedback.md`, `<덱 이름>-feedback.json`에 저장된다.
- `검수 완료`를 누르면 `<덱 이름>-feedback.done`이 생긴다. 에이전트는 이 파일을 기다렸다가 의견을 읽는다.
- 상단 막대에서 비율, 표시 크기, PDF 가로 길이를 바꿀 수 있다. 화면과 PDF에만 적용되고 덱 파일은 바뀌지 않는다.
- `HTML 저장`, `PDF 저장`은 Chrome·Edge에서 저장 위치를 묻는다. Safari·Firefox는 브라우저 다운로드 설정을 따른다. PDF는 서버가 Chrome으로 만들며 Chrome, Chromium, Edge 중 하나가 설치되어 있어야 한다. 검수 화면과 PDF에는 함께 들어 있는 Pretendard 글꼴(SIL OFL 1.1)이 쓰이고 PDF에 포함된다.
