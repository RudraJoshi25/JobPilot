@echo off
cd /d C:\Users\rjjos\job-agent
call .venv\Scripts\activate.bat
python main.py --auto
>> logs\scheduler.log 2>&1