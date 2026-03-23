param(
    [Parameter(Mandatory=$true)]
    [string]$InputFile,
    
    [Parameter(Mandatory=$false)]
    [string]$OutputFile = "lambda_test_event.json"
)

# Read and parse the input JSON
$content = Get-Content -Path $InputFile -Raw -Encoding UTF8

# Wrap in braces if needed to make valid JSON
if (-not $content.StartsWith("{")) {
    $content = "{" + $content + "}"
}

$data = $content | ConvertFrom-Json

# Determine if this is Route1Geometry or Route1ReturnGeometry
$geometryKey = $null
if ($data.PSObject.Properties.Name -contains "Route1Geometry") {
    $geometryKey = "Route1Geometry"
} elseif ($data.PSObject.Properties.Name -contains "Route1ReturnGeometry") {
    $geometryKey = "Route1ReturnGeometry"
} else {
    Write-Error "Input file must contain Route1Geometry or Route1ReturnGeometry"
    exit 1
}

# Extract coordinates from DynamoDB format
$coordsList = $data.$geometryKey.M.coordinates.L
$coordinates = @()

foreach ($coordObj in $coordsList) {
    $lng = [double]$coordObj.L[0].N
    $lat = [double]$coordObj.L[1].N
    $coordinates += ,@($lng, $lat)
}

Write-Host "✓ Extracted $($coordinates.Count) coordinates" -ForegroundColor Green

# Sample to max 25 waypoints if needed
$total = $coordinates.Count
if ($total -gt 25) {
    $sampled = @()
    $sampled += ,$coordinates[0]  # Start
    
    $step = ($total - 1) / 24.0
    for ($i = 1; $i -lt 24; $i++) {
        $idx = [Math]::Round($i * $step)
        $sampled += ,$coordinates[$idx]
    }
    
    $sampled += ,$coordinates[$total - 1]  # End
    $coordinates = $sampled
    Write-Host "✓ Sampled down to $($coordinates.Count) waypoints" -ForegroundColor Green
}

# Create Lambda test event
$lambdaEvent = @{
    routeGeometry = @{
        type = "LineString"
        coordinates = $coordinates
    }
} | ConvertTo-Json -Depth 10

# Save to output file
$lambdaEvent | Out-File -FilePath $OutputFile -Encoding UTF8

Write-Host ""
Write-Host "✓ Lambda test event saved to: $OutputFile" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Copy the contents of $OutputFile"
Write-Host "2. Paste into AWS Lambda test event for 'generate-turn-instructions'"
Write-Host "3. Run the test and copy the response"
Write-Host "4. Use ConvertWaypointsToDynamo.ps1 to convert the response"
