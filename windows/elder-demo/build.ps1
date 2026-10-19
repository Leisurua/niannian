$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv $Venv
    } else {
        & python -m venv $Venv
    }
    if ($LASTEXITCODE -ne 0) { throw "无法创建 Python 3.12 虚拟环境" }
}
& $VenvPython -c "import sys; assert sys.version_info[:2] == (3, 12)"
if ($LASTEXITCODE -ne 0) { throw "需要 Python 3.12" }
& $VenvPython -m pip install --disable-pip-version-check -e $ProjectRoot pyinstaller
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
& $VenvPython -m unittest discover -s (Join-Path $ProjectRoot "tests") -v
if ($LASTEXITCODE -ne 0) { throw "客户端测试失败" }
& $VenvPython -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "念念-Windows老人演示端" `
    --specpath (Join-Path $ProjectRoot "build") `
    --paths (Join-Path $ProjectRoot "src") `
    (Join-Path $ProjectRoot "launcher.py")
if ($LASTEXITCODE -ne 0) { throw "打包失败" }
Write-Host "构建完成"
