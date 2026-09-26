# 源码为UTF-8，资源路径从本脚本目录计算。
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$sourceRoot = $PSScriptRoot
$iconPath = Join-Path $sourceRoot 'assets\personal-suite.ico'
$assetPath = Join-Path $sourceRoot 'assets'
$sourcePath = Join-Path $sourceRoot '小程序集合.py'
$buildOutput = Join-Path $sourceRoot '打包输出'
$buildWork = Join-Path $sourceRoot '打包临时'
python -m PyInstaller --noconfirm --onefile --windowed --name '小程序集合' --icon $iconPath --add-data "$assetPath;assets" --distpath $buildOutput --workpath $buildWork --specpath $buildWork $sourcePath
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
