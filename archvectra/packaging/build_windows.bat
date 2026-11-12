@echo off
rem Builds dist\ArchVectra\ : engine\archvectra.exe + the AutoCAD LISP + install notes.
rem Run from the archvectra folder inside an activated virtual environment:
rem   pip install -e . pyinstaller
rem   packaging\build_windows.bat
setlocal
pyinstaller --noconfirm --clean --onedir --name archvectra ^
  --distpath build\pyi-dist --workpath build\pyi-work --specpath build ^
  --collect-submodules skimage --collect-data skimage ^
  --exclude-module onnxruntime --exclude-module pymupdf4llm --exclude-module pymupdf.layout ^
  --exclude-module matplotlib --exclude-module tkinter ^
  --paths src packaging\entry.py || exit /b 1
if exist dist\ArchVectra rmdir /s /q dist\ArchVectra
mkdir dist\ArchVectra
xcopy /e /i /q build\pyi-dist\archvectra dist\ArchVectra\engine >nul || exit /b 1
copy /y autocad\archvectra.lsp dist\ArchVectra\ >nul
copy /y autocad\INSTALL.md dist\ArchVectra\ >nul
copy /y config\default.toml dist\ArchVectra\ >nul
echo Built dist\ArchVectra
