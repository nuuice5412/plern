# =====================================================================
#  run.ps1 - ตั้งค่าและเปิดเว็บแอปในคำสั่งเดียว (Windows / PowerShell)
#
#    .\run.ps1              ติดตั้งของที่ขาด (ถ้ามี) แล้วเปิดเว็บ
#    .\run.ps1 -Reset       ลบฐานข้อมูลแล้วสร้างใหม่ + seed ใหม่
#    .\run.ps1 -Port 8000   เปลี่ยนพอร์ต
#    .\run.ps1 -NoBrowser   ไม่ต้องเปิดเบราว์เซอร์ให้
#
# ถ้า PowerShell บล็อกสคริปต์ ให้รัน:
#    powershell -ExecutionPolicy Bypass -File .\run.ps1
# =====================================================================
[CmdletBinding()]
param(
    [switch]$Reset,
    [int]$Port = 5000,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    $text" -ForegroundColor DarkGray }

# ---------------------------------------------------------------------
# 1) หา Python
# ---------------------------------------------------------------------
function Find-Python {
    $candidates = @()

    foreach ($name in @('python', 'python3', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { $candidates += $cmd.Source }
    }

    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
                   ForEach-Object { $_.FullName }
    $candidates += Get-ChildItem "C:\Python3*\python.exe" -ErrorAction SilentlyContinue |
                   ForEach-Object { $_.FullName }
    # runtime ที่มาพร้อมเครื่องมือบางตัว (เผื่อเครื่องนี้ไม่มี Python ติดตั้งเอง)
    $candidates += Get-ChildItem "$env:USERPROFILE\.dsh\dsh-runtimes\*\dependencies\python\python.exe" -ErrorAction SilentlyContinue |
                   ForEach-Object { $_.FullName }

    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) {
            $version = & $path -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$version -ge [version]'3.10') {
                return $path
            }
        }
    }
    throw "ไม่พบ Python 3.10 ขึ้นไป กรุณาติดตั้งจาก https://www.python.org/downloads/ (ติ๊ก Add to PATH ด้วย)"
}

Write-Step 'ตรวจสอบ Python'
$python = Find-Python
Write-Ok $python

# ---------------------------------------------------------------------
# 2) สร้าง virtual environment + ติดตั้ง library
# ---------------------------------------------------------------------
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Step 'สร้าง virtual environment (.venv)'
    & $python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'สร้าง venv ไม่สำเร็จ' }
    $needInstall = $true
} else {
    Write-Ok 'มี .venv อยู่แล้ว'
    $needInstall = $false
}

Write-Step 'ตรวจสอบ library (Flask, pyodbc, requests)'
$missing = & $venvPython -c "import importlib.util as u; print(''.join(m for m in ['flask','pyodbc','requests'] if u.find_spec(m) is None))"
if ($missing -or $needInstall) {
    Write-Ok "ติดตั้ง: $missing"
    & $venvPython -m pip install --quiet --disable-pip-version-check --upgrade pip
    & $venvPython -m pip install --quiet --disable-pip-version-check -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'ติดตั้ง library ไม่สำเร็จ (ตรวจสอบอินเทอร์เน็ต)' }
} else {
    Write-Ok 'ครบแล้ว'
}

# ---------------------------------------------------------------------
# 3) ฐานข้อมูล
# ---------------------------------------------------------------------
Write-Step 'ตรวจสอบฐานข้อมูล MusicStreamingDB'
$dbReady = $false
if (-not $Reset) {
    & $venvPython tools\init_db.py --check *> $null
    $dbReady = ($LASTEXITCODE -eq 0)
}

if ($Reset -or -not $dbReady) {
    if ($Reset) { Write-Ok 'โหมด -Reset: ลบและสร้างฐานข้อมูลใหม่' }
    else        { Write-Ok 'ยังไม่มีฐานข้อมูล (หรือเชื่อมต่อไม่ได้) -> สร้างใหม่' }
    & $venvPython tools\init_db.py
    if ($LASTEXITCODE -ne 0) {
        throw 'สร้างฐานข้อมูลไม่สำเร็จ ตรวจสอบว่า service SQL Server ทำงานอยู่ และชื่อ instance ถูกต้อง (ค่า default: .\SQLEXPRESS)'
    }
} else {
    Write-Ok 'ฐานข้อมูลพร้อมใช้'
}

# ---------------------------------------------------------------------
# 4) ไฟล์เสียงตัวอย่าง
# ---------------------------------------------------------------------
Write-Step 'ตรวจสอบไฟล์เสียงตัวอย่าง'
$audioCount = @(Get-ChildItem 'app\static\audio\song_*.wav' -ErrorAction SilentlyContinue).Count
if ($audioCount -eq 0) {
    & $venvPython tools\gen_audio.py --count 24
} else {
    Write-Ok "มีอยู่แล้ว $audioCount ไฟล์"
}

# ---------------------------------------------------------------------
# 5) เปิดเว็บ
# ---------------------------------------------------------------------
$url = "http://127.0.0.1:$Port"
Write-Host ''
Write-Host '  ┌───────────────────────────────────────────────┐' -ForegroundColor Green
Write-Host "     Spi Music กำลังทำงานที่  $url" -ForegroundColor Green
Write-Host '     บัญชีทดลอง: demo / demo1234' -ForegroundColor Green
Write-Host '     กด Ctrl+C เพื่อหยุด' -ForegroundColor Green
Write-Host '  └───────────────────────────────────────────────┘' -ForegroundColor Green
Write-Host ''

if (-not $NoBrowser) {
    Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 3; Start-Process $u } -ArgumentList $url | Out-Null
}

$env:FLASK_DEBUG = '1'
$env:PORT = "$Port"
& $venvPython run.py
