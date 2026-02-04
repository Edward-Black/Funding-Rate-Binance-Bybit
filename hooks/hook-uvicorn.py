# Хук PyInstaller: включить uvicorn и все подмодули в exe
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('uvicorn')
