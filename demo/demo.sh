#!/bin/bash
# dify-admin デモスクリプト
# 使い方: asciinema rec --command "./demo/demo.sh" demo.cast
# GIF変換: agg demo.cast demo.gif

set -e

# 色付き表示用
type_and_run() {
    echo ""
    echo -e "\033[1;36m$ $1\033[0m"
    sleep 1
    eval "$1"
    sleep 2
}

echo -e "\033[1;33m=== dify-admin デモ ===\033[0m"
sleep 1

# 1. 接続チェック
type_and_run "dify-admin doctor"

# 2. アプリ一覧
type_and_run "dify-admin apps list"

# 3. テンプレート一覧
type_and_run "dify-admin apps templates"

# 4. テンプレからアプリ作成
type_and_run "dify-admin apps scaffold chat-basic --name 'Demo Bot'"

# 5. 名前でアプリ取得
type_and_run "dify-admin --json apps search Demo | python3 -m json.tool | head -20"

# 6. JSON出力
type_and_run "dify-admin --json apps list | python3 -c 'import json,sys; [print(a[\"name\"]) for a in json.load(sys.stdin)]'"

# 7. 作成したアプリを削除
type_and_run "dify-admin apps delete --name 'Demo Bot' --yes"

echo ""
echo -e "\033[1;32m=== デモ完了 ===\033[0m"
sleep 1
