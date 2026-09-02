$ErrorActionPreference = 'SilentlyContinue'
$root = 'C:\Users\ethan\Downloads\Roblox-Fastflag-Manager-main\Roblox-Fastflag-Manager-main'
$pyw  = 'C:\Python314\pythonw.exe'
if (-not (Test-Path $pyw)) { Write-Output "NO pythonw at $pyw"; exit 1 }

$env:EXECUTOR_NO_ELEVATE = '1'
$before = @(Get-Process msedgewebview2).Count
$p = Start-Process -FilePath $pyw -ArgumentList ('"' + $root + '\Executor.pyw"') `
     -WorkingDirectory $root -PassThru
Write-Output "launched pythonw pid=$($p.Id)  webview2-before=$before"
Start-Sleep -Seconds 13
$p.Refresh()
Write-Output "pythonw hasExited=$($p.HasExited)"
Write-Output "webview2-after=$(@(Get-Process msedgewebview2).Count)"
Write-Output "----- executor_boot.log -----"
$log = Join-Path $root 'executor_boot.log'
if (Test-Path $log) { Get-Content $log -Raw } else { Write-Output "(no log)" }

Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Get-Process msedgewebview2 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
