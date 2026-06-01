@echo off
cd /d "%~dp0"

echo === Installing PyInstaller ===
pip install pyinstaller -q

echo.
echo === Building ImageVault.exe (single file) ===
pyinstaller --onefile --noconsole --name ImageVault --icon=icon.ico --clean main.py

echo.
echo === Done ===
echo Output: dist\ImageVault.exe
echo Just share this single .exe file — no install needed.
pause
