$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path (Split-Path -Parent $projectRoot) '.venv/Scripts/python.exe'
$runnerPath = Join-Path $projectRoot 'run_local.py'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument ('"' + $runnerPath + '" --daily') -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At '07:00'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Simulative-Diploma-Daily-0700' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Load previous calendar day into diploma PostgreSQL. Local timezone must be Moscow.' -Force | Select-Object TaskName, State
