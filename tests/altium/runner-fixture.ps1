param(
    [Parameter(Mandatory)] [string] $Runner,
    [Parameter(Mandatory)] [string] $Scenario,
    [Parameter(Mandatory)] [string] $Scratch
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $Scratch -Force | Out-Null
$global:FixtureStatus = Join-Path $Scratch 'status.txt'
$global:FixtureCalls = Join-Path $Scratch 'launches.json'
$global:FixtureScenario = $Scenario
$global:FixtureNow = [datetime]'2026-01-01T00:00:00'
$global:FixtureLaunches = @()
Set-Content -LiteralPath $global:FixtureCalls -Value '[]'

# Model only the UI Automation surface read by run.ps1. No real windows are
# inspected, and every process launch is intercepted below.
Add-Type -TypeDefinition @'
namespace System.Windows.Automation {
    public enum TreeScope { Children, Descendants }
    public class Condition { public static Condition TrueCondition = new Condition(); }
    public class PropertyCondition : Condition { public PropertyCondition(object p, int id) {} }
    public class Information { public string Name; }
    public class AutomationElement {
        public static object ProcessIdProperty = new object();
        public static AutomationElement RootElement = new AutomationElement();
        public static AutomationElement[] Windows = new AutomationElement[0];
        public Information Current = new Information();
        public AutomationElement[] FindAll(TreeScope scope, Condition condition) {
            return object.ReferenceEquals(this, RootElement) ? Windows : new AutomationElement[0];
        }
    }
}
'@
$windows = @()
if ($Scenario -ne 'no-window') {
    $main = New-Object System.Windows.Automation.AutomationElement
    $main.Current.Name = 'Synthetic Altium Designer'
    $windows += $main
}
if ($Scenario -eq 'dialog') {
    $dialog = New-Object System.Windows.Automation.AutomationElement
    $dialog.Current.Name = 'Synthetic question'
    $windows += $dialog
}
[System.Windows.Automation.AutomationElement]::Windows = $windows

function Add-Type { param([string[]] $AssemblyName) } # Do not load desktop UI Automation.
function Get-Process {
    [CmdletBinding()] param([string] $Name)
    if ($Name -ne 'X2') { throw "Unexpected process lookup: $Name" }
    if ($global:FixtureScenario -eq 'missing') { return @() }
    $process = [pscustomobject]@{ Id = 123456; Path = 'C:\fixture-only\X2.EXE' }
    if ($global:FixtureScenario -eq 'multiple') { return @($process, $process) }
    return $process
}
function Get-ChildItem {
    [CmdletBinding()] param([string] $Path, [switch] $Directory)
    if ($Path -ne 'C:\Program Files\Altium') { throw "Unexpected file lookup: $Path" }
    return @()
}
function Start-Process {
    [CmdletBinding()] param([string] $FilePath, [string] $ArgumentList, [switch] $Wait)
    if ($FilePath -ne 'C:\fixture-only\X2.EXE') { throw "Unexpected executable: $FilePath" }
    $global:FixtureLaunches += $ArgumentList
    ConvertTo-Json -InputObject @($global:FixtureLaunches) -Compress |
        Set-Content -LiteralPath $global:FixtureCalls
    if ($ArgumentList -like '-RScriptingSystem:*') {
        if ($global:FixtureScenario -eq 'done') { Set-Content -LiteralPath $global:FixtureStatus -Value 'done' }
        if ($global:FixtureScenario -eq 'done-multi') {
            Set-Content -LiteralPath $global:FixtureStatus -Value @('fixture started', 'done')
        }
        if ($global:FixtureScenario -eq 'error') {
            Set-Content -LiteralPath $global:FixtureStatus -Value 'error: synthetic_failure'
        }
    }
}
function Get-Date { return $global:FixtureNow }
function Start-Sleep { param([int] $Seconds); $global:FixtureNow = $global:FixtureNow.AddSeconds($Seconds) }

$lock = $null
try {
    if ($Scenario -eq 'locked') {
        $lock = [IO.File]::Open($global:FixtureStatus, [IO.FileMode]::Create, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    }
    & $Runner -ScriptProject (Join-Path $Scratch 'fixture.PrjScr') -Proc 'fixture.pas>Export' `
        -StatusFile $global:FixtureStatus -TimeoutSec 9
    exit $LASTEXITCODE
}
finally {
    if ($lock) { $lock.Dispose() }
}
