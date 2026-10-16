$ErrorActionPreference = 'Stop'

$endpoint = (terraform output -raw ai_services_endpoint).TrimEnd('/')
$ocrEndpoint = (terraform output -raw document_intelligence_endpoint).TrimEnd('/')
$failed = $false

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
    $failed = $true
    Write-Host "LANGUAGE PII: FAILED -> $($_.Exception.Message)"
    if ($_.ErrorDetails.Message) { Write-Host ("  detail: " + $_.ErrorDetails.Message) }
}

try {
    $ocrBody = @{
        urlSource = 'https://learn.microsoft.com/azure/ai-services/computer-vision/media/quickstarts/presentation.png'
    } | ConvertTo-Json
    $uri = "$ocrEndpoint/documentintelligence/documentModels/prebuilt-read:analyze?api-version=2024-11-30&stringIndexType=unicodeCodePoint"
    $submission = Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType 'application/json' -Body $ocrBody
    $operationLocation = [string]($submission.Headers['Operation-Location'] | Select-Object -First 1)
    if (-not $operationLocation) { throw 'OCR response omitted Operation-Location.' }
    $deadline = (Get-Date).AddMinutes(2)
    do {
        $ocr = Invoke-RestMethod -Method Get -Uri $operationLocation -Headers $headers
        if ($ocr.status -eq 'succeeded') { break }
        if ($ocr.status -notin @('notStarted', 'running')) {
            throw "OCR operation ended with status '$($ocr.status)': $($ocr.error.message)"
        }
        if ((Get-Date) -ge $deadline) { throw 'OCR operation timed out after two minutes.' }
        Start-Sleep -Seconds 2
    } while ($true)
    $lines = @($ocr.analyzeResult.pages | ForEach-Object { $_.lines })
    if ($lines.Count -eq 0) { throw 'OCR returned no lines for the sample image.' }
    Write-Host "DOCUMENT INTELLIGENCE READ: OK"
    Write-Host ("  lines read: " + $lines.Count)
    Write-Host ("  sample: " + $lines[0].content)
}
catch {
    $failed = $true
    Write-Host "DOCUMENT INTELLIGENCE READ: FAILED -> $($_.Exception.Message)"
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
    $failed = $true
    Write-Host "FOUNDRY PROJECT: FAILED -> $($_.Exception.Message)"
    if ($_.ErrorDetails.Message) { Write-Host ("  detail: " + $_.ErrorDetails.Message) }
}

if ($failed) { throw 'One or more infrastructure smoke checks failed.' }
