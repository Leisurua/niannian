from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf-checkout", "crlf-checkout"])
def test_smoke_passes_posix_scripts_to_docker(tmp_path, newline):
    pwsh = shutil.which("pwsh")
    assert pwsh, "PowerShell is required to verify infra/smoke.ps1"
    smoke = tmp_path / "smoke.ps1"
    smoke.write_bytes((ROOT / "infra/smoke.ps1").read_text(encoding="utf-8").replace("\n", newline).encode("utf-8"))
    harness = tmp_path / "harness.ps1"
    harness.write_text(r'''
param([string]$SmokePath)
$ErrorActionPreference = 'Stop'
$global:ShellCalls = 0
function docker {
    $global:LASTEXITCODE = 0
    $dockerArgs = @($args)
    if ($dockerArgs -contains 'psql') { Write-Output 'vector'; return }
    $commandIndex = [array]::IndexOf($dockerArgs, '-c')
    if ($commandIndex -ge 0) {
        $global:ShellCalls += 1
        if ($dockerArgs[$commandIndex + 1].Contains("`r")) {
            $global:LASTEXITCODE = 71
        }
        if ($dockerArgs[-1] -notmatch '^e0-t04-smoke/[a-f0-9]{32}\.txt$') {
            throw 'Probe key was not passed as a positional argument'
        }
    }
}
function Invoke-WebRequest { [pscustomobject]@{StatusCode = 403} }
& $SmokePath
if ($global:ShellCalls -ne 2) { throw 'Expected upload and cleanup shell commands' }
''', encoding="utf-8")
    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(harness), "-SmokePath", str(smoke)],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: Synthetic probe cleanup completed." in result.stdout
