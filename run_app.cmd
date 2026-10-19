@echo off
setlocal
cd /d "%~dp0"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Preparando o ambiente local do painel...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv "%~dp0.venv"
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo Python nao foi encontrado. Instale o Python 3 e marque a opcao para adicionar ao PATH.
            pause
            exit /b 1
        )
        python -m venv "%~dp0.venv"
    )
    if errorlevel 1 (
        echo Nao foi possivel criar o ambiente do painel.
        pause
        exit /b 1
    )
)

"%VENV_PY%" -c "import streamlit, pandas, plotly, openpyxl, xlrd" >nul 2>nul
if errorlevel 1 (
    echo Instalando os componentes do painel. Na primeira vez, e necessario acesso a internet.
    "%VENV_PY%" -m pip install --upgrade pip
    if errorlevel 1 (
        echo Nao foi possivel atualizar o instalador Python.
        pause
        exit /b 1
    )
    "%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo Nao foi possivel instalar os componentes. Verifique a conexao e tente novamente.
        pause
        exit /b 1
    )
)

echo Abrindo o painel no navegador. Para encerrar, feche esta janela.
"%VENV_PY%" -m streamlit run "%~dp0app.py" --server.address=127.0.0.1 --server.headless=false --browser.gatherUsageStats=false
if errorlevel 1 (
    echo O painel foi encerrado com erro. Confira as mensagens acima.
    pause
)
