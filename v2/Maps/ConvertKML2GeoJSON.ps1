param(
    [Parameter(Mandatory = $true)]
    [string]$KmlPath,

    # Optional output path; if omitted, writes to stdout
    [string]$OutputPath
)

if (-not (Test-Path $KmlPath)) {
    Write-Error "File not found: $KmlPath"
    exit 1
}

# Load KML as XML
[string]$kmlText = Get-Content -Path $KmlPath -Raw
[xml]$kml = $kmlText

# Handle KML namespace (MyMaps usually uses http://www.opengis.net/kml/2.2)
$ns = New-Object System.Xml.XmlNamespaceManager($kml.NameTable)
$ns.AddNamespace("k", $kml.DocumentElement.NamespaceURI)

# Find all Placemark elements that contain a LineString
$placemarkNodes = $kml.SelectNodes("//k:Placemark[k:LineString]", $ns)

if (-not $placemarkNodes -or $placemarkNodes.Count -eq 0) {
    Write-Error "No Placemark elements with LineString found in KML."
    exit 1
}

$features = @()
$inv = [System.Globalization.CultureInfo]::InvariantCulture

foreach ($pm in $placemarkNodes) {
    # Name, if present
    $nameNode = $pm.SelectSingleNode("k:name", $ns)
    $name = if ($nameNode) { $nameNode.InnerText } else { "" }

    # Coordinates text: "lng,lat,alt lng,lat,alt ..."
    $coordNode = $pm.SelectSingleNode("k:LineString/k:coordinates", $ns)
    if (-not $coordNode) { continue }

    $coordText = $coordNode.InnerText.Trim()
    if ([string]::IsNullOrWhiteSpace($coordText)) { continue }

    $coordTokens = $coordText -split "\s+" | Where-Object { $_ -ne "" }

    $coordArray = @()
    foreach ($token in $coordTokens) {
        # Each token: "lng,lat,alt" OR "lng,lat"
        $parts = $token.Split(',')
        if ($parts.Count -lt 2) { continue }

        $lng = [double]::Parse($parts[0], $inv)
        $lat = [double]::Parse($parts[1], $inv)

        $coordArray += ,@($lng, $lat)
    }

    if ($coordArray.Count -eq 0) { continue }

    $feature = [ordered]@{
        type       = "Feature"
        properties = @{
            name = $name
        }
        geometry   = @{
            type        = "LineString"
            coordinates = $coordArray
        }
    }

    $features += $feature
}

$geojson = [ordered]@{
    type     = "FeatureCollection"
    features = $features
}

$jsonText = $geojson | ConvertTo-Json -Depth 10

if ($OutputPath) {
    $jsonText | Out-File -FilePath $OutputPath -Encoding UTF8
    Write-Host "GeoJSON written to $OutputPath"
} else {
    $jsonText
}
