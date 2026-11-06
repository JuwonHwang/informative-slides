# slide-review

HTML 슬라이드 덱을 검수 화면에 띄워 요소별 의견을 받는 에이전트 스킬이다. 어느 도구로 만든 덱이든
`<section>`으로 장이 나뉘고 `←`/`→`로 넘어가면 검수할 수 있다.

## 설치

`informative-slides` 플러그인에 함께 들어 있다. 저장소 루트의 [README](../../README.md)대로 설치하면
`informative-slides:slide-review`로 등록된다.

다른 코딩 에이전트에서는 요청에 "skills/slide-review/SKILL.md를 읽고 그 절차로 검수 화면을 열어라"를 붙인다.

## 직접 실행

```bash
python3 skills/slide-review/scripts/review.py open <덱.html>   # 검수 화면을 연다. 열린 검수 탭이 있으면 그 탭의 내용을 바꾼다
python3 skills/slide-review/scripts/review.py stop             # 검수 서버를 내린다
```

- 요소를 클릭해 의견을 단다. 같은 요소를 다시 클릭하면 상위 블록이 선택된다.
- 의견은 입력하는 대로 `<덱 이름>-feedback.md`, `<덱 이름>-feedback.json`에 저장된다.
- `피드백 보내기`: 검수를 이어 가면서 지금까지의 의견을 보낸다. `<덱 이름>-feedback.sent`가 생기고, 의견은 `<덱 이름>-feedback-history/`로 옮겨진다. 에이전트가 덱을 고치면 화면이 덱을 다시 불러온다.
- `검수 완료`: 남은 의견을 보내고 검수를 끝낸다. `<덱 이름>-feedback.done`이 생긴다. 이후 화면에서는 HTML·PDF 저장과 PDF 설정만 쓸 수 있고, 탭을 닫으면 검수 서버가 종료된다.
- 검수 서버는 열린 검수 화면이 없는 상태가 10분, 또는 조작이 없는 상태가 60분 이어지면 스스로 종료한다.
- 상단 막대에서 비율, 표시 크기, PDF 가로 길이를 바꿀 수 있다. 화면과 PDF에만 적용되고 덱 파일은 바뀌지 않는다.
- `HTML 저장`, `PDF 저장`은 Chrome·Edge에서 저장 위치를 묻는다. Safari·Firefox는 브라우저 다운로드 설정을 따른다. PDF는 서버 컴퓨터의 Chrome, Chromium, Edge(Playwright Chromium 포함)로 만든다. 서버 컴퓨터에 없으면(ssh 원격 서버 등) 브라우저 인쇄 창으로 저장한다. 검수 화면과 PDF에는 함께 들어 있는 Pretendard 글꼴(SIL OFL 1.1)이 쓰이고 PDF에 포함된다.
