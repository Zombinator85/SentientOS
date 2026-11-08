param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1024, 65535)]
    [int]$Port
)

$ErrorActionPreference = "Stop"
$source = @"
using System;
using System.Runtime.InteropServices;

public static class SentientOSGlobalHotkeyNative
{
    [StructLayout(LayoutKind.Sequential)]
    public struct Point
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct Message
    {
        public IntPtr HWnd;
        public UInt32 Value;
        public UIntPtr WParam;
        public IntPtr LParam;
        public UInt32 Time;
        public Point Pt;
    }

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool RegisterHotKey(IntPtr hWnd, int id, uint modifiers, uint key);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern int GetMessage(out Message message, IntPtr hWnd, uint min, uint max);
}
"@

$client = [System.Net.Sockets.UdpClient]::new()
$hotkeyId = 0x534F
$modifiers = [uint32](0x0002 -bor 0x0004 -bor 0x4000)
$keySpace = [uint32]0x20

function Send-HotkeyEvent([string]$Value) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    [void]$client.Send($bytes, $bytes.Length, "127.0.0.1", $Port)
}

try {
    Add-Type -TypeDefinition $source -ErrorAction Stop
    $registered = [SentientOSGlobalHotkeyNative]::RegisterHotKey(
        [IntPtr]::Zero, $hotkeyId, $modifiers, $keySpace)
    if (-not $registered) {
        $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        Send-HotkeyEvent ("registration_failed:" + $code)
        exit 2
    }

    Send-HotkeyEvent "registered"
    $message = New-Object SentientOSGlobalHotkeyNative+Message
    while ($true) {
        $result = [SentientOSGlobalHotkeyNative]::GetMessage(
            [ref]$message, [IntPtr]::Zero, 0, 0)
        if ($result -le 0) {
            break
        }
        if ($message.Value -eq 0x0312 -and
            $message.WParam.ToUInt64() -eq [uint64]$hotkeyId) {
            Send-HotkeyEvent "sentientos.toggle_chat.v1"
        }
    }
}
finally {
    [void][SentientOSGlobalHotkeyNative]::UnregisterHotKey(
        [IntPtr]::Zero, $hotkeyId)
    $client.Dispose()
}
