param(
    [Parameter(Mandatory = $true)]
    [string]$GeoJsonPath,

    # Name of the DynamoDB attribute, e.g. "Route1Geometry" or "Route1ReturnGeometry"
    [string]$AttributeName = "Route1Geometry",

    # Which feature index to use (if there are multiple). Default: 0.
    [int]$FeatureIndex = 0
)

if (-not (Test-Path $GeoJsonPath)) {
    Write-Error "File not found: $GeoJsonPath"
    exit 1
}

# Read & parse GeoJSON
$raw = Get-Content -Path $GeoJsonPath -Raw
$json = $raw | ConvertFrom-Json

if (-not $json.features) {
    Write-Error "No 'features' array found in GeoJSON."
    exit 1
}

# If the requested feature is not a LineString, try to find the first LineString
$feature = $json.features[$FeatureIndex]

if ($feature.geometry.type -ne "LineString") {
    $lineFeature = $json.features | Where-Object { $_.geometry.type -eq "LineString" } | Select-Object -First 1
    if (-not $lineFeature) {
        Write-Error "No LineString geometry found in features."
        exit 1
    }
    $feature = $lineFeature
}

$geom = $feature.geometry

if ($geom.type -ne "LineString") {
    Write-Error "Selected feature is not a LineString."
    exit 1
}

if (-not $geom.coordinates -or $geom.coordinates.Count -eq 0) {
    Write-Error "LineString has no coordinates."
    exit 1
}

# Build DynamoDB JSON for coordinates[]
$invariant = [System.Globalization.CultureInfo]::InvariantCulture
$coordEntries = @()

foreach ($coord in $geom.coordinates) {
    # coord[0] = lng, coord[1] = lat
    $lng = [double]$coord[0]
    $lat = [double]$coord[1]

    $lngStr = $lng.ToString("0.######", $invariant)
    $latStr = $lat.ToString("0.######", $invariant)

    $coordJson = @"
        {
          "L": [
            { "N": "$lngStr" },
            { "N": "$latStr" }
          ]
        }
"@

    $coordEntries += $coordJson.TrimEnd()
}

$coordsJoined = ($coordEntries -join ",`n")

# Final DynamoDB snippet
$snippet = @"
"$AttributeName": {
  "M": {
    "type": { "S": "LineString" },
    "coordinates": {
      "L": [
$coordsJoined
      ]
    }
  }
}
"@

# Output to console (you can redirect to a file)
$snippet | Out-File "C:\users\Jeremiah\Desktop\out.json"
