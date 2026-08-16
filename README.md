# APTstory_auto-public-skill

아파트스토리(AptStory) 단지 웹사이트 세션으로 방문차량 예약을 자동화하는 OpenClaw/Codex skill입니다.

## Quick start

```bash
export APTSTORY_BASE_URL="https://your-apartment.aptstory.com"
export APTSTORY_USERNAME="your-id"
export APTSTORY_PASSWORD="your-password"

python3 APTstory_auto-public-skill/scripts/aptstory_web_cli.py list-visits --limit 5
```

자세한 사용법과 API 노트는 [`APTstory_auto-public-skill/SKILL.md`](./APTstory_auto-public-skill/SKILL.md)를 보세요.
