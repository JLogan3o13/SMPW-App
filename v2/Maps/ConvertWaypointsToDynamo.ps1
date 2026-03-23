param(
    [Parameter(Mandatory=$true)]
    [string]$InputFile,
    
    [Parameter(Mandatory=$true)]
    [ValidateSet("routeInstructions", "returnRouteInstructions")]
    [string]$AttributeName,
    
    [Parameter(Mandatory=$false)]
    [string]$OutputFile
)

# Default output filename based on attribute name
if (-not $OutputFile) {
    $OutputFile = "$AttributeName.json"
}

# Read the Lambda response
$content = Get-Content -Path $InputFile -Raw -Encoding UTF8

# The Lambda response might be wrapped in quotes or have "instructions": prefix
# Try to extract just the instructions array
if ($content -match '"instructions"\s*:\s*(\[.*\])') {
    $instructionsJson = $matches[1]
} elseif ($content -match '(\[.*\])') {
    $instructionsJson = $matches[1]
} else {
    Write-Error "Could not find instructions array in input file"
    exit 1
}

# Parse the instructions
$instructions = $instructionsJson | ConvertFrom-Json

Write-Host "✓ Parsed $($instructions.Count) instructions" -ForegroundColor Green

# Convert to DynamoDB format
function ConvertTo-DynamoInstruction {
    param($inst)
    
    $result = @{
        M = @{
            distance = @{ N = $inst.distance.ToString() }
            duration = @{ N = $inst.duration.ToString() }
            instruction = @{ S = $inst.instruction }
            maneuver = @{
                M = @{
                    type = @{ S = $inst.maneuver.type }
                    location = @{
                        L = @(
                            @{ N = $inst.maneuver.location[0].ToString() },
                            @{ N = $inst.maneuver.location[1].ToString() }
                        )
                    }
                    bearing_after = @{ N = $inst.maneuver.bearing_after.ToString() }
                    bearing_before = @{ N = $inst.maneuver.bearing_before.ToString() }
                }
            }
            name = @{ S = if ($inst.name) { $inst.name } else { "" } }
        }
    }
    
    # Add modifier if present
    if ($inst.maneuver.PSObject.Properties.Name -contains "modifier") {
        $result.M.maneuver.M.modifier = @{ S = $inst.maneuver.modifier }
    }
    
    return $result
}

# Convert all instructions
$dynamoInstructions = @()
foreach ($inst in $instructions) {
    $dynamoInstructions += ConvertTo-DynamoInstruction -inst $inst
}

# Create the final output
$output = @{
    $AttributeName = @{
        L = $dynamoInstructions
    }
} | ConvertTo-Json -Depth 20

# Save to file
$output | Out-File -FilePath $OutputFile -Encoding UTF8

Write-Host "✓ Converted $($dynamoInstructions.Count) instructions to DynamoDB format" -ForegroundColor Green
Write-Host "✓ Saved to: $OutputFile" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Open DynamoDB console"
Write-Host "2. Find your item (RaidersGames / Zone E)"
Write-Host "3. Copy contents of $OutputFile"
Write-Host "4. Paste into the '$AttributeName' attribute"
