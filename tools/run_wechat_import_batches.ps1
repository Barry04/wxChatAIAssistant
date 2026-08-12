param(
    [int]$Start = 0,
    [int]$End = 478,
    [int]$BatchSize = 10,
    [int]$Workers = 2
)

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$importer = Join-Path $PSScriptRoot "import_wechat_history.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

for ($offset = $Start; $offset -lt $End; $offset += $BatchSize) {
    $limit = [Math]::Min($BatchSize, $End - $offset)
    Write-Host ("Starting batch start={0}, limit={1}" -f $offset, $limit)
    & $python $importer `
        --start $offset `
        --limit $limit `
        --workers $Workers `
        --no-distill
    if ($LASTEXITCODE -ne 0) {
        throw "Batch start=$offset failed; coverage report was preserved"
    }
}

Write-Host "Batch import finished. Run distill_self_skill separately."
