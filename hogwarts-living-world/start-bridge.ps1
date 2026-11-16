# Load Windows-DPAPI-protected free cloud keys only into this process.
$ErrorActionPreference = "Stop"
$dir=Join-Path $env:LOCALAPPDATA "HogwartsLivingWorld"
$path=Join-Path $dir "free-keys.dpapi.json"

function Unseal-Key([string]$encrypted){
    if([string]::IsNullOrWhiteSpace($encrypted)){return ""}
    $secure=ConvertTo-SecureString $encrypted
    $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
try {
    if(Test-Path $path){
        $config=Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json
        if($config.gemini_dpapi){$env:GEMINI_API_KEY=Unseal-Key $config.gemini_dpapi}
        if($config.groq_dpapi){$env:GROQ_API_KEY=Unseal-Key $config.groq_dpapi}
    }
    if(-not $env:HLW_REPLY_LANGUAGE){$env:HLW_REPLY_LANGUAGE="ru"}
    if(-not $env:HLW_WATCH_EVENTS){$env:HLW_WATCH_EVENTS="1"}
    Set-Location $PSScriptRoot
    Write-Host ""
    Write-Host "Hogwarts Living World. Cloud-only, no paid provider fallback."
    Write-Host "Go to http://127.0.0.1:8765/health to inspect status."
    if(-not $env:GEMINI_API_KEY -and -not $env:GROQ_API_KEY){
        Write-Host "No cloud keys found. Run setup-free.bat first (or use env variables)."
    }
    $app=Join-Path $PSScriptRoot "HogwartsLivingWorld.exe"
    if(Test-Path $app){
        & $app
    } else {
        & py -3 -m hlw
    }
} finally {
    Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:GROQ_API_KEY -ErrorAction SilentlyContinue
}
