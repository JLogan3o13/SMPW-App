param(
    [Parameter(Mandatory=$true)]
    [string]$InputFile
)
$kml = [xml](Get-Content $($InputFile) -Raw)
$ns = New-Object System.Xml.XmlNamespaceManager($kml.NameTable)
$ns.AddNamespace("k", $kml.DocumentElement.NamespaceURI)
$coordText = $kml.SelectSingleNode("//k:LineString/k:coordinates", $ns).InnerText
$points = ($coordText.Trim() -split "\s+")
Write-Host "Points: $($points.Count)"

function Get-Meters($lng1,$lat1,$lng2,$lat2) {
    $R = 6371000.0
    $p1 = $lat1*[Math]::PI/180; $p2 = $lat2*[Math]::PI/180
    $dp = ($lat2-$lat1)*[Math]::PI/180; $dl = ($lng2-$lng1)*[Math]::PI/180
    $a = [Math]::Sin($dp/2)*[Math]::Sin($dp/2) + [Math]::Cos($p1)*[Math]::Cos($p2)*[Math]::Sin($dl/2)*[Math]::Sin($dl/2)
    return $R * 2 * [Math]::Atan2([Math]::Sqrt($a), [Math]::Sqrt(1-$a))
}

$coords = $points | ForEach-Object { ($_ -split ",")[0..1] | ForEach-Object {[double]$_} }
$total = 0.0
for ($i = 2; $i -lt $points.Count*2; $i += 2) {
    $total += Get-Meters $coords[$i-2] $coords[$i-1] $coords[$i] $coords[$i+1]
}
Write-Host "Total length: $([Math]::Round($total)) m"
Write-Host "Avg spacing: $([Math]::Round($total / $points.Count, 1)) m/point"