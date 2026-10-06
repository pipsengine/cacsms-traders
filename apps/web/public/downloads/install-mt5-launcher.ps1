param(
    [ValidateSet('Install', 'Open')][string]$Mode = 'Install',
    [string]$TerminalPath
)
$ErrorActionPreference = 'Stop'
$launcherDirectory = Join-Path $env:LOCALAPPDATA 'CacsmsTraders\MT5Launcher'
$launcherFile = Join-Path $launcherDirectory 'mt5-launcher.ps1'
$configurationFile = Join-Path $launcherDirectory 'terminal.json'

function Resolve-Mt5Terminal([string]$Candidate) {
    if (-not $Candidate) { throw 'Select your installed broker MT5 terminal64.exe.' }
    $terminalItem = Get-Item -LiteralPath $Candidate
    if ($terminalItem.PSIsContainer -or $terminalItem.Name -ine 'terminal64.exe') {
        throw 'The selected file must be your installed broker terminal64.exe.'
    }
    return $terminalItem.FullName
}

try {
    if ($Mode -eq 'Install') {
        if (-not $TerminalPath) {
            $runningTerminals = @(Get-Process -Name terminal64 -ErrorAction SilentlyContinue | ForEach-Object { $_.Path } | Where-Object { $_ } | Sort-Object -Unique)
            if ($runningTerminals.Count -eq 1) { $TerminalPath = $runningTerminals[0] }
            else {
                Add-Type -AssemblyName System.Windows.Forms
                $picker = New-Object System.Windows.Forms.OpenFileDialog
                $picker.Title = 'Select your broker MT5 terminal64.exe'
                $picker.Filter = 'MetaTrader 5 terminal (terminal64.exe)|terminal64.exe'
                $picker.InitialDirectory = $env:ProgramFiles
                if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 0 }
                $TerminalPath = $picker.FileName
                $picker.Dispose()
            }
        }
        $validatedTerminal = Resolve-Mt5Terminal $TerminalPath
        New-Item -ItemType Directory -Path $launcherDirectory -Force | Out-Null
        if ($PSCommandPath -ne $launcherFile) { Copy-Item -LiteralPath $PSCommandPath -Destination $launcherFile -Force }
        @{ terminal_path = $validatedTerminal } | ConvertTo-Json | Set-Content -LiteralPath $configurationFile -Encoding UTF8
        $protocolKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Software\Classes\cacsms-mt5')
        try {
            $protocolKey.SetValue('', 'URL:Cacsms Traders MT5 Launcher')
            $protocolKey.SetValue('URL Protocol', '')
            $commandKey = $protocolKey.CreateSubKey('shell\open\command')
            try {
                $powershellExecutable = Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
                # Fixed arguments only. Browser URI contents never become commands or executable paths.
                $commandKey.SetValue('', ('"{0}" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}" -Mode Open' -f $powershellExecutable, $launcherFile))
            } finally { $commandKey.Dispose() }
        } finally { $protocolKey.Dispose() }
        Write-Host 'MT5 launcher installed for your Windows user. Return to Cacsms Traders and select Open MT5 or Connect.'
        Write-Host 'This launcher opens the terminal only. It does not connect market data or enable trading.'
    } else {
        $configuration = Get-Content -LiteralPath $configurationFile -Raw | ConvertFrom-Json
        $validatedTerminal = Resolve-Mt5Terminal $configuration.terminal_path
        $existingTerminal = Get-Process -Name terminal64 -ErrorAction SilentlyContinue | Where-Object { $_.Path -ieq $validatedTerminal } | Select-Object -First 1
        if ($existingTerminal) {
            if ($existingTerminal.MainWindowHandle -ne [IntPtr]::Zero) {
                if (-not ('CacsmsMt5Desktop' -as [type])) {
                    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class CacsmsMt5Desktop {
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
}
'@
                }
                [void][CacsmsMt5Desktop]::ShowWindowAsync($existingTerminal.MainWindowHandle, 9)
                [void][CacsmsMt5Desktop]::SetForegroundWindow($existingTerminal.MainWindowHandle)
            }
            $desktopShell = New-Object -ComObject WScript.Shell
            [void]$desktopShell.AppActivate($existingTerminal.Id)
        } else {
            Start-Process -FilePath $validatedTerminal -WorkingDirectory (Split-Path -LiteralPath $validatedTerminal) -WindowStyle Normal
        }
    }
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Cacsms Traders MT5 Launcher')
    exit 1
}
