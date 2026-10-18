$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "C:\Users\lenovo\AppData\Local\Programs\Python\Python312\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "未找到 Python 3.12：$Python"
}

$Venv = Join-Path $ProjectRoot ".venv"
if (-not (Test-Path -LiteralPath (Join-Path $Venv "Scripts\python.exe"))) {
    & $Python -m venv $Venv
}

$VenvPython = Join-Path $Venv "Scripts\python.exe"
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip
& $VenvPython -m pip install --disable-pip-version-check -e $ProjectRoot pyinstaller
& $VenvPython -m unittest discover -s (Join-Path $ProjectRoot "tests") -v

& $VenvPython -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "念念-Windows老人演示端" `
    --specpath (Join-Path $ProjectRoot "build") `
    --paths (Join-Path $ProjectRoot "src") `
    (Join-Path $ProjectRoot "launcher.py")

Write-Host "已生成：$(Join-Path $ProjectRoot 'dist\念念-Windows老人演示端.exe')"
