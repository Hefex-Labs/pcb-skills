# Hefex Labs: run one DelphiScript procedure in the open Altium instance, safely.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File run.ps1 -ScriptProject <PrjScr> -Proc "<file>.pas>Proc" -StatusFile <txt> [-TimeoutSec 180]
#
# Exit codes: 0 status file ends with done, 1 status file has an error: line,
# 2 a dialog is open in Altium (before or during the run), 3 timeout, 4 several Altium processes,
# 5 status file locked, 6 Altium not running or without main window.
param(
    [Parameter(Mandatory)] [string] $ScriptProject,
    [Parameter(Mandatory)] [string] $Proc,
    [Parameter(Mandatory)] [string] $StatusFile,
    [int] $TimeoutSec = 180,
    [string] $X2 = ''
)

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

function Get-AltiumExe {
    if ($X2) { return $X2 }
    $running = Get-Process X2 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($running -and $running.Path) { return $running.Path }
    $dirs = Get-ChildItem 'C:\Program Files\Altium' -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName 'X2.EXE') } | Sort-Object Name
    if (-not $dirs) { throw 'X2.EXE not found' }
    return (Join-Path $dirs[-1].FullName 'X2.EXE')
}

# Titles of top-level Altium windows other than the main window: dialogs.
function Get-AltiumDialogs {
    $A = [System.Windows.Automation.AutomationElement]
    $result = @()
    foreach ($p in Get-Process X2 -ErrorAction SilentlyContinue) {
        $cond = New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, $p.Id)
        foreach ($w in $A::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)) {
            $name = $w.Current.Name
            if ($name -and ($name -notmatch 'Altium Designer')) {
                $text = @()
                foreach ($e in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)) {
                    if ($e.Current.Name) { $text += $e.Current.Name }
                }
                $result += ("{0}: {1}" -f $name, (($text | Select-Object -Unique) -join ' | '))
            }
        }
    }
    return $result
}

$exe = Get-AltiumExe
$procs = @(Get-Process X2 -ErrorAction SilentlyContinue)
# Started by a script, Altium once came up without any window; the user starts it.
if ($procs.Count -eq 0) { "error: Altium is not running; ask the user to start it and wait for its main window"; exit 6 }
if ($procs.Count -gt 1) { "error: several Altium processes ($($procs.Id -join ', '))"; exit 4 }
# Process.MainWindowTitle is often empty although Altium is up; look for the window itself.
$A = [System.Windows.Automation.AutomationElement]
$cond = New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, $procs[0].Id)
$main = @($A::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $cond) |
    Where-Object { $_.Current.Name -match 'Altium Designer' })
if (-not $main) { "error: Altium has no main window yet (still starting?)"; exit 6 }
$d = Get-AltiumDialogs
if ($d) { "error: dialog open"; $d | ForEach-Object { "dialog: $_" }; exit 2 }
# Clears a script paused in the debugger; harmless otherwise.
Start-Process -Wait -FilePath $exe -ArgumentList '-REditScript:Stop'
Start-Sleep -Seconds 3

# A script stopped mid-run can keep its status file open; a new run would then
# fail on it with a modal I/O error. Refuse instead.
if (Test-Path $StatusFile) {
    try { Remove-Item $StatusFile -Force -ErrorAction Stop }
    catch { "error: status file locked ($StatusFile); restart Altium or use another file"; exit 5 }
}
# Start-Process keeps the quotes intact; Git Bash and cmd mangle them, and Altium
# then starts a second instance that only reports "another instance is busy".
$arg = '-RScriptingSystem:RunScript(ProjectName="{0}"|ProcName="{1}")' -f $ScriptProject, $Proc
Start-Process -FilePath $exe -ArgumentList $arg
"started: $Proc"

$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    if (Test-Path $StatusFile) {
        $lines = Get-Content $StatusFile
        if ($lines | Where-Object { $_ -like 'error:*' }) { $lines; exit 1 }
        if ($lines -and ($lines[-1] -eq 'done')) { $lines; exit 0 }
    }
    $d = Get-AltiumDialogs
    if ($d) {
        "error: dialog open during run"
        $d | ForEach-Object { "dialog: $_" }
        if (Test-Path $StatusFile) { Get-Content $StatusFile }
        exit 2
    }
}
"error: timeout"
if (Test-Path $StatusFile) { Get-Content $StatusFile }
exit 3
