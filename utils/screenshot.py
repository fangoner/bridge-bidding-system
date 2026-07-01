import subprocess
import time
import os
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import base64

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


SCREENSHOT_DIR = Path(__file__).parent.parent / "screenshots"


def ensure_screenshot_dir():
    if not SCREENSHOT_DIR.exists():
        SCREENSHOT_DIR.mkdir()


def trigger_screenshot_shortcut() -> bool:
    """模拟 Win+Shift+S 系统截屏快捷键"""
    ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# 尝试直接启动截图工具
try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "ms-screenclip:"
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    [System.Diagnostics.Process]::Start($psi)
    Write-Output "LAUNCHED"
    return
} catch {}

# 备用: SendKeys
try {
    [System.Windows.Forms.SendKeys]::SendWait("+(%){s}")
    Write-Output "TRIGGERED"
} catch {
    Write-Output "FAILED"
}
'''
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=5
        )
        if "LAUNCHED" in result.stdout or "TRIGGERED" in result.stdout:
            return True
        return False
    except Exception as e:
        print(f"触发截屏快捷键失败: {e}")
        return False


def read_clipboard_image() -> Optional[Tuple[bytes, str]]:
    """从剪贴板读取图片，返回 (图片数据, 格式)"""
    ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

try {
    $clipboard = [System.Windows.Forms.Clipboard]::GetImage()
    if ($clipboard -ne $null) {
        $ms = New-Object System.IO.MemoryStream
        $clipboard.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $bytes = $ms.ToArray()
        $ms.Close()
        [Convert]::ToBase64String($bytes)
    } else {
        Write-Output "NO_IMAGE"
    }
} catch {
    Write-Output "ERROR: $_"
}
'''
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout.strip()

        if output == "NO_IMAGE":
            return None
        elif output.startswith("ERROR"):
            print(f"读取剪贴板失败: {output}")
            return None
        elif output and len(output) > 100:
            image_data = base64.b64decode(output)
            return (image_data, "png")

        return None
    except Exception as e:
        print(f"读取剪贴板异常: {e}")
        return None
