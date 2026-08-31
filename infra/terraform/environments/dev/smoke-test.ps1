$ErrorActionPreference = 'Stop'

# Vision OCR and Language PII are served by the same multi-service AI Services account.
$endpoint = (terraform output -raw ai_services_endpoint).TrimEnd('/')

$token = az account get-access-token --resource 'https://cognitiveservices.azure.com' --query accessToken -o tsv
$headers = @{ Authorization = "Bearer $token" }

# --- Azure AI Language: PII detection + redaction ---
$body = @{
    kind          = 'PiiEntityRecognition'
    parameters    = @{ modelVersion = 'latest' }
    analysisInput = @{
        documents = @(
            @{
                id       = '1'
                language = 'en'
                text     = "Jane Doe's card number is 5555 4444 3333 1111 and her email is jane.doe@contoso.com."
            }
        )
    }
} | ConvertTo-Json -Depth 10

try {
    $uri = "$endpoint/language/:analyze-text?api-version=2023-04-01"
    $r = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' -Body $body
    Write-Host "LANGUAGE PII: OK"
    Write-Host ("  redacted: " + $r.results.documents[0].redactedText)
    Write-Host ("  entities: " + (($r.results.documents[0].entities | ForEach-Object { $_.category }) -join ', '))
}
catch {
    Write-Host "LANGUAGE PII: FAILED -> $($_.Exception.Message)"
    if ($_.ErrorDetails.Message) { Write-Host ("  detail: " + $_.ErrorDetails.Message) }
}

# --- Azure AI Vision: Image Analysis / OCR read ---
$visionBody = @{ url = 'https://learn.microsoft.com/azure/ai-services/computer-vision/media/quickstarts/presentation.png' } | ConvertTo-Json

try {
    # api-version 2024-02-01 is not served by this account and returns a misleading 401.
    $uri = "$endpoint/computervision/imageanalysis:analyze?api-version=2023-10-01&features=read"
    $v = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' -Body $visionBody
    $lines = $v.readResult.blocks[0].lines
    Write-Host "VISION OCR: OK"
    Write-Host ("  lines read: " + $lines.Count)
    Write-Host ("  sample: " + $lines[0].text)
}
catch {
    Write-Host "VISION OCR: FAILED -> $($_.Exception.Message)"
    if ($_.ErrorDetails.Message) { Write-Host ("  detail: " + $_.ErrorDetails.Message) }
}

# --- Foundry project: confirm the account is a Foundry resource with a project ---
try {
    $accountId = terraform output -raw ai_services_id
    $armToken = az account get-access-token --resource 'https://management.azure.com' --query accessToken -o tsv
    $uri = "https://management.azure.com$accountId/projects?api-version=2025-06-01"
    $p = Invoke-RestMethod -Method Get -Uri $uri -Headers @{ Authorization = "Bearer $armToken" }
    Write-Host "FOUNDRY PROJECT: OK"
    foreach ($project in $p.value) {
        Write-Host ("  " + $project.name + " (default: " + $project.properties.isDefault + ")")
        Write-Host ("  endpoint: " + $project.properties.endpoints.'AI Foundry API')
    }
}
catch {
    Write-Host "FOUNDRY PROJECT: FAILED -> $($_.Exception.Message)"
    if ($_.ErrorDetails.Message) { Write-Host ("  detail: " + $_.ErrorDetails.Message) }
}
