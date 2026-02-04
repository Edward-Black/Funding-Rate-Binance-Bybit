# Хук PyInstaller: включить fastapi и все подмодули в exe
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('fastapi')
