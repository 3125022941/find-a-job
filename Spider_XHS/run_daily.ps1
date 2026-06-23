# Qiuzhao tiqianpi - daily run + Windows toast when a new company opens.
# Kept ASCII-only so Windows PowerShell 5.1 (no-BOM) parses it correctly.
# Chinese notification text comes from recruit_out/notify_message.txt (UTF-8, written by Python).
# Manual test: powershell -ExecutionPolicy Bypass -File run_daily.ps1

$ErrorActionPreference = 'Continue'
Set-Location -Path $PSScriptRoot

# Make sure execjs can find node (scheduled-task PATH may be incomplete)
$env:Path = "E:\Node;" + $env:Path

$python = "C:\Users\lenovo\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm'

New-Item -ItemType Directory -Force -Path "recruit_out\logs" | Out-Null

# Run collector (--detail fetches body text for high-score hits => better company detection)
& $python "xhs_recruit_collect.py" --detail *> "recruit_out\logs\cron-last-run.log"

# Read this run's newly-opened companies
$news = @()
$newFile = "recruit_out\new_companies.json"
if (Test-Path $newFile) {
    try {
        $parsed = Get-Content $newFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($parsed) { $news = @($parsed) }
    } catch {}
}

if ($news.Count -gt 0) {
    $msg = ""
    if (Test-Path "recruit_out\notify_message.txt") {
        $msg = (Get-Content "recruit_out\notify_message.txt" -Raw -Encoding UTF8).Trim()
    }
    if ([string]::IsNullOrWhiteSpace($msg)) { $msg = ($news -join ", ") }

    "$ts  $msg" | Add-Content -Encoding UTF8 "recruit_out\alerts.log"

    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $ni = New-Object System.Windows.Forms.NotifyIcon
        $ni.Icon = [System.Drawing.SystemIcons]::Information
        $ni.BalloonTipTitle = "XHS Recruit Monitor"
        $ni.BalloonTipText = $msg
        $ni.Visible = $true
        $ni.ShowBalloonTip(20000)
        Start-Sleep -Seconds 10
        $ni.Dispose()
    } catch {
        "$ts  toast failed: $_" | Add-Content -Encoding UTF8 "recruit_out\alerts.log"
    }
} else {
    "$ts  no new company" | Add-Content -Encoding UTF8 "recruit_out\logs\cron-heartbeat.log"
}
