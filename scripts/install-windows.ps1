<#
.SYNOPSIS
  Ярлыки запуска демона micPy на Windows: автозагрузка + рабочий стол.

.DESCRIPTION
  Запускайте из обычного PowerShell (не из песочницы Claude Desktop — она
  виртуализирует %APPDATA%, и ярлык в автозагрузке не будет виден системе).

  Что делает:
    1. создаёт ярлык MicPy в папке автозагрузки (shell:startup);
    2. создаёт ярлык "MicPy Voice" на рабочем столе;
    3. перезапускает демон (останавливает старый pythonw из этого venv).

  Конфиг (сервер, хоткей) берётся из ~\.config\micpy\.env — эта папка
  не виртуализируется. Лог демона без консоли: ~\.cache\micpy\daemon.log

.PARAMETER RepoDir
  Каталог с клонированным репозиторием и .venv (по умолчанию — родитель scripts\).

.PARAMETER NoStart
  Только создать ярлыки, демон не запускать.
#>
param(
    [string]$RepoDir = (Split-Path -Parent $PSScriptRoot),
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'

$pythonw = Join-Path $RepoDir '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) {
    throw "Не найден $pythonw. Создайте venv: python -m venv .venv; .venv\Scripts\pip install -e ."
}

$shell = New-Object -ComObject WScript.Shell

function New-MicpyShortcut([string]$path) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = '-m client.cli daemon'
    $lnk.WorkingDirectory = $RepoDir
    $lnk.WindowStyle = 7          # свёрнуто; окна у pythonw всё равно нет
    $lnk.Description = 'micPy: голосовой ввод по глобальному хоткею'
    $lnk.Save()
    Write-Host "Ярлык: $path"
}

New-MicpyShortcut (Join-Path ([Environment]::GetFolderPath('Startup')) 'MicPy.lnk')
New-MicpyShortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) 'MicPy Voice.lnk')

$envFile = Join-Path $HOME '.config\micpy\.env'
if (-not (Test-Path $envFile)) {
    Write-Warning "Нет $envFile — демон возьмёт настройки по умолчанию (localhost:5092). См. README."
}

# Перезапуск: гасим только pythonw из этого venv
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.ExecutablePath -eq $pythonw } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "Остановлен старый демон (PID $($_.ProcessId))" }

if (-not $NoStart) {
    Start-Process -FilePath $pythonw -ArgumentList '-m', 'client.cli', 'daemon' -WorkingDirectory $RepoDir
    Write-Host 'Демон запущен. Лог: ~\.cache\micpy\daemon.log'
}
