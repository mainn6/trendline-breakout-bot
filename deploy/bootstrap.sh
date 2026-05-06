#!/usr/bin/env bash
# 한 줄로 실행: curl -L <url> | bash
# git clone + setup.sh 실행
set -euo pipefail
REPO_URL="https://github.com/mainn6/trendline-breakout-bot.git"
APP_DIR="$HOME/trendline-breakout-bot"

if ! command -v git >/dev/null 2>&1; then
  sudo apt-get update -y && sudo apt-get install -y git
fi

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
git pull
bash deploy/setup.sh
