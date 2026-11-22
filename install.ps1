# Установщик rb-tui для Windows.
#
#   irm https://raw.githubusercontent.com/JeySerYT/rb-tui/main/install.ps1 | iex
#
# Переменные:
#   RB_TUI_REPO         owner/repo (по умолч. JeySerYT/rb-tui)
#   RB_TUI_VERSION      версия без v (по умолч. latest)
#   RB_TUI_INSTALL_DIR  куда ставить rb-tui.exe
#                       (по умолч. %LOCALAPPDATA%\rb-tui\bin)
#   RB_TUI_BASE_URL     свой базовый URL вместо GitHub (для тестов)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repo = if ($env:RB_TUI_REPO) { $env:RB_TUI_REPO } else { "JeySerYT/rb-tui" }
$version = if ($env:RB_TUI_VERSION) { $env:RB_TUI_VERSION } else { "latest" }
$installDir = if ($env:RB_TUI_INSTALL_DIR) {
    $env:RB_TUI_INSTALL_DIR
} else {
    Join-Path $env:LOCALAPPDATA "rb-tui\bin"
}
$base = if ($env:RB_TUI_BASE_URL) {
    $env:RB_TUI_BASE_URL.TrimEnd("/")
} else {
    "https://github.com/$repo/releases"
}
if ($version -eq "latest") {
    # У проектов только с бетами нет /releases/latest — берём первый из API.
    try {
        $releases = @(Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases?per_page=1" -UseBasicParsing)
        if ($releases.Count -eq 0) { throw "нет релизов" }
        $url = "$base/download/$($releases[0].tag_name)"
    } catch {
        throw "не удалось получить последний релиз $repo : $_"
    }
} else {
    $url = "$base/download/v$($version.TrimStart("v"))"
}

$asset = "rb-tui-windows-x86_64.zip"
$tmp = Join-Path $env:TEMP ("rb-tui-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null

try {
    Write-Host "==> скачиваю $asset"
    Invoke-WebRequest -Uri "$url/$asset" -OutFile (Join-Path $tmp $asset) -UseBasicParsing
    Invoke-WebRequest -Uri "$url/$asset.sha256" -OutFile (Join-Path $tmp "$asset.sha256") -UseBasicParsing

    $checksumFile = Join-Path $tmp "$asset.sha256"
    $expected = (Get-Content $checksumFile -Raw).Trim().Split()[0].ToLower()
    $actual = (Get-FileHash (Join-Path $tmp $asset) -Algorithm SHA256).Hash.ToLower()
    if ($expected -ne $actual) {
        throw "контрольная сумма не совпала"
    }
    Write-Host "==> контрольная сумма ok"

    # Снять Mark-of-the-Web: иначе при первом запуске SmartScreen ругается.
    Unblock-File -Path (Join-Path $tmp $asset) -ErrorAction SilentlyContinue
    Expand-Archive -Path (Join-Path $tmp $asset) -DestinationPath $tmp -Force
    Unblock-File -Path (Join-Path $tmp "rb-tui.exe") -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    Copy-Item (Join-Path $tmp "rb-tui.exe") (Join-Path $installDir "rb-tui.exe") -Force
    Unblock-File -Path (Join-Path $installDir "rb-tui.exe") -ErrorAction SilentlyContinue

    if ([Environment]::OSVersion.Platform -eq "Win32NT") {
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $parts = @()
        if ($userPath) { $parts = $userPath -split ";" | Where-Object { $_ } }
        if (-not ($parts | Where-Object { $_.TrimEnd([char]"\") -ieq $installDir.TrimEnd([char]"\") })) {
            $newPath = (@($parts) + $installDir) -join ";"
            [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
            $env:Path = "$env:Path;$installDir"
            Write-Host "==> добавлено в PATH: $installDir"
            Write-Host "    перезапусти терминал, чтобы PATH обновился"
        }
    }

    Write-Host "==> установлено: $(Join-Path $installDir 'rb-tui.exe')"
    if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
        Write-Host "    Windows ARM64: используется x64-сборка через эмуляцию"
    }
    Write-Host "    бинарник не подписан: если SmartScreen предупредит,"
    Write-Host "    нажми «Подробнее» → «Выполнить в любом случае»"
    if ([Environment]::OSVersion.Platform -eq "Win32NT") {
        & (Join-Path $installDir "rb-tui.exe") --version
    }
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}