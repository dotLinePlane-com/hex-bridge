param(
    [string]$IdfPath = 'D:/project/esp-idf-v6.0.2',
    [string]$BuildDir = 'build-wifi-final'
)

# Use the real GCC drivers when the chip-specific Rust wrappers cannot resolve
# their executable path under a restricted Windows account. Does not flash.
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path $PSScriptRoot -Parent
$envDump = cmd.exe /c "`"$IdfPath/export.bat`" >nul 2>&1 && set"
if ($LASTEXITCODE -ne 0) { throw 'ESP-IDF export failed' }
foreach ($entry in $envDump) {
    if ($entry -match '^([^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
}
$gcc = (Get-Command xtensa-esp-elf-gcc.exe -ErrorAction Stop).Source
$toolRoot = Split-Path (Split-Path $gcc -Parent) -Parent
$env:XTENSA_GNU_CONFIG = (Join-Path $toolRoot 'lib/xtensa_esp32.so').Replace('\', '/')
if (!(Test-Path -LiteralPath $env:XTENSA_GNU_CONFIG)) { throw 'ESP32 dynconfig missing' }
$env:IDF_CCACHE_ENABLE = '0'
# Scope the SDK ownership exception to this process; do not change git config.
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = $IdfPath.Replace('\', '/')
$buildPath = [IO.Path]::GetFullPath((Join-Path $projectDir $BuildDir))
$toolDir = (Join-Path $buildPath 'gcc-toolchain').Replace('\', '/')
New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
$toolchain = @'
set(_CMAKE_TOOLCHAIN_PREFIX xtensa-esp-elf-)
foreach(_flags cflags cxxflags asmflags ldflags)
 if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/${_flags}")
  file(WRITE "${CMAKE_CURRENT_LIST_DIR}/${_flags}" "-mdynconfig=xtensa_esp32.so\n")
 endif()
endforeach()
include($ENV{IDF_PATH}/tools/cmake/toolchain.cmake)
'@
Set-Content -LiteralPath "$toolDir/toolchain-esp32.cmake" -Value $toolchain
New-Item -ItemType Directory -Force -Path "$toolDir/bootloader" | Out-Null
Set-Content -LiteralPath "$toolDir/bootloader/toolchain-esp32.cmake" -Value $toolchain
$hook = @"
if(BOOTLOADER_BUILD)
 set(CMAKE_TOOLCHAIN_FILE "$toolDir/bootloader/toolchain-esp32.cmake" CACHE FILEPATH "" FORCE)
 set(CMAKE_TOOLCHAIN_FILE "$toolDir/bootloader/toolchain-esp32.cmake")
else()
 set(CMAKE_TOOLCHAIN_FILE "$toolDir/toolchain-esp32.cmake" CACHE FILEPATH "" FORCE)
 set(CMAKE_TOOLCHAIN_FILE "$toolDir/toolchain-esp32.cmake")
endif()
if(COMMAND idf_build_set_property)
 idf_build_set_property(EXTRA_CMAKE_ARGS "-DCMAKE_PROJECT_INCLUDE_BEFORE=$toolDir/before-project.cmake")
endif()
"@
Set-Content -LiteralPath "$toolDir/before-project.cmake" -Value $hook
Push-Location $projectDir
try {
    & idf.py -B $BuildDir -D "CMAKE_PROJECT_INCLUDE_BEFORE=$toolDir/before-project.cmake" build
    if ($LASTEXITCODE -ne 0) { throw "ESP-IDF build failed ($LASTEXITCODE)" }
} finally {
    Pop-Location
}
