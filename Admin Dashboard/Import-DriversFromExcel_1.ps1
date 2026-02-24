cls

# PowerShell script to import drivers from Excel to DynamoDB JSON format
# Run this script in the same directory as your Excel file

$excelPath = "C:\users\jeremiah\desktop\smpw app\JW - F1 2025 - Master List (Monica).xlsx"
$outputPath = "c:\users\jeremiah\desktop\smpw app\import.json"

# Create Excel COM object
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

try {
    # Open workbook
    Write-Host "Opening Excel file: $excelPath" -ForegroundColor Cyan
    $workbook = $excel.Workbooks.Open((Resolve-Path $excelPath))
    
    # Use the "Master List" sheet (first sheet)
    $worksheet = $workbook.Worksheets.Item("Master List")
    
    # Get the used range
    $usedRange = $worksheet.UsedRange
    $rowCount = $usedRange.Rows.Count
    
    Write-Host "Found $rowCount rows (including header) in 'Master List' sheet" -ForegroundColor Cyan
    
    # Initialize array to hold all drivers
    $drivers = @()
    $addedCount = 0
    $skippedCount = 0
    
    # Process each row (starting from row 2 to skip header)
    # Columns: A=LastName, B=FirstName, C=Co-Pilot, F=Mobile, H=Make, I=Model, K=Pass
    for ($row = 2; $row -le $rowCount; $row++) {
        $lastName = $worksheet.Cells.Item($row, 1).Text.Trim()
        $firstName = $worksheet.Cells.Item($row, 2).Text.Trim()
        $coPilot = $worksheet.Cells.Item($row, 3).Text.Trim()
        $mobile = $worksheet.Cells.Item($row, 6).Text.Trim()
        $make = $worksheet.Cells.Item($row, 8).Text.Trim()
        $model = $worksheet.Cells.Item($row, 9).Text.Trim()
        $numPass = $worksheet.Cells.Item($row, 11).Text.Trim()
        
        # Skip if Make, Model, or # Pass is empty (these should all be valid now)
        if ([string]::IsNullOrWhiteSpace($make) -or 
            [string]::IsNullOrWhiteSpace($model) -or 
            [string]::IsNullOrWhiteSpace($numPass)) {
            $skippedCount++
            Write-Host "Row $row : SKIPPED - $firstName $lastName (missing vehicle info)" -ForegroundColor Yellow
            continue
        }
        
        # Validate seat capacity is a number
        $seatCapacity = 0
        if (-not [int]::TryParse($numPass, [ref]$seatCapacity)) {
            $skippedCount++
            Write-Host "Row $row : SKIPPED - $firstName $lastName (invalid seat capacity: $numPass)" -ForegroundColor Yellow
            continue
        }
        
        # Build full name with co-pilot if present
        # Format: "FirstName & CoPilot LastName" or just "FirstName LastName"
        $fullName = ""
        if (-not [string]::IsNullOrWhiteSpace($coPilot)) {
            $fullName = "$firstName & $coPilot $lastName".Trim()
        } else {
            $fullName = "$firstName $lastName".Trim()
        }
        
        if ([string]::IsNullOrWhiteSpace($fullName)) {
            $skippedCount++
            Write-Host "Row $row : SKIPPED - No name provided" -ForegroundColor Yellow
            continue
        }
        
        # Generate UUID
        $driverId = [guid]::NewGuid().ToString()
        
        # Create DynamoDB item
        $driverItem = @{
            "driverId" = @{
                "S" = $driverId
            }
            "name" = @{
                "S" = $fullName
            }
            "phoneNumber" = @{
                "S" = $mobile
            }
            "make" = @{
                "S" = $make
            }
            "model" = @{
                "S" = $model
            }
            "seatCapacity" = @{
                "N" = $seatCapacity.ToString()
            }
        }
        
        $drivers += $driverItem
        $addedCount++
        Write-Host "Row $row : ADDED - $fullName ($make $model, $seatCapacity seats)" -ForegroundColor Green
    }
    
    # Convert to JSON and save
    Write-Host "`nConverting to JSON..." -ForegroundColor Cyan
    $json = $drivers | ConvertTo-Json -Depth 10
    $json | Out-File -FilePath $outputPath -Encoding UTF8
    
    Write-Host "`n============================================" -ForegroundColor Cyan
    Write-Host "IMPORT SUMMARY" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "Total rows processed: $($rowCount - 1)" -ForegroundColor White
    Write-Host "Drivers added: $addedCount" -ForegroundColor Green
    Write-Host "Rows skipped: $skippedCount" -ForegroundColor Yellow
    Write-Host "Output file: $outputPath" -ForegroundColor White
    Write-Host "============================================" -ForegroundColor Cyan
    
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
} finally {
    # Close workbook and quit Excel
    if ($workbook) {
        $workbook.Close($false)
    }
    $excel.Quit()
    
    # Release COM objects
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($worksheet) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($workbook) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
    
    Write-Host "`nDone! You can now import this file to DynamoDB." -ForegroundColor Cyan
}
