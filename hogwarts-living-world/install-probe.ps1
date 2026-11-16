param([string]$ModsDirectory="")
$ErrorActionPreference = "Stop"
$source=Join-Path $PSScriptRoot "UE4SS-OPTIONAL\HLWProbe"
if(-not(Test-Path (Join-Path $source "Scripts\main.lua"))){
    throw "Probe script not found in distribution. Extract the entire ZIP first."
}
Write-Host ""
Write-Host "HLW — OPTIONAL, READ-ONLY UE4SS HANDSHAKE INSTALLER"
Write-Host "Do not install while Hogwarts Legacy is running."
Write-Host "Make a game save backup first. This will not install UE4SS or edit any game saves."
if(-not $ModsDirectory){
    $ModsDirectory=Read-Host "Enter FULL path to the EXISTING Hogwarts Legacy\Phoenix\Binaries\Win64\ue4ss\Mods folder"
}
if(-not $ModsDirectory){throw "Cancelled: no path supplied."}
$targetFolder=Get-Item -LiteralPath $ModsDirectory -ErrorAction Stop
$target=$targetFolder.FullName
if($targetFolder.Name -ne "Mods" -or (Split-Path (Split-Path $target -Parent) -Leaf) -ne "ue4ss"){
    throw "Wrong target: select the EXISTING ue4ss\Mods folder, not the game root."
}
if($target -notmatch '(?i)[\\/]Binaries[\\/](Win64|WinGDK)[\\/]ue4ss[\\/]Mods$'){
    throw "The directory must be inside Hogwarts Legacy\Phoenix\Binaries\Win64 (or WinGDK)."
}
if(-not(Test-Path (Join-Path $target "SonorusMod")) -and -not(Test-Path (Join-Path $target "SpellCaster"))){
    Write-Host "Warning: no SonorusMod or SpellCaster present in this UE4SS folder."
    $answer=Read-Host "Continue with this existing UE4SS installation? Type YES"
    if($answer -cne "YES"){throw "Cancelled."}
}
$dest=Join-Path $target "HLWProbe"
if(Test-Path $dest){throw "HLWProbe already exists. No files were overwritten."}
Copy-Item -LiteralPath $source -Destination $dest -Recurse -ErrorAction Stop
Write-Host "Copied diagnostic probe only to: $dest"
Write-Host "No original mods.txt, game packages or save files were modified."
Write-Host "If your older UE4SS needs it, manually add HLWProbe : 1 to ue4ss\Mods\mods.txt."
Write-Host "In-game press Ctrl+Alt+F10 and check http://127.0.0.1:8765/health"
