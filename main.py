import tkinter as tk
import asyncio
from bleak import BleakClient
from bleak import BleakScanner
import threading
import math
import time
from PIL import Image, ImageDraw, ImageTk
import numpy as np

# 标准心率服务UUID
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_CHARACTERISTIC_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

# 全局变量
current_hr = 0  # 当前心率值
hr_history = []  # 心率历史记录
MAX_HISTORY = 50  # 最多存储50个点（约50秒数据）
dragging = False  # 是否正在拖动小部件
drag_x = 0
drag_y = 0
is_connected = False  # 连接状态标志

class HeartRateWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("❤️ 心率监测")
        self.root.geometry("240x240+100+100")  # 缩小尺寸
        self.root.overrideredirect(True)  # 移除窗口边框
        self.root.attributes('-topmost', True)  # 窗口置顶
        self.root.attributes('-transparentcolor', 'black')  # 设置透明背景
        self.root.configure(bg='black')
        
        # 创建心形遮罩
        self.create_heart_mask()
        
        # 创建画布
        self.canvas = tk.Canvas(root, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 绑定鼠标事件
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drag)
        self.canvas.bind("<Enter>", self.on_enter)
        self.canvas.bind("<Leave>", self.on_leave)
        
        # 创建关闭按钮
        self.close_btn = tk.Label(root, text="✕", font=("Arial", 9), 
                                 bg="#ff5555", fg="white", bd=0, relief="flat")
        self.close_btn.place(x=210, y=10, width=18, height=18)  # 调整位置
        self.close_btn.bind("<Button-1>", lambda e: root.destroy())
        
        # 绘制初始界面
        self.draw_widget()
        
        # 启动更新循环
        self.update_ui()
    
    def create_heart_mask(self):
        """创建透明心形窗口遮罩"""
        # 创建心形图像
        size = 240  # 缩小尺寸
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # 使用参数方程绘制心形
        points = []
        t_values = np.linspace(0, 2 * np.pi, 200)
        
        for t in t_values:
            # 标准心形参数方程
            x = 16 * (np.sin(t) ** 3)
            y = 13 * np.cos(t) - 5 * np.cos(2*t) - 2 * np.cos(3*t) - np.cos(4*t)
            
            # 缩放并移动到中心
            x = int(x * 5.6 + size/2)  # 按比例缩小
            y = int(-y * 5.6 + size/2) # 按比例缩小
            
            points.append((x, y))
        
        # 绘制心形并填充
        draw.polygon(points, fill="#ff2255")
        
        # 添加内部渐变效果
        for i in range(60):  # 减少层数以提高性能
            # 创建内部稍小的心形
            inner_points = []
            for (x, y) in points:
                # 向中心收缩
                dx = x - size/2
                dy = y - size/2
                dist = math.sqrt(dx*dx + dy*dy)
                if dist > 0:
                    scale = 1 - i/150
                    nx = size/2 + dx * scale
                    ny = size/2 + dy * scale
                    inner_points.append((nx, ny))
            
            # 选择渐变色
            r = min(255, 255 - i)
            g = min(255, 70 - i//2)
            b = min(255, 100 - i//2)
            alpha = max(50, 255 - i*4)  # 逐渐增加透明度
            color = (r, g, b, alpha)
            draw.polygon(inner_points, fill=color)
        
        # 转换为Tkinter图像
        self.heart_photo = ImageTk.PhotoImage(image)
    
    def draw_widget(self):
        """绘制小部件内容"""
        self.canvas.delete("all")
        
        # 绘制心形背景
        self.canvas.create_image(120, 120, image=self.heart_photo)  # 中心位置调整
        
        # 绘制心率值 - 大字体
        hr_text = f"{current_hr}" if current_hr > 0 else "--"
        text_color = "#ffffff" if current_hr > 0 else "#aaaaaa"
        self.canvas.create_text(120, 95, text=hr_text,  # 位置调整
                               font=("Arial", 48, "bold"),  # 字体缩小
                               fill=text_color, tags="hr_text")
        
        # 绘制BPM - 小字体
        self.canvas.create_text(120, 130, text="BPM",  # 位置调整
                               font=("Arial", 16),  # 字体缩小
                               fill=text_color, tags="bpm_text")
        
        # 绘制状态文本
        status = self.get_status_text(current_hr)
        self.canvas.create_text(120, 160, text=status,  # 位置调整
                               font=("Arial", 12),  # 字体缩小
                               fill=text_color)
        
        # 绘制实际心率曲线
        if len(hr_history) > 1:
            self.draw_real_heartrate()
    
    def draw_real_heartrate(self):
        """绘制实际心率变化曲线"""
        # 确定绘制区域 (心形底部)
        graph_y = 190  # 位置调整
        graph_height = 30  # 高度减小
        
        # 找到心率范围
        if len(hr_history) > 0:
            min_hr = min(hr_history)
            max_hr = max(hr_history)
            hr_range = max(max_hr - min_hr, 10)  # 确保有足够范围
        else:
            min_hr = 60
            max_hr = 100
            hr_range = 40
        
        # 绘制曲线
        points = []
        for i, hr in enumerate(hr_history):
            # 计算位置
            x = 10 + (i / len(hr_history)) * 220  # 宽度调整
            y = graph_y - ((hr - min_hr) / hr_range) * graph_height
            
            points.append(x)
            points.append(y)
        
        if points:
            # 绘制曲线
            self.canvas.create_line(points, fill="#ffffff", width=2, smooth=True)  # 线宽减小
            
            # 绘制当前点
            last_x = points[-2]
            last_y = points[-1]
            self.canvas.create_oval(last_x-3, last_y-3, 
                                   last_x+3, last_y+3, 
                                   fill="#ff5555", outline="#ffffff", width=1)
    
    def get_status_text(self, hr):
        """获取心率状态描述"""
        global is_connected
        
        if not is_connected:
            return "未连接"
        if hr <= 0:
            return "等待数据..."
        elif hr < 60:
            return "心率偏低"
        elif hr <= 100:
            return "正常心率"
        elif hr <= 120:
            return "轻度活动"
        elif hr <= 150:
            return "中等运动"
        else:
            return "高强度"
    
    def update_ui(self):
        """更新UI"""
        self.draw_widget()
        self.root.after(100, self.update_ui)  # 每秒更新10次
    
    def start_drag(self, event):
        """开始拖动窗口"""
        global dragging, drag_x, drag_y
        dragging = True
        drag_x = event.x
        drag_y = event.y
    
    def on_drag(self, event):
        """拖动窗口"""
        if dragging:
            x = self.root.winfo_x() + (event.x - drag_x)
            y = self.root.winfo_y() + (event.y - drag_y)
            self.root.geometry(f"+{x}+{y}")
    
    def stop_drag(self, event):
        """停止拖动"""
        global dragging
        dragging = False
    
    def on_enter(self, event):
        """鼠标进入时增加透明度"""
        self.root.attributes('-alpha', 0.97)
        self.close_btn.config(bg="#ff0000")  # 悬停时关闭按钮变红
    
    def on_leave(self, event):
        """鼠标离开时恢复透明度"""
        self.root.attributes('-alpha', 0.92)
        self.close_btn.config(bg="#ff5555")  # 离开时恢复原色

def hr_data_handler(_, data: bytearray):
    """解析心率数据并更新全局变量"""
    global current_hr, hr_history, is_connected
    
    # 解析标准心率数据格式
    flags = data[0]
    hr_value = data[1]
    
    # 更新当前心率
    current_hr = hr_value
    
    # 添加到历史记录
    hr_history.append(hr_value)
    
    # 保持历史记录不超过最大值
    if len(hr_history) > MAX_HISTORY:
        hr_history.pop(0)
    
    # 确保连接状态标志为真
    is_connected = True

async def connect_to_watch():
    """连接手表并监听心率数据"""
    global current_hr, is_connected, hr_history
    
    print(f"⌚ 连接至设备 {device_mac}...")
    
    # 添加重连机制
    while True:
        try:
            async with BleakClient(device_mac) as client:
                print("✅ 连接成功！监听心率中...")
                is_connected = True
                await client.start_notify(HR_CHARACTERISTIC_UUID, hr_data_handler)
                
                # 持续运行直到连接断开
                while client.is_connected:
                    await asyncio.sleep(1)
                
                # 连接断开后重置状态
                print("❌ 连接断开")
                is_connected = False
                current_hr = 0
                hr_history.clear()
                
        except Exception as e:
            print(f"连接失败: {e}")
            is_connected = False
            current_hr = 0  # 重置心率值
            hr_history.clear()
            
            # 等待一段时间后重试
            await asyncio.sleep(5)

def bluetooth_thread():
    """蓝牙连接线程"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(connect_to_watch())

async def scan_ble_devices():
    """
    扫描并列出所有可发现的小米BLE设备
    """
    print("⏳ 正在扫描蓝牙设备... (约需10秒)")
    
    # 扫描蓝牙设备（默认10秒）
    devices = await BleakScanner.discover()
    
    if not devices:
        print("\n❌ 未找到任何蓝牙设备")
        return
    
    # 过滤名称中包含'xiaomi'或'小米'的设备
    xiaomi_devices = [device for device in devices 
                      if device.name and ('xiaomi' in device.name.lower() or '小米' in device.name)]
    
    if not xiaomi_devices:
        print("\n❌ 未找到任何小米蓝牙设备")
        return
    
    print(f"\n✅ 发现 {len(xiaomi_devices)} 个小米蓝牙设备:")
    print("=" * 70)
    print(f"{'序号':<5} | {'设备名称':<25} | {'MAC地址':<20} | {'信号强度(RSSI)':<15}")
    print("-" * 70)
    
    for i, device in enumerate(xiaomi_devices, 1):
        # 处理设备名称为空的情况
        name = device.name if device.name else "Unknown"
        
        # 获取信号强度（部分设备可能不提供）
        rssi = device.rssi if hasattr(device, 'rssi') and device.rssi is not None else "N/A"
        
        print(f"{i:<5} | {name[:24]:<25} | {device.address:<20} | {rssi:<15}")
        return device.address  
    print("=" * 70)
    print("💡 提示：MAC地址格式为 XX:XX:XX:XX:XX:XX")
    print("🔍 信号强度(RSSI)说明：值越大表示信号越好（0 > -30 > -60 > -90）")


if __name__ == "__main__":
    # 替换为你的手表MAC地址
        # 运行扫描

    #device_mac = "E6:16:A8:8A:7A:68"
    device_mac=asyncio.run(scan_ble_devices())
    # 初始化主窗口
    root = tk.Tk()
    
    # 启动蓝牙线程
    bt_thread = threading.Thread(target=bluetooth_thread, daemon=True)
    bt_thread.start()
    
    # 创建小部件
    widget = HeartRateWidget(root)
    
    # 启动主循环
    root.mainloop()
