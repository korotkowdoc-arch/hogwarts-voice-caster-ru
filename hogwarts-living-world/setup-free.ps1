# Secure, local-only first-run setup. No secrets sent to GitHub.
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "This setup requires Windows DPAPI." }
$dir = Join-Path $env:LOCALAPPDATA "HogwartsLivingWorld"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$target=Join-Path $dir "free-keys.dpapi.json"

Write-Host ""
Write-Host "HOGWARTS LIVING WORLD - CLOUD FREE ACCOUNT SETUP"
Write-Host "Use ONLY unbilled free-tier API projects. Paid accounts can charge money."
Write-Host "API keys are encrypted for this Windows user and never written to GitHub."
Write-Host "Press ENTER to leave an existing key unchanged."
Write-Host ""

$settings=@{}
if(Test-Path $target){
    $existing=Get-Content -Raw -Encoding UTF8 $target | ConvertFrom-Json
    foreach($name in @("gemini","groq")){
        $prop=$name+"_dpapi"
        if($existing.PSObject.Properties.Name -contains $prop){ $settings[$prop]=$existing.$prop }
    }
}
foreach($provider in @("gemini","groq")){
    $hint=if($provider -eq "gemini"){"https://aistudio.google.com/apikey"}else{"https://console.groq.com/keys"}
    Write-Host "Free $provider key: $hint"
    $secret=Read-Host -AsSecureString "Paste API key for $provider (hidden)"
    if($secret.Length -gt 0){
        $settings[$provider+"_dpapi"]=ConvertFrom-SecureString $secret
        Write-Host "Saved encrypted key for $provider."
    } else {
        Write-Host "No change to $provider."
    }
}
($settings | ConvertTo-Json -Depth 3) | Set-Content -Encoding UTF8 -Path $target
Write-Host ""
Write-Host "Saved local settings to: $target"
Write-Host "Launch run.bat. Do not enable billing in cloud accounts."
