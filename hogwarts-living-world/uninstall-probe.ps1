param([string]$ModsDirectory="")
$ErrorActionPreference = "Stop"
Write-Host "HLW — OPTIONAL UE4SS PROBE REMOVAL"
if(-not $ModsDirectory){
    $ModsDirectory=Read-Host "Enter FULL path to the EXISTING ue4ss\Mods folder"
}
$parent=Get-Item -LiteralPath $ModsDirectory -ErrorAction Stop
if($parent.Name -ne "Mods" -or (Split-Path (Split-Path $parent.FullName -Parent) -Leaf) -ne "ue4ss"){
    throw "Wrong path: expected ue4ss\Mods directory."
}
$target=Join-Path $parent.FullName "HLWProbe"
$script=Join-Path $target "Scripts\main.lua"
if(-not(Test-Path $script)){throw "HLW probe not found; nothing was deleted."}
$content=Get-Content -LiteralPath $script -Raw -Encoding UTF8
if(-not $content.Contains("Hogwarts Living World UE4SS handshake ONLY")){
    throw "Refusing to remove an unknown mod. This does not look like our diagnostic probe."
}
$confirm=Read-Host "Delete ONLY HLWProbe? Type YES"
if($confirm -cne "YES"){throw "Cancelled."}
Remove-Item -LiteralPath $target -Recurse -Force
Write-Host "Removed HLWProbe only. Other UE4SS mods were untouched."
Write-Host "If you manually added HLWProbe : 1 to mods.txt, remove only that line."
