param(
    [Parameter(Mandatory=$true)]
    [string]$InputFile,

    [Parameter(Mandatory=$false)]
    [string]$OutputFile = "lambda_test_event.json",

    [Parameter(Mandatory=$false)]
    [int]$MaxWaypoints = 25
)

# ----------------------------------------------------------------------------
# Haversine distance in meters between two [lng, lat] points.
# ----------------------------------------------------------------------------
function Get-HaversineMeters {
    param($lng1, $lat1, $lng2, $lat2)

    $R = 6371000.0
    $phi1 = $lat1 * [Math]::PI / 180.0
    $phi2 = $lat2 * [Math]::PI / 180.0
    $dPhi = ($lat2 - $lat1) * [Math]::PI / 180.0
    $dLambda = ($lng2 - $lng1) * [Math]::PI / 180.0

    $a = [Math]::Pow([Math]::Sin($dPhi / 2), 2) +
         [Math]::Cos($phi1) * [Math]::Cos($phi2) * [Math]::Pow([Math]::Sin($dLambda / 2), 2)
    $c = 2 * [Math]::Atan2([Math]::Sqrt($a), [Math]::Sqrt(1 - $a))

    return $R * $c
}

# ----------------------------------------------------------------------------
# Build a parallel array of cumulative distance (meters) from the start of
# the line up to and including each coordinate.
# ----------------------------------------------------------------------------
function Get-CumulativeDistances {
    param($coordinates)

    $cum = New-Object System.Collections.Generic.List[double]
    $cum.Add(0.0)

    for ($i = 1; $i -lt $coordinates.Count; $i++) {
        $prev = $coordinates[$i - 1]
        $curr = $coordinates[$i]
        $d = Get-HaversineMeters -lng1 $prev[0] -lat1 $prev[1] -lng2 $curr[0] -lat2 $curr[1]
        $cum.Add($cum[$i - 1] + $d)
    }

    return $cum
}

# ----------------------------------------------------------------------------
# Pick up to $count points spaced evenly by DISTANCE along the line, rather
# than evenly by INDEX. This is the fix: a dense cluster of points on a curve
# and a sparse straightaway of the same real-world length now get a
# proportional (not lopsided) share of the sampled waypoints, so drawn-line
# point density no longer needs to be manually managed before conversion.
#
# The first and last points are always kept exactly as the route's real
# start and end. For every target distance in between, we pick the actual
# coordinate whose cumulative distance is closest to that target.
# ----------------------------------------------------------------------------
function Get-EvenlySpacedByDistance {
    param($coordinates, $cumulative, $count)

    $total = $coordinates.Count
    if ($total -le $count) {
        return $coordinates
    }

    $totalDistance = $cumulative[$total - 1]
    $sampled = New-Object System.Collections.Generic.List[object]
    $sampled.Add($coordinates[0])

    $searchStart = 0
    $step = $totalDistance / ($count - 1)

    for ($i = 1; $i -lt ($count - 1); $i++) {
        $targetDist = $i * $step

        # Walk forward from where the previous search left off (cumulative
        # distances are monotonically increasing, so this stays O(n) overall
        # instead of O(n * count)).
        $bestIdx = $searchStart
        $bestDiff = [Math]::Abs($cumulative[$searchStart] - $targetDist)

        for ($j = $searchStart; $j -lt $total; $j++) {
            $diff = [Math]::Abs($cumulative[$j] - $targetDist)
            if ($diff -lt $bestDiff) {
                $bestDiff = $diff
                $bestIdx = $j
            }
            if ($cumulative[$j] -gt $targetDist -and $diff -gt $bestDiff) {
                # Cumulative distance is monotonic, so once we've passed the
                # target and started getting farther away, the best match is
                # already found — stop walking.
                break
            }
        }

        $sampled.Add($coordinates[$bestIdx])
        $searchStart = $bestIdx
    }

    $sampled.Add($coordinates[$total - 1])
    return $sampled
}

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

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

Write-Host "Extracted $($coordinates.Count) coordinates" -ForegroundColor Green

# Sample to max $MaxWaypoints waypoints, evenly spaced by real-world
# distance rather than by point index.
$total = $coordinates.Count
if ($total -gt $MaxWaypoints) {
    $cumulative = Get-CumulativeDistances -coordinates $coordinates
    $totalMeters = $cumulative[$total - 1]

    $coordinates = Get-EvenlySpacedByDistance -coordinates $coordinates -cumulative $cumulative -count $MaxWaypoints

    Write-Host "Sampled down to $($coordinates.Count) waypoints (evenly spaced by distance over $([Math]::Round($totalMeters)) m)" -ForegroundColor Green
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
Write-Host "Lambda test event saved to: $OutputFile" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Copy the contents of $OutputFile"
Write-Host "2. Paste into AWS Lambda test event for 'generate-turn-instructions'"
Write-Host "3. Run the test and copy the response"
Write-Host "4. Use ConvertWaypointsToDynamo.ps1 to convert the response"
