param([string]$Player="story_demo")
$ErrorActionPreference="Stop"
$uri="http://127.0.0.1:8765"
Write-Host "Hogwarts Living World: offline scripted narrative test."
Write-Host "No cloud calls. No game files modified. Only local test profile."
if($Player -notmatch '^[A-Za-z0-9_.-]{1,64}$'){throw "Invalid test profile ID"}
$nonce=[guid]::NewGuid().ToString("N")
$events=@(
    @{npc="sebastian";event="player_helped"},
    @{npc="sebastian";event="player_helped"},
    @{npc="sebastian";event="meeting_accepted"},
    @{npc="sebastian";event="meeting_attended"},
    @{npc="sebastian";event="secret_revealed_to_ominis"},
    @{npc="sebastian";event="apology_accepted"},
    @{npc="ominis";event="meeting_attended"},
    @{npc="poppy";event="player_helped"},
    @{npc="poppy";event="meeting_attended"}
)
$index=0
foreach($action in $events){
    $index++
    $json=@{
        player_id=$Player
        npc_id=$action.npc
        event=$action.event
        event_id=("scenario_"+$nonce+"_"+$index)
    } | ConvertTo-Json
    $result=Invoke-RestMethod -Method Post -Uri "$uri/v1/world/event" -Body ([Text.Encoding]::UTF8.GetBytes($json)) -ContentType "application/json"
    Write-Host "$index. $($action.npc): $($action.event) => affinity $($result.affinity), trust $($result.trust)"
}
Write-Host ""
foreach($npc in @("sebastian","ominis","poppy")){
    $story=Invoke-RestMethod "$uri/v1/world/story?player_id=$Player&npc_id=$npc"
    Write-Host "$npc stages:" ($story.completed_milestones -join ", ")
}
$queue=Invoke-RestMethod "$uri/v1/world/outbox?player_id=$Player"
Write-Host ""
Write-Host "Proposed events (NOT executed inside Hogwarts Legacy):"
$queue.events | Select-Object id,npc_id,kind | Format-Table -AutoSize
Write-Host "Visit $uri and choose profile $Player to review the same saved relationships."
