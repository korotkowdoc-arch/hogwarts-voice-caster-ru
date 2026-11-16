$ErrorActionPreference="Stop"
$url="http://127.0.0.1:8765"
Write-Host "Testing free embedding compatibility. Sends ONE short text to Gemini (unless cached)."
$health=Invoke-RestMethod -Uri "$url/health" -TimeoutSec 5
if(-not $health.long_term_embeddings.model){
    throw "Embeddings are disabled. Close run.bat; launch run-with-memory.bat."
}
$body=@{model="text-embedding-3-small";input="Мы с Себастьяном обсуждали библиотеку.";encoding_format="base64"} | ConvertTo-Json
$r=Invoke-RestMethod -Method Post -Uri "$url/v1/embeddings" -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType "application/json" -TimeoutSec 35
if($r.data.Count -ne 1 -or -not $r.data[0].embedding){
    throw "Unexpected embedding response"
}
$bytes=[Convert]::FromBase64String([string]$r.data[0].embedding)
if($bytes.Length -ne 1536*4){
    throw "Embedding size mismatch: expected 1536 x float32"
}
Write-Host "SUCCESS: 1536-dimensional free Gemini vector returned."
Write-Host "Sonorus Memory > Enable Long-Term Memory may now be switched on."
Write-Host "Model name in Sonorus stays text-embedding-3-small (local compatibility alias)."
