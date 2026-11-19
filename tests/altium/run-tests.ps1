param(
    [string] $Runner = (Join-Path $PSScriptRoot '..\..\odbpp-export\altium\run.ps1'),
    [string] $Scratch = (Join-Path ([IO.Path]::GetTempPath()) ('hefex-altium-tests-' + [guid]::NewGuid().ToString('N')))
)

$ErrorActionPreference = 'Stop'
$runnerPath = (Resolve-Path -LiteralPath $Runner).Path
$fixture = Join-Path $PSScriptRoot 'runner-fixture.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$cases = @(
    @{ Name = 'missing'; Code = 6; Launches = 0 },
    @{ Name = 'multiple'; Code = 4; Launches = 0 },
    @{ Name = 'no-window'; Code = 6; Launches = 0 },
    @{ Name = 'dialog'; Code = 2; Launches = 0 },
    @{ Name = 'locked'; Code = 5; Launches = 1 },
    @{ Name = 'error'; Code = 1; Launches = 2 },
    @{ Name = 'timeout'; Code = 3; Launches = 2 },
    @{ Name = 'done'; Code = 0; Launches = 2 },
    @{ Name = 'done-multi'; Code = 0; Launches = 2 }
)
$results = @()
foreach ($case in $cases) {
    $caseScratch = Join-Path $Scratch $case.Name
    New-Item -ItemType Directory -Path $caseScratch -Force | Out-Null
    $log = Join-Path $caseScratch 'runner.log'
    # Windows PowerShell wraps native stderr as ErrorRecord objects. Capture
    # expected error exits without treating their text as a harness failure.
    try {
        $ErrorActionPreference = 'Continue'
        & $powershell -NoProfile -ExecutionPolicy Bypass -File $fixture -Runner $runnerPath `
            -Scenario $case.Name -Scratch $caseScratch *> $log
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = 'Stop' }
    $launches = Get-Content -LiteralPath (Join-Path $caseScratch 'launches.json') -Raw | ConvertFrom-Json
    $launchCount = if ($null -eq $launches) { 0 } else { $launches.Count }
    $passed = $code -eq $case.Code -and $launchCount -eq $case.Launches
    $results += [pscustomobject]@{ scenario = $case.Name; expected = $case.Code; actual = $code; launches = $launchCount; passed = $passed }
    if ($passed) { Write-Output "PASS $($case.Name): exit $code, $launchCount intercepted launches" }
    else { Write-Output "FAIL $($case.Name): expected exit $($case.Code), got $code; launches $launchCount"; Get-Content -LiteralPath $log }
}
$results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Scratch 'results.json')
Write-Output "Runner: $runnerPath"
Write-Output "Evidence: $Scratch"
if (@($results | Where-Object { -not $_.passed }).Count) { exit 1 }
