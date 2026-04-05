import subprocess
import time
import os
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import base64

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm.doubao_client import DoubaoVisionClient


SCREENSHOT_DIR = Path(__file__).parent.parent / "screenshots"


def ensure_screenshot_dir():
    if not SCREENSHOT_DIR.exists():
        SCREENSHOT_DIR.mkdir()


def trigger_screenshot_shortcut() -> bool:
    """模拟 Win+Shift+S 系统截屏快捷键"""
    ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# 方法1: 尝试直接启动截图工具
try {
    # Windows 10/11 使用 ms-screenclip:
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "ms-screenclip:"
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    [System.Diagnostics.Process]::Start($psi)
    Write-Output "LAUNCHED"
    return
} catch {}

# 方法2: 如果上面失败，尝试 SendKeys
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
            print(f"截屏已触发: {result.stdout.strip()}")
            return True
        print(f"截屏触发失败: {result.stdout} {result.stderr}")
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
            print("剪贴板中没有图片")
            return None
        elif output.startswith("ERROR"):
            print(f"读取剪贴板失败: {output}")
            return None
        elif output and len(output) > 100:
            image_data = base64.b64decode(output)
            print(f"从剪贴板读取图片成功，大小: {len(image_data)} bytes")
            return (image_data, "png")
        
        print(f"剪贴板读取结果异常: {output[:100] if output else 'empty'}")
        return None
    except Exception as e:
        print(f"读取剪贴板异常: {e}")
        return None


def capture_edge_window() -> Optional[str]:
    ensure_screenshot_dir()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    screenshot_path = SCREENSHOT_DIR / f"edge_capture_{timestamp}.png"
    
    try:
        import mss
        
        with mss.mss() as sct:
            monitors = sct.monitors
            print(f"检测到显示器: {monitors}")
            
            if len(monitors) >= 3:
                second_monitor = monitors[2]
                print(f"截取第二屏幕: {second_monitor}")
                
                screenshot = sct.grab(second_monitor)
                
                from PIL import Image
                img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                img.save(str(screenshot_path))
                
                print(f"截屏图像大小: {img.size}")
                print(f"截屏已保存: {screenshot_path}")
                
                if screenshot_path.exists():
                    return str(screenshot_path)
            else:
                print("只有一个屏幕，切换到Edge窗口...")
                
                import ctypes
                user32 = ctypes.windll.user32
                
                class RECT(ctypes.Structure):
                    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), 
                               ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                
                EnumWindowsProc = ctypes.WINFUNCTYPE(
                    ctypes.c_bool,
                    ctypes.c_void_p,
                    ctypes.c_void_p
                )
                
                target_hwnd = None
                target_title = None
                
                def enum_callback(hwnd, lParam):
                    nonlocal target_hwnd, target_title
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length == 0:
                        return True
                    
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value
                    title_lower = title.lower()
                    
                    if 'trae' in title_lower or 'visual studio' in title_lower or 'pycharm' in title_lower:
                        return True
                    
                    if ('microsoft edge' in title_lower or 'edge beta' in title_lower or 
                        'edge dev' in title_lower or 'chrome' in title_lower or
                        'bridge' in title_lower or 'bbo' in title_lower or '桥牌' in title_lower or
                        '桥友' in title_lower):
                        target_hwnd = hwnd
                        target_title = title
                        return False
                    
                    return True
                
                user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
                
                if target_hwnd:
                    print(f"找到窗口: {target_title}")
                    
                    SW_MAXIMIZE = 3
                    user32.ShowWindow(target_hwnd, SW_MAXIMIZE)
                    user32.SetForegroundWindow(target_hwnd)
                    
                    print("已最大化窗口，等待1秒...")
                    time.sleep(1)
                    
                    screenshot = sct.grab(sct.monitors[1])
                    
                    from PIL import Image
                    img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                    img.save(str(screenshot_path))
                    
                    print(f"截屏图像大小: {img.size}")
                    print(f"截屏已保存: {screenshot_path}")
                    
                    if screenshot_path.exists():
                        return str(screenshot_path)
                else:
                    print("未找到浏览器窗口")
                    
    except Exception as e:
        print(f"截屏失败: {e}")
        import traceback
        traceback.print_exc()
    
    return None


def capture_window_region(left: int, top: int, width: int, height: int):
    try:
        import mss
        with mss.mss() as sct:
            monitor = {"left": left, "top": top, "width": width, "height": height}
            screenshot = sct.grab(monitor)
            from PIL import Image
            return Image.frombytes('RGB', screenshot.size, screenshot.rgb)
    except ImportError:
        pass
    
    try:
        import pyautogui
        return pyautogui.screenshot(region=(left, top, width, height))
    except Exception as e:
        print(f"区域截屏失败: {e}")
        return None


def capture_all_screens():
    try:
        import mss
        with mss.mss() as sct:
            monitors = sct.monitors
            if len(monitors) > 1:
                all_monitors = {
                    "left": min(m["left"] for m in monitors[1:]),
                    "top": min(m["top"] for m in monitors[1:]),
                    "width": sum(m["width"] for m in monitors[1:]),
                    "height": max(m["height"] for m in monitors[1:]),
                }
                screenshot = sct.grab(all_monitors)
                from PIL import Image
                return Image.frombytes('RGB', screenshot.size, screenshot.rgb)
            else:
                screenshot = sct.grab(sct.monitors[1])
                from PIL import Image
                return Image.frombytes('RGB', screenshot.size, screenshot.rgb)
    except ImportError:
        pass
    
    try:
        import pyautogui
        import tkinter as tk
        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        root.destroy()
        
        return pyautogui.screenshot(region=(0, 0, screen_width, screen_height))
    except Exception as e:
        print(f"截屏失败: {e}")
        return None


