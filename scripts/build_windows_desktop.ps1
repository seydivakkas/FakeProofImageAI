<#
P9-I04 — offline-capable PyInstaller Windows one-directory build.
Requires locally installed dependencies and PyInstaller. Does not download,
contact APIs, create a certificate, or claim installer/Windows acceptance.
Run from the repository root on Windows 10/11 with a suitable Python venv.
#>
[CmdletBinding()]
param([string]$OutputName = 'FakeProofImageAI')
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
    throw 'Bu betik Windows üzerinde çalıştırılmalıdır.'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
& python -c 'import aiforensics, tkinter, PIL, scipy, cv2, PyInstaller'
if ($LASTEXITCODE -ne 0) { throw 'Gerekli paketler mevcut değil; önce yerel wheel dosyalarından kurun.' }
$entry = Join-Path $root 'src\aiforensics\desktop_app.py'
# The entry script itself uses relative imports: use an absolute wrapper script.
$wrapper = Join-Path $root 'scripts\desktop_frozen_entry.py'
$arguments = @('--noconfirm','--clean','--onedir','--windowed',
  '--name', $OutputName,
  '--paths', (Join-Path $root 'src'),
  '--collect-submodules','aiforensics',
  '--collect-all','scipy',
  '--collect-all','cv2',
  '--collect-all','PIL')
$examples = Join-Path $root 'examples'
if (Test-Path $examples) { $arguments += @('--add-data', "$examples;examples") }
& python -m PyInstaller @arguments $wrapper
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller derlemesi başarısız.' }
$target = Join-Path $root "dist\$OutputName\$OutputName.exe"
if (-not (Test-Path $target)) { throw 'Beklenen .exe oluşturulmadı.' }
$sha = (Get-FileHash -Algorithm SHA256 -Path $target).Hash.ToLowerInvariant()
$metadata = @{ scheme='fakeproof.windows.bundle.v1'; executable=$target;
  sha256=$sha; validation='NOT_REAL_WINDOWS_ACCEPTANCE'; origin_verdict='NONE' }
$metadata | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $root "dist\$OutputName\BUILD_SHA256.json")
Write-Host "Derleme üretildi: $target"
Write-Host 'Uyarı: Derleme başarılı olsa bile gerçek Windows cihaz kabulü henüz yapılmamıştır.'
