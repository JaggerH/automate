@echo off
chcp 65001 > nul

rem 静默启动守护模式 - 最小化输出
python main.py --daemon --silent