def capture_fullscreen_powershell(screenshot_path: Path) -> Optional[str]:
    ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$bitmap = New-Object System.Drawing.Bitmap([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen([System.Drawing.Point]::Empty, [System.Drawing.Point]::Empty, $bitmap.Size)
$bitmap.Save("{screenshot_path}", [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "SUCCESS"
'''
    
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if "SUCCESS" in result.stdout and screenshot_path.exists():
            return str(screenshot_path)
        
        print(f"截屏失败: {result.stderr}")
        return None
        
    except Exception as e:
        print(f"截屏异常: {e}")
        return None


def capture_active_window() -> Optional[str]:
    ensure_screenshot_dir()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    screenshot_path = SCREENSHOT_DIR / f"active_window_{timestamp}.png"
    
    try:
        screenshot = capture_all_screens()
        if screenshot:
            screenshot.save(str(screenshot_path))
            if screenshot_path.exists():
                return str(screenshot_path)
        return None
    except Exception as e:
        print(f"截屏异常: {e}")
        return capture_fullscreen_powershell(screenshot_path)


def capture_region(x: int, y: int, width: int, height: int) -> Optional[str]:
    ensure_screenshot_dir()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    screenshot_path = SCREENSHOT_DIR / f"region_{timestamp}.png"
    
    ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$rect = New-Object System.Drawing.Rectangle({x}, {y}, {width}, {height})
$bitmap = New-Object System.Drawing.Bitmap($rect.Width, $rect.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($rect.Location, [System.Drawing.Point]::Empty, $rect.Size)
$bitmap.Save("{screenshot_path}", [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "SUCCESS"
'''
    
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if "SUCCESS" in result.stdout and screenshot_path.exists():
            return str(screenshot_path)
        
        return None
        
    except Exception as e:
        print(f"区域截屏异常: {e}")
        return None


BRIDGE_EXTRACTION_PROMPT = """你的任务是从桥牌游戏图片中提取信息：

1. 四位牌手的手牌
2. 当前的叫牌序列（如果有显示）
3. 当前定约（如果有显示）

重要规则：
- 牌面10必须用T表示，例如：♠KT85 而不是 ♠K1085
- 叫牌序列必须从庄家（dealer）开始，严格按照叫牌顺序列出
- 每个叫品必须准确对应其位置（南/西/北/东）
- 所有叫品都必须记录，包括开头的pass和结尾的pass
- 最终定约叫品之后通常还有三个pass结束叫牌，也可能有加倍/再加倍，必须全部记录
- 叫牌顺序是顺时针：南→西→北→东→南→...
- 仔细观察叫牌区域，确定每个叫品对应的位置，不要混淆相邻位置的叫品

请严格按照以下JSON格式输出：
{
  "南家手牌": "花色符号+牌面，如 ♠KT85 ♥AT863 ♦Q42 ♣63，牌面10用T表示",
  "西家手牌": "...",
  "北家手牌": "...",
  "东家手牌": "...",
  "叫牌序列": ["北:pass", "东:pass", "南:1NT", "西:pass", "北:2D", "东:pass", "南:pass", "西:pass"]，从庄家开始完整记录所有叫品，如果未显示则为null,
  "当前定约": "如 4H 由南做庄，如果未显示则为null",
  "页面类型": "BBO/桥友圈/桥牌教程书籍/新睿桥牌/其他"
}"""


class BridgeScreenshotCapture:
    def __init__(self):
        self.vision_client = DoubaoVisionClient()
    
    def capture_and_analyze(self, capture_type: str = "fullscreen") -> Dict[str, Any]:
        if capture_type == "edge":
            screenshot_path = capture_edge_window()
        elif capture_type == "fullscreen":
            screenshot_path = capture_active_window()
        else:
            screenshot_path = capture_active_window()
        
        if not screenshot_path:
            return {"error": "截屏失败"}
        
        print(f"截屏已保存: {screenshot_path}")
        
        if not self.vision_client.is_configured():
            return {
                "error": "豆包API未配置",
                "screenshot_path": screenshot_path
            }
        
        print("正在识别牌局信息...")
        result = self._analyze_screenshot(screenshot_path)
        result["screenshot_path"] = screenshot_path
        
        return result
    
    def _analyze_screenshot(self, screenshot_path: str) -> Dict[str, Any]:
        try:
            with open(screenshot_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            response = self.vision_client.client.chat.completions.create(
                model=self.vision_client.endpoint,
                messages=[
                    {
                        "role": "system",
                        "content": BRIDGE_EXTRACTION_PROMPT
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0
            )
            
            result_text = response.choices[0].message.content
            
            import json
            try:
                if "```json" in result_text:
                    json_match = result_text.split("```json")[1].split("```")[0]
                elif "```" in result_text:
                    json_match = result_text.split("```")[1].split("```")[0]
                else:
                    json_match = result_text
                
                return json.loads(json_match.strip())
            except json.JSONDecodeError:
                return {"raw_response": result_text, "error": "JSON解析失败"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def analyze_existing_image(self, image_path: str) -> Dict[str, Any]:
        if not os.path.exists(image_path):
            return {"error": f"图片文件不存在: {image_path}"}
        
        if not self.vision_client.is_configured():
            return {"error": "豆包API未配置"}
        
        print(f"正在分析图片: {image_path}")
        return self._analyze_screenshot(image_path)
