param(
    [Parameter(Mandatory = $true)]
    [int64]$WindowHandle
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Runtime.WindowsRuntime

Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class WxChatWindowRect {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
}
"@

function Await-WinRT {
    param(
        [Parameter(Mandatory = $true)]$Operation,
        [Parameter(Mandatory = $true)][Type]$ResultType
    )

    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        } |
        Select-Object -First 1
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

$rect = New-Object WxChatWindowRect+RECT
if (-not [WxChatWindowRect]::GetWindowRect([IntPtr]$WindowHandle, [ref]$rect)) {
    throw "Unable to read WeChat window rectangle"
}

$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -lt 600 -or $height -lt 400) {
    throw "WeChat window is too small for guarded title recognition"
}

# Capture only the right-pane title bar. Never capture the message list or composer.
$cropX = $rect.Left + [Math]::Round($width * 0.28)
$cropY = $rect.Top
$cropWidth = [Math]::Max(1, [Math]::Round($width * 0.48))
$cropHeight = [Math]::Max(1, [Math]::Round($height * 0.12))
$tempPath = Join-Path ([System.IO.Path]::GetTempPath()) (
    "wxchat-title-" + [Guid]::NewGuid().ToString("N") + ".png"
)

$bitmap = New-Object System.Drawing.Bitmap $cropWidth, $cropHeight
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($cropX, $cropY, 0, 0, $bitmap.Size)
    $bitmap.Save($tempPath, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}

try {
    $storageFileType = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $randomAccessStreamType = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $bitmapDecoderType = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
    $softwareBitmapType = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
    $ocrResultType = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]
    $ocrEngineType = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $languageType = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]
    $fileAccessModeType = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]

    $storageFile = Await-WinRT ($storageFileType::GetFileFromPathAsync($tempPath)) $storageFileType
    $stream = Await-WinRT ($storageFile.OpenAsync($fileAccessModeType::Read)) $randomAccessStreamType
    try {
        $decoder = Await-WinRT ($bitmapDecoderType::CreateAsync($stream)) $bitmapDecoderType
        $softwareBitmap = Await-WinRT ($decoder.GetSoftwareBitmapAsync()) $softwareBitmapType
        try {
            $language = New-Object $languageType("zh-Hans-CN")
            $engine = $ocrEngineType::TryCreateFromLanguage($language)
            if ($null -eq $engine) {
                throw "Simplified Chinese Windows OCR is unavailable"
            }
            $result = Await-WinRT ($engine.RecognizeAsync($softwareBitmap)) $ocrResultType
            [pscustomobject]@{
                text = [string]$result.Text
                lines = @($result.Lines | ForEach-Object { [string]$_.Text })
            } | ConvertTo-Json -Compress
        } finally {
            if ($softwareBitmap -is [IDisposable]) {
                $softwareBitmap.Dispose()
            }
        }
    } finally {
        if ($stream -is [IDisposable]) {
            $stream.Dispose()
        }
    }
} finally {
    Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
}
