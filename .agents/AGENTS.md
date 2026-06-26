# Windows Rust/Python Hybrid Development Guidelines

1. **Target Folder Exclusions**:
   - In hybrid Rust/Python codebases on Windows, Windows Defender may lock `.rcgu.o` and `.rmeta` files in cargo target directories.
   - If a build fails with `os error 32 (access denied/file in use)`, run `Remove-Item -Recurse -Force "path/to/target"` and advise the user to exclude the cargo `target/` directory in Windows Security settings.

2. **PyO3 Extension Upgrades & Maturin**:
   - If `maturin develop` fails with "cannot overwrite the installed extension module", stop all python processes (`Get-Process | Where-Object {$_.Name -match 'python|cargo'} | Stop-Process -Force`) and remove the stale directory `C:\Aletheia\.venv\Lib\site-packages\~letheia_rust` before retrying.

3. **Windows Python Execution**:
   - Never run raw `python` or `pytest` in terminal commands on Windows workspaces. Always run using `.venv\Scripts\python.exe` or `.venv\Scripts\pytest` explicitly to prevent escaping the virtual environment.
