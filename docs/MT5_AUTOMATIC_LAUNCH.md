# Automatic MT5 terminal opening

On a Windows gateway, **Connect** starts the configured broker `terminal64.exe`
before attempting the Python SDK connection. An existing matching process is
reused. Launching is separate from authorization and execution; a missing SDK can
prevent the connection while the terminal still opens. Non-MT5 executables are
refused. Status reads do not launch applications.

For the hosted website, install the desktop launcher once on the Windows PC where
MT5 is installed. The installer is served at `/downloads/install-mt5-launcher.ps1`.
From Windows PowerShell, run the downloaded file:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\install-mt5-launcher.ps1"
```

It reuses the sole running terminal when possible; otherwise a file picker asks
you to select the broker's installed `terminal64.exe`. An explicit path can also
be supplied with `-TerminalPath "C:\Program Files\Your Broker MT5\terminal64.exe"`.
No broker credentials are requested or stored.

The installer copies the launcher into the current user's LocalAppData directory
and registers `cacsms-mt5://` under that user's `Software\Classes`. No administrator
installation is needed. The protocol runs a fixed launcher command: web-supplied
URLs cannot specify executables, terminal paths or command arguments.

After installation, **Connect** or **Open MT5 on this PC** requests the local
terminal opening. Accept the browser's external-application prompt. The browser
cannot confirm that the terminal actually opened, so the UI reports a request
rather than a successful market-data connection. An already-running configured
terminal is activated instead of spawning another copy.

This launcher is not the remote market-data bridge. The hosted API still needs an
authenticated Windows gateway to consume that terminal's data. Opening MT5 does
not migrate accounts, bind execution or change **ANALYSIS ONLY**.

The existing gateway connect route retains its tenant/RBAC checks. Unsupported
API hosts report `MT5_DESKTOP_COMPANION_REQUIRED` rather than suggesting that
installing the MT5 Python package on a cloud API will open a client's desktop.

Verification includes launcher unit tests, Windows PowerShell syntax parsing and
the frontend production build. Installer registration and the browser-to-terminal
flow require installation on the target Windows desktop and are not exercised by
unit tests.

Windows protocol handlers are the mechanism described by Microsoft's
[URI activation documentation](https://learn.microsoft.com/en-us/windows/apps/develop/launch/handle-uri-activation).
