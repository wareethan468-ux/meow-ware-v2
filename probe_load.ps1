$ErrorActionPreference = 'SilentlyContinue'
$dir = 'C:\Users\ethan\Downloads\Roblox-Fastflag-Manager-main\Roblox-Fastflag-Manager-main\dist-dbg\Executor'
$exe = Join-Path $dir 'Executor.exe'
$out = Join-Path $dir '__probe.out'
$err = Join-Path $dir '__probe.err'
Remove-Item $out,$err -Force -ErrorAction SilentlyContinue

$p = Start-Process -FilePath $exe -WorkingDirectory $dir -PassThru `
     -RedirectStandardOutput $out -RedirectStandardError $err
Start-Sleep -Seconds 9
$p.Refresh()

if ($p.HasExited) {
    Write-Output "RESULT: EXITED-EARLY code=$($p.ExitCode)"
} else {
    Write-Output "RESULT: ALIVE pid=$($p.Id) mainWindowTitle=[$($p.MainWindowTitle)]"
    $wv = @(Get-Process msedgewebview2 -ErrorAction SilentlyContinue)
    Write-Output "webview2-children: $($wv.Count)"
    Get-Process | Where-Object {
        $_.MainWindowTitle -match 'Ordinal|not be located|valid Win32|Application Error|System Error'
    } | ForEach-Object { Write-Output "ERROR-DIALOG: $($_.ProcessName) [$($_.MainWindowTitle)]" }
    # kill the app and any webview children spawned
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    $wv | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
}
Write-Output "----- STDOUT -----"
if (Test-Path $out) { Get-Content $out -Raw } else { Write-Output "(none)" }
Write-Output "----- STDERR -----"
if (Test-Path $err) { Get-Content $err -Raw } else { Write-Output "(none)" }
