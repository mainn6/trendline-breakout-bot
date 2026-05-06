# Oracle Cloud Free Tier 배포 가이드

평생 무료 24시간 봇 운영. Tokyo region 사용 시 Binance Futures WebSocket 정상 동작.

## Phase 1 — Oracle Cloud 계정 (10분, 직접)

1. https://signup.cloud.oracle.com 접속
2. 이메일 + 신용카드 등록 (검증용, **결제 안 됨**)
3. **Home Region: Japan East (Tokyo)** 선택 ‼️ 한 번 정하면 못 바꿔
4. 가입 완료까지 1~3분 대기

## Phase 2 — VM 인스턴스 생성 (5분)

1. 콘솔 좌측 메뉴 → **Compute → Instances**
2. **Create instance** 클릭
3. 옵션:
   - Name: `breakout-bot`
   - Image: **Ubuntu 22.04** (Canonical)
   - Shape: **VM.Standard.A1.Flex** (ARM Ampere) — Always Free
   - OCPUs: **4** / Memory: **24 GB**
   - VNIC: 기본 그대로 (자동 public IP)
   - SSH key:
     - 로컬에 없으면 "Generate SSH key" 클릭 → `Save Private Key` 다운로드
     - `~/.ssh/oci_breakout_bot.key`로 저장 후 `chmod 600`
4. **Create** 클릭, 1~2분 후 RUNNING

## Phase 3 — SSH 접속 (1분)

콘솔에서 인스턴스 클릭 → Public IP 복사 (예: `158.101.x.x`)

```bash
chmod 600 ~/.ssh/oci_breakout_bot.key
ssh -i ~/.ssh/oci_breakout_bot.key ubuntu@<PUBLIC_IP>
```

## Phase 4 — 자동 셋업 스크립트 1줄 (3분)

VM 안에서:

```bash
curl -L https://raw.githubusercontent.com/mainn6/trendline-breakout-bot/main/deploy/bootstrap.sh | bash
```

(또는 git clone 후 `bash deploy/setup.sh`)

## Phase 5 — `.env` 작성

```bash
nano ~/trendline-breakout-bot/.env
```

```
TELEGRAM_BOT_TOKEN=8260348358:AAGGG3M5L6cUb6AzfMlDXw21YM4mqQqEz7s
TELEGRAM_CHAT_ID=5156600204
LOG_LEVEL=INFO
```

저장: `Ctrl+O`, `Enter`, `Ctrl+X`

## Phase 6 — 시작!

```bash
sudo systemctl start breakout-bot
sudo journalctl -u breakout-bot -f
```

로그에서:
- `WS connected: ... streams` ✅
- `Bot 부팅 완료` Telegram 메시지 도착 ✅

이후 Mac 꺼도 봇은 24시간 동작.

## 명령어 cheatsheet

| 작업 | 명령 |
|---|---|
| 시작 | `sudo systemctl start breakout-bot` |
| 정지 | `sudo systemctl stop breakout-bot` |
| 재시작 | `sudo systemctl restart breakout-bot` |
| 상태 | `sudo systemctl status breakout-bot` |
| 실시간 로그 | `sudo journalctl -u breakout-bot -f` |
| 최근 100줄 | `sudo journalctl -u breakout-bot -n 100 --no-pager` |
| 자동시작 OFF | `sudo systemctl disable breakout-bot` |
| 코드 업데이트 | `cd ~/trendline-breakout-bot && git pull && sudo systemctl restart breakout-bot` |

## 비용

**0원 (평생)** — Always Free 한도:
- ARM Ampere A1: 4 OCPU + 24GB RAM
- 200GB block storage
- 월 10TB outbound traffic

봇은 RAM 200MB도 안 씀 → 한도 압도적으로 여유.
