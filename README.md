# 🏠 아파트스토리 방문차량 예약 Skill

> **"방문차량 등록해줘"** — 말 한마디면 됩니다.  
> 아파트스토리(AptStory) 웹사이트로 **조회 · 예약 · 수정 · 삭제**까지, AI 에이전트가 대신 처리합니다.

---

## 이게 뭐예요?

우리 아파트 관리 앱 **아파트스토리**에서 방문차량을 등록할 때, 매번 앱 열고 번호판 치고 날짜 고르기 귀찮으셨죠?

이 저장소는 **AI 에이전트용 Skill**입니다.  
Hermes, OpenClaw, Cursor, Codex 등 **Skills를 지원하는 도구**에 넣어두면, 평문으로 말해도 실제로 아파트스토리에 접속해서 작업합니다.

| 할 수 있는 일 | 설명 |
|---|---|
| 🔍 **조회** | 내 방문차량 예약 목록, 개별 상세, 주차 설정 확인 |
| ➕ **예약** | 차량번호 + 날짜로 방문차량 등록 |
| ✏️ **수정** | 기존 예약 날짜·차량번호 변경 |
| 🗑️ **삭제** | 더 이상 필요 없는 예약 취소 |
| ⭐ **즐겨찾기** | 자주 쓰는 차량 번호 북마크 관리 |

모바일 앱 UI 자동화가 아니라, **아파트스토리 웹사이트 로그인 + 공식 API**를 씁니다.  
앱보다 웹이 단순해서(폼 로그인 + 쿠키) 에이전트가 다루기 좋습니다.

---

## 어떤 도구에서 쓸 수 있어요?

Skills 형식을 지원하는 도구라면 대부분 OK입니다.

| 도구 | 사용 방법 |
|---|---|
| **OpenClaw** | Skill 폴더에 이 repo 추가 → `$aptstory-web-reservation` 호출 |
| **Hermes** | Agent skill로 등록 후 자연어로 요청 |
| **Cursor / Codex** | Skill 경로 지정 후 "방문차량 목록 보여줘" 등으로 사용 |
| **직접 실행** | 아래 CLI로 터미널에서 바로 실행 |

에이전트에게는 이렇게 말하면 됩니다:

```
내 아파트스토리 방문차량 예약 목록 5개만 보여줘
```

```
내일 12가3456 차량 방문차량 등록해줘
```

```
visitId 123456 예약 삭제해줘
```

---

## 시작하기

### 1. 준비물

- **Python 3** (추가 패키지 설치 없음, 표준 라이브러리만 사용)
- **아파트스토리 웹 로그인 정보** (아파트 홈페이지 ID / PW)
- **우리 단지 도메인** — 관리사무소에 문의하세요

> 예시: `홍길동더샵아파트` → `https://hgdthesharp.aptstory.com`  
> 단지마다 서브도메인이 다릅니다.

### 2. Skill 등록 (에이전트용)

이 repo를 clone한 뒤, 사용 중인 도구의 Skill 경로에 `APTstory_auto-public-skill` 폴더를 연결하세요.

- Skill 정의: [`APTstory_auto-public-skill/SKILL.md`](./APTstory_auto-public-skill/SKILL.md)
- Agent 설정: [`APTstory_auto-public-skill/agents/openai.yaml`](./APTstory_auto-public-skill/agents/openai.yaml)

### 3. 로그인 정보 설정

비밀번호는 **환경 변수**로 넣는 걸 권장합니다. (쉘 히스토리에 남지 않아요)

```bash
export APTSTORY_BASE_URL="https://your-apartment.aptstory.com"
export APTSTORY_USERNAME="내아이디"
export APTSTORY_PASSWORD="내비밀번호"
```

---

## CLI로 직접 쓰기

에이전트 없이 터미널에서 바로 돌릴 수도 있습니다.

```bash
# 주차 설정 확인
python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py settings

# 방문차량 목록 (최근 5건)
python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py list-visits --limit 5

# 특정 차량번호로 검색
python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py list-visits --car-no 12가3456

# 방문차량 예약 등록
python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py create-visit \
  --car-no 12가3456 \
  --start-date 2026-03-10 \
  --end-date 2026-03-10

# 예약 수정
python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py update-visit 123456 \
  --car-no 12가3456 \
  --start-date 2026-03-11 \
  --end-date 2026-03-11

# 예약 삭제
python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py delete-visit 123456

# 즐겨찾기 목록 / 등록 / 삭제
python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py list-bookmarks
python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py create-bookmark --car-no 12가3456 --title "부모님"
python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py delete-bookmark 42
```

번호판 형식이 특이한 경우 `--allow-any-car-no` 옵션을 붙이세요.

---

## 프로젝트 구조

```
APTstory_auto-public-skill/
├── SKILL.md                 # Skill 정의 (에이전트가 읽는 가이드)
├── agents/openai.yaml       # Agent 인터페이스 설정
├── references/api-notes.md  # 확인된 API 스펙 & 주의사항
└── scripts/
    ├── aptstory_web_cli.py  # CLI 본체
    └── test_aptstory_web_cli.py
```

API 상세는 [`references/api-notes.md`](./APTstory_auto-public-skill/references/api-notes.md)를 참고하세요.

---

## ⚠️ 알아두면 좋은 점

- **단지마다 도메인이 다릅니다.** 다른 아파트로 옮기면 로그인 URL·API를 다시 확인하세요.
- **동/호수는 서버가 로그인 세션에서 자동으로 잡습니다.** 직접 넣을 필요 없어요.
- **날짜는 꼭 명시하세요.** API가 차량번호만으로 당일 예약을 만들어버리는 경우가 있어서, CLI는 시작일·종료일을 필수로 받습니다.
- **비밀번호를 repo에 올리지 마세요.** 환경 변수만 쓰세요.

---

## 테스트

```bash
python3 APTstory_auto-public-skill/scripts/test_aptstory_web_cli.py -v
```

네트워크 없이 입력 검증·에러 처리 로직을 확인합니다.

---

## 라이선스

[LICENSE](./LICENSE) 참고

---

<p align="center">
  <sub>아파트너는 이미 있더라구요 — 아파트스토리는 없어서 만들어봤습니다 🙌</sub><br>
  <sub>문의·이슈는 GitHub Issues로 편하게 남겨주세요!</sub>
</p>
