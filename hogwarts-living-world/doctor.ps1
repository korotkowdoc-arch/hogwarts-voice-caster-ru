param([string]$GameDir="")
$ErrorActionPreference="Stop"

$dir=Join-Path $env:LOCALAPPDATA "HogwartsLivingWorld"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$report=[ordered]@{
    generated_at=(Get-Date).ToString("o")
    os="Windows"
    local_bridge_running=$false
    local_bridge_version=$null
    cloud_provider_names=@()
    game_hook_verified=$false
    last_ue4ss_probe=$null
    world_db_exists=(Test-Path (Join-Path $dir "world.sqlite3"))
    world_backups=0
    encrypted_keys_file_exists=(Test-Path (Join-Path $dir "free-keys.dpapi.json"))
    existing_ue4ss=$false
    sonorus_server_present=$false
    voice_spell_caster_present=$false
    game_path_was_supplied=([bool]$GameDir)
}
$backup_dir=Join-Path $dir "backups"
if(Test-Path $backup_dir){
    $report.world_backups=@(Get-ChildItem -Path $backup_dir -Filter "world-*.sqlite3" -File -ErrorAction SilentlyContinue).Count
}
try{
    $health=Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 3
    $report.local_bridge_running=$true
    $report.local_bridge_version=$health.version
    $report.cloud_provider_names=@($health.configured_providers)
    $report.last_ue4ss_probe=$health.last_probe.received_at
}catch{
    Write-Host "Bridge is not running. Start run.bat before checking in-game communication."
}
if($GameDir){
    $p=Join-Path $GameDir "Phoenix\Binaries\Win64"
    if(-not(Test-Path $p)){ $p=Join-Path $GameDir "Binaries\WinGDK" }
    $report.existing_ue4ss=(Test-Path (Join-Path $p "ue4ss\Mods"))
    $report.sonorus_server_present=(Test-Path (Join-Path $p "sonorus\server.py"))
    $report.voice_spell_caster_present=(Test-Path (Join-Path $p "ue4ss\Mods\SpellCaster"))
}
$path=Join-Path $dir "diagnostic-report.json"
($report | ConvertTo-Json -Depth 5) | Set-Content -Encoding UTF8 -Path $path
Write-Host ""
Write-Host "HOGWARTS LIVING WORLD DIAGNOSTICS"
Write-Host "Status and booleans only. No API keys or full game paths included."
$report | Format-List | Out-Host
Write-Host "Report: $path"
Write-Host ""
Write-Host "For next-game-day testing: Ctrl+Alt+F10, then run doctor.bat again."
