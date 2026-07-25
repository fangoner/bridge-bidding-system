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
    """启动系统截图工具"""
    # os.startfile 直接通过 ShellExecute 打开协议URL
    try:
        import os as _os
        _os.startfile("ms-screenclip:")
        print("[INFO] os.startfile ms-screenclip: 成功")
        return True
    except Exception as e:
        print(f"[INFO] os.startfile 失败: {e}")

    # cmd /c start 备用
    try:
        subprocess.run(["cmd", "/c", "start", "", "ms-screenclip:"],
                       capture_output=True, timeout=5)
        print("[INFO] cmd start ms-screenclip: 成功")
        return True
    except Exception as e:
        print(f"[INFO] cmd start 失败: {e}")

    print("[ERROR] 所有触发方式均失败")
    return False


def read_clipboard_image() -> Optional[Tuple[bytes, str]]:
    """从剪贴板读取图片，返回 (图片数据, 格式)"""
    import time as _time
    t0 = _time.time()

    # 方法1: PIL ImageGrab 直接读剪贴板（最可靠）
    try:
        from PIL import ImageGrab
        img = ImageGrab.grabclipboard()
        if img is not None:
            import io as _io
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            image_data = buf.getvalue()
            print(f"[DIAG] PIL ImageGrab 成功: {len(image_data)}字节 PNG, 耗时={_time.time()-t0:.1f}s")
            return (image_data, "png")
        print(f"[DIAG] PIL ImageGrab: 剪贴板无图片")
    except Exception as e:
        print(f"[DIAG] PIL ImageGrab 失败: {e}")

    # 方法2: PowerShell System.Drawing 备用
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
        import subprocess as _sp
        t1 = _time.time()
        result = _sp.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10
        )
        elapsed = _time.time() - t1
        output = result.stdout.strip()
        print(f"[DIAG] PowerShell: 耗时={elapsed:.1f}s, 输出长度={len(output)}")

        if output == "NO_IMAGE":
            print(f"[DIAG] PowerShell: 剪贴板无图片 (总{_time.time()-t0:.1f}s)")
            return None
        elif output.startswith("ERROR"):
            print(f"[DIAG] PowerShell 失败: {output}")
            return None
        elif output and len(output) > 100:
            import base64 as _b64
            image_data = _b64.b64decode(output)
            print(f"[DIAG] PowerShell: {len(image_data)}字节 PNG (总{_time.time()-t0:.1f}s)")
            return (image_data, "png")

        print(f"[DIAG] PowerShell: 未知输出")
        return None
    except Exception as e:
        print(f"[DIAG] PowerShell 异常: {e}")
        return None
