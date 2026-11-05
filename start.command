#!/bin/sh
cd "$(dirname "$0")" || exit 1
python3 launcher.py
if [ "$?" -ne 0 ]; then
  printf '\n启动遇到问题，请保留此窗口的错误提示。按回车退出。\n'
  read -r response
fi
