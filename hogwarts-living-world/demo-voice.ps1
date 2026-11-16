param(
    [string]$Text="Привет! Как проходит твой день в Хогвартсе?",
    [ValidateSet("Kore","Puck","Charon","Aoede")][string]$Voice="Kore",
    [ValidateSet("neutral","warm","tense")][string]$Style="warm"
)
$ErrorActionPreference="Stop"
$url="http://127.0.0.1:8765/v1/voice/preview"
$dest=Join-Path $PSScriptRoot "hlw-voice-preview.wav"
$body=@{text=$Text;voice=$Voice;style=$Style} | ConvertTo-Json
Write-Host "Cloud Gemini TTS preview. Only if enabled in free account."
Invoke-WebRequest -Uri $url -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body)) -OutFile $dest
Write-Host "Saved:" $dest
$player=New-Object System.Media.SoundPlayer($dest)
$player.PlaySync()
