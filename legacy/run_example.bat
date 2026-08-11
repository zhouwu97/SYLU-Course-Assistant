@echo off
chcp 65001 >nul
py sylu_course_auto.py --config config.json --yes --keep-open
pause
