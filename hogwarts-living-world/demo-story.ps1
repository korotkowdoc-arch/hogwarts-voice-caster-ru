param([string]$Player="demo_save", [string]$Npc="sebastian")
$ErrorActionPreference = "Stop"
$root = "http://127.0.0.1:8765"
Write-Host "Hogwarts Living World demo. NO GAME FILES WILL BE MODIFIED."
$health=Invoke-RestMethod "$root/health"
Write-Host "Bridge:" $health.version "| configured providers:" ($health.configured_providers -join ",")
$nonce=[guid]::NewGuid().ToString("N")
for($i=1;$i -le 2;$i++){
    $payload=@{player_id=$Player; npc_id=$Npc; event="player_helped"; event_id=("test_"+$nonce+"_"+$i)} | ConvertTo-Json
    $result=Invoke-RestMethod -Method Post -Uri "$root/v1/world/event" -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($payload))
    Write-Host "Event $i => affinity:" $result.affinity "trust:" $result.trust
}
$events=Invoke-RestMethod "$root/v1/world/outbox?player_id=$Player"
$events.events | ConvertTo-Json -Depth 7
Write-Host ""
Write-Host "These are proposals only. No NPC moved, and no owl was sent in Hogwarts Legacy."
