param(
    [Parameter(Mandatory=$true)][ValidateSet('install','start','stop','status')][string]$Action,
    [string]$ServiceName = 'SentientOS'
)
$servicePath = (Join-Path $PSScriptRoot '..\..\sentientosd.py' | Resolve-Path)
switch ($Action) {
  'install' {
    if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) {
      New-Service -Name $ServiceName -BinaryPathName "python.exe $servicePath" -DisplayName 'SentientOS Autonomy' -Description 'SentientOS Autonomy Runtime' -StartupType Automatic | Out-Null
    }
    Start-Service -Name $ServiceName
  }
  'start' { Start-Service -Name $ServiceName }
  'stop' { Stop-Service -Name $ServiceName }
  'status' {
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($null -eq $svc) { Write-Output "Service $ServiceName not installed" }
    else { Write-Output "Status: $($svc.Status)" }
  }
}
