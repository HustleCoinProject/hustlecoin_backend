@echo off
setlocal enabledelayedexpansion

:: Ask user for file extensions
set /p extensions="Enter file extensions you want to send in context (space separated, e.g. py txt c cpp kt java): "

:: Output file
set outputfile=all_code_context.txt
> "%outputfile%" echo ==== Combined code files ====
echo Searching for: %extensions%
echo Output will be in "%outputfile%"
echo.

:: Loop over each extension
for %%e in (%extensions%) do (
    echo --- Extension: %%e ---
    for /r %%f in (*.%%e) do (
        set "filename=%%~nxf"
        set "foldername=%%~pnf"

        :: Skip if file or any folder in its path starts with "."
        echo !foldername! | findstr /r "\\\.[^\\]*" >nul && (
            rem Found a folder starting with dot, skip this file
            continue
        )
        if "!filename:~0,1!"=="." (
            rem File starts with dot, skip
            continue
        )

        echo ==== FILE: %%f ==== >> "%outputfile%"
        type "%%f" >> "%outputfile%"
        echo. >> "%outputfile%"
        echo. >> "%outputfile%"
    )
)

echo Done! All matching files combined into "%outputfile%"
pause
