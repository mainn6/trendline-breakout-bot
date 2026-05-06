#!/usr/bin/env bash
# Oracle Cloud Free Tier (Ubuntu 22.04 ARM) 위에서 봇 셋업.
# SSH 접속 후 1번 실행하면 끝.
set -euo pipefail

REPO_URL="https://github.com/mainn6/trendline-breakout-bot.git"
APP_DIR="$HOME/trendline-breakout-bot"

echo "==> 1. 시스템 패키지 업데이트"
sudo apt-get update -y
sudo apt-get install -y python3.11 python3.11-venv python3-pip git build-essential \
                        libfreetype6-dev pkg-config

echo "==> 2. 코드 가져오기"
if [ -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR" && git pull
else
  git clone "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
fi

echo "==> 3. 가상환경 + 의존성"
cd "$APP_DIR"
python3.11 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -e ".[dev]"
pip install -q mplfinance

echo "==> 4. .env 파일 — 직접 채워야 함"
if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "‼️  .env 파일 직접 편집:"
  echo "    nano $APP_DIR/.env"
  echo "    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 채우기"
  echo
fi

echo "==> 5. 테스트 (선택)"
.venv/bin/pytest -q || echo "(테스트 일부 실패 — 무시 가능)"

echo "==> 6. systemd service 등록"
sudo cp deploy/breakout-bot.service /etc/systemd/system/breakout-bot.service
sudo systemctl daemon-reload
sudo systemctl enable breakout-bot

echo
echo "✅ 셋업 완료!"
echo
echo "다음 명령어로 실제 시작:"
echo "  sudo systemctl start breakout-bot"
echo
echo "로그 확인:"
echo "  sudo journalctl -u breakout-bot -f"
echo
echo "상태 확인:"
echo "  sudo systemctl status breakout-bot"
