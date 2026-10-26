param(
  [Parameter(Mandatory = $true)]
  [string]$StorageAccount,
  [string]$ResourceGroup = 'finsight-prod-rg',
  [string]$Registry = 'finsightregistry61459',
  [string]$Container = 'finsightdata'
)

$ErrorActionPreference = 'Stop'

function Invoke-Az([string[]]$Arguments) {
  $result = & az @Arguments
  if ($LASTEXITCODE -ne 0) {
    $safeArguments = New-Object System.Collections.Generic.List[string]
    for ($index = 0; $index -lt $Arguments.Count; $index++) {
      $safeArguments.Add($Arguments[$index])
      if ($Arguments[$index] -in @('--connection-string', '--secrets')) {
        $index++
        $safeArguments.Add('<redacted>')
      }
    }
    throw "Azure CLI command failed: az $($safeArguments -join ' ')"
  }
  return $result
}

$imageTag = ((& git rev-parse HEAD) -join "`n").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($imageTag)) {
  throw 'Could not determine the current Git commit for the container image tag.'
}

$connectionArgs = @(
  'storage', 'account', 'show-connection-string',
  '--resource-group', $ResourceGroup,
  '--name', $StorageAccount,
  '--query', 'connectionString',
  '--output', 'tsv'
)
$connectionString = ((Invoke-Az $connectionArgs) -join "`n").Trim()
if ([string]::IsNullOrWhiteSpace($connectionString)) {
  throw 'Azure returned an empty Blob Storage connection string.'
}

Invoke-Az @(
  'storage', 'container', 'create',
  '--name', $Container,
  '--connection-string', $connectionString,
  '--output', 'none'
) | Out-Null

foreach ($app in @(
  @{ Name = 'finsight-api'; Image = 'finsight-api' },
  @{ Name = 'finsight-worker'; Image = 'finsight-worker' }
)) {
  Write-Host "Configuring $($app.Name)..."
  Invoke-Az @(
    'containerapp', 'secret', 'set',
    '--name', $app.Name,
    '--resource-group', $ResourceGroup,
    '--secrets', "azure-storage-connection=$connectionString",
    '--output', 'none'
  ) | Out-Null

  Invoke-Az @(
    'containerapp', 'update',
    '--name', $app.Name,
    '--resource-group', $ResourceGroup,
    '--image', "$Registry.azurecr.io/$($app.Image):$imageTag",
    '--set-env-vars',
    'STORAGE_BACKEND=azure_blob',
    'AZURE_STORAGE_CONNECTION_STRING=secretref:azure-storage-connection',
    "AZURE_STORAGE_CONTAINER=$Container",
    '--output', 'none'
  ) | Out-Null
}

Write-Host ''
Write-Host 'Blob storage configured and the API/worker images updated.' -ForegroundColor Green
Write-Host 'Wait for the new revisions to become healthy, then upload the workbook again.'
