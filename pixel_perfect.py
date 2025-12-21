import sys
import time
import os
import json
from datetime import datetime
from PyQt5.QtCore import QRectF

# 设备检测相关导入
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# 设备检测库导入（可选）
# 如果需要更好的音频设备检测，可以安装 pycaw: pip install pycaw
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False
    print("DEBUG: pycaw 未安装，无法检测音频设备")

# 添加音频录制相关导入
try:
    import pyaudiowpatch as pyaudio
    HAS_PYAUDIO_WPATCH = True
except ImportError:
    HAS_PYAUDIO_WPATCH = False
    print("DEBUG: pyaudiowpatch 未安装，无法录制系统音频")

# 添加全局快捷键相关导入
try:
    from pynput import keyboard
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False
    print("DEBUG: pynput 未安装，无法使用全局快捷键")

import subprocess
import threading

# Windows API 相关导入（用于实现点击穿透和窗口枚举）
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    
    # Windows 常量
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x80000
    WS_EX_TRANSPARENT = 0x20
    WS_EX_TOOLWINDOW = 0x80
    
    # 窗口枚举相关常量
    GWL_STYLE = -16
    WS_VISIBLE = 0x10000000
    WS_MINIMIZE = 0x20000000
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    
    # 窗口检查相关常量
    SMTO_ABORTIFHUNG = 0x0002
    WM_NULL = 0x0000
    SW_SHOWMINIMIZED = 2
    SW_SHOW = 5
    GWL_HWNDPARENT = -8

# PyQt5 相关导入
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QMessageBox, QDesktopWidget,
    QCheckBox, QComboBox, QLineEdit, QGroupBox, QSpinBox, QScrollArea,
    QMenu, QAction, QKeySequenceEdit, QFormLayout, QSizePolicy, QDialog
)
from PyQt5.QtCore import Qt, QPoint, QTimer, QSettings, pyqtSignal, QThread, QRect
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QKeySequence, QImage, QPen, QBrush, QColor, QCursor, QRegion


class RoundedMenu(QMenu):
    """自定义圆角下拉菜单 - 修复方角投影/描边问题"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 设置窗口属性，启用透明背景
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        
    def paintEvent(self, event):
        """自定义绘制事件 - 实现完整的圆角效果"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        
        # 步骤1: 清除系统默认背景
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(self.rect(), Qt.transparent)
        
        # 步骤2: 切换回正常绘制模式
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        
        # 步骤3: 绘制圆角背景
        radius = 8
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QColor(0x1a, 0x1a, 0x21))
        
        # 步骤4: 绘制边框
        pen = QPen(QColor(0x37, 0x41, 0x51), 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        
        # 步骤5: 设置裁剪路径，在圆角区域内绘制菜单项
        painter.setClipPath(path)
        painter.end()
        
        # 调用父类的paintEvent在裁剪区域内绘制菜单项
        super().paintEvent(event)
    
    def showEvent(self, event):
        """显示事件 - 延迟设置窗口遮罩"""
        super().showEvent(event)
        # 延迟设置遮罩，确保菜单大小已确定
        QTimer.singleShot(1, self._set_mask)
    
    def _set_mask(self):
        """设置圆角遮罩，裁剪窗口的实际形状（关键步骤）"""
        radius = 8
        mask = QPixmap(self.size())
        mask.fill(Qt.transparent)
        painter = QPainter(mask)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(Qt.black))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        painter.drawPath(path)
        painter.end()
        self.setMask(mask.mask())


class RegionSelectorWindow(QWidget):
    """区域选择窗口 - 类似 ShareX 的区域选择"""
    region_selected = pyqtSignal(tuple)  # (x, y, width, height)
    window_closing = pyqtSignal()  # 窗口关闭信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 确保窗口显示在最顶层并设置为无框全屏，但移除WindowTransparentForInput以允许鼠标交互
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        
        # 确保半透明背景正确应用
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_PaintOnScreen, True)
        # 确保光标可以正确设置
        self.setAttribute(Qt.WA_SetCursor, True)
        
        # 设置为全屏
        self.setWindowState(Qt.WindowFullScreen)
        
        # 确保窗口在所有屏幕上显示
        screen_rect = QApplication.desktop().screenGeometry()
        self.setGeometry(screen_rect)
        
        self.start_point = None
        self.end_point = None
        self.selecting = False
        self.selected_region = None  # 用于存储最终选择的区域
        self.show_close_button = True  # 控制关闭按钮的显示
        self.close_button_hovered = False  # 跟踪关闭按钮的悬停状态
        
        # 调整大小相关变量
        self.resize_handle_size = 12  # 边框调整区域的大小（像素），增大以提高检测灵敏度
        self.resizing = False  # 是否正在调整大小
        self.resize_type = None  # 调整类型：'top', 'bottom', 'left', 'right', 'top-left', 'top-right', 'bottom-left', 'bottom-right'
        self.resize_start_pos = None  # 调整大小开始时的鼠标位置
        self.resize_start_region = None  # 调整大小开始时的区域
        
        # 移动相关变量
        self.move_button_size = 16  # 移动按钮大小（增大以提高可见性）
        self.move_button_hovered = False  # 移动按钮悬停状态
        self.moving = False  # 是否正在移动窗口
        self.move_start_pos = None  # 移动开始时的鼠标位置
        self.move_start_region = None  # 移动开始时的区域
        
        # 录制状态和设置（由主窗口设置）
        self.is_recording = False  # 是否正在录制
        self.allow_move_during_recording = False  # 录制时是否允许移动
        
        # 启用鼠标跟踪，这样即使不按下鼠标也能接收到鼠标移动事件
        self.setMouseTracking(True)
        
        # Windows API 相关（用于点击穿透）
        if sys.platform == 'win32':
            self.hwnd = None  # 窗口句柄
            self.original_exstyle = None  # 原始扩展样式
        
        # 移除样式表设置，避免与paintEvent冲突
    
    def _update_click_through_region(self):
        """更新窗口区域，只让可交互区域响应鼠标事件（Windows API）"""
        if sys.platform != 'win32' or not self.is_recording:
            return
        
        try:
            if self.hwnd is None:
                # 获取窗口句柄
                self.hwnd = int(self.winId())
            
            if not self.selected_region:
                # 没有选择区域，禁用点击穿透（整个窗口可点击）
                user32.SetWindowRgn(self.hwnd, 0, True)
                return
            
            # 创建区域，只包含可交互区域
            x, y, width, height = self.selected_region
            border_margin = self.resize_handle_size
            
            # 计算交互区域（包括边框和按钮）
            left = max(0, x - border_margin)
            top = max(0, y - border_margin)
            right = x + width + border_margin
            bottom = y + height + border_margin
            
            # 创建矩形区域
            region = gdi32.CreateRectRgn(left, top, right, bottom)
            
            # 如果有关闭按钮，添加关闭按钮区域
            if self.show_close_button:
                close_button_size = 24
                close_button_x = x + width - close_button_size - 5
                close_button_y = y + 5
                close_region = gdi32.CreateRectRgn(
                    close_button_x, close_button_y,
                    close_button_x + close_button_size, close_button_y + close_button_size
                )
                temp_region = gdi32.CreateRectRgn(0, 0, 0, 0)
                gdi32.CombineRgn(temp_region, region, close_region, 2)  # RGN_OR
                gdi32.DeleteObject(region)
                gdi32.DeleteObject(close_region)
                region = temp_region
            
            # 如果有移动按钮，添加移动按钮区域
            move_button_rect = self.get_move_button_rect()
            if move_button_rect:
                move_region = gdi32.CreateRectRgn(
                    move_button_rect.x(), move_button_rect.y(),
                    move_button_rect.x() + move_button_rect.width(),
                    move_button_rect.y() + move_button_rect.height()
                )
                temp_region = gdi32.CreateRectRgn(0, 0, 0, 0)
                gdi32.CombineRgn(temp_region, region, move_region, 2)  # RGN_OR
                gdi32.DeleteObject(region)
                gdi32.DeleteObject(move_region)
                region = temp_region
            
            # 设置窗口区域
            user32.SetWindowRgn(self.hwnd, region, True)
            print(f"DEBUG: 已更新窗口区域，只允许交互区域响应鼠标事件")
        except Exception as e:
            print(f"DEBUG: 更新窗口区域失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _clear_click_through_region(self):
        """清除窗口区域限制，恢复整个窗口可点击"""
        if sys.platform != 'win32':
            return
        
        try:
            if self.hwnd is None:
                self.hwnd = int(self.winId())
            user32.SetWindowRgn(self.hwnd, 0, True)
            print("DEBUG: 已清除窗口区域限制")
        except Exception as e:
            print(f"DEBUG: 清除窗口区域限制失败: {e}")
    
    
    def set_recording_state(self, is_recording, allow_move_during_recording):
        """设置录制状态和是否允许在录制时移动"""
        old_recording = self.is_recording
        self.is_recording = is_recording
        self.allow_move_during_recording = allow_move_during_recording
        print(f"DEBUG: RegionSelectorWindow.set_recording_state - is_recording: {self.is_recording}, allow_move_during_recording: {self.allow_move_during_recording}")
        
        # 在录制时，更新窗口区域，只让可交互区域响应鼠标事件
        if sys.platform == 'win32':
            if self.is_recording and not old_recording:
                # 刚开始录制，更新窗口区域
                QTimer.singleShot(100, self._update_click_through_region)  # 延迟一点确保窗口已显示
            elif not self.is_recording and old_recording:
                # 停止录制，清除窗口区域限制
                self._clear_click_through_region()
        
        # 注意：现在采用收缩录制区域的方法，虚线框仍然可见，不会被录制到
        self.update()
    
    def get_resize_type(self, pos):
        """检测鼠标位置对应的调整大小类型，返回None表示不在调整区域"""
        if not self.selected_region:
            return None
        
        x, y, width, height = self.selected_region
        px, py = pos.x(), pos.y()
        handle_size = self.resize_handle_size
        
        # 检查四个角（优先级最高）
        corner_size = handle_size
        # 左上角
        if (x - corner_size <= px <= x + corner_size and 
            y - corner_size <= py <= y + corner_size):
            return 'top-left'
        # 右上角
        if (x + width - corner_size <= px <= x + width + corner_size and 
            y - corner_size <= py <= y + corner_size):
            return 'top-right'
        # 左下角
        if (x - corner_size <= px <= x + corner_size and 
            y + height - corner_size <= py <= y + height + corner_size):
            return 'bottom-left'
        # 右下角
        if (x + width - corner_size <= px <= x + width + corner_size and 
            y + height - corner_size <= py <= y + height + corner_size):
            return 'bottom-right'
        
        # 检查四条边（排除角区域，避免与角检测冲突）
        # 上边（排除左右角区域）
        if (x + corner_size + 1 < px < x + width - corner_size - 1 and 
            y - handle_size <= py <= y + handle_size):
            return 'top'
        # 下边（排除左右角区域）
        if (x + corner_size + 1 < px < x + width - corner_size - 1 and 
            y + height - handle_size <= py <= y + height + handle_size):
            return 'bottom'
        # 左边（排除上下角区域）
        if (x - handle_size <= px <= x + handle_size and 
            y + corner_size + 1 < py < y + height - corner_size - 1):
            return 'left'
        # 右边（排除上下角区域）
        if (x + width - handle_size <= px <= x + width + handle_size and 
            y + corner_size + 1 < py < y + height - corner_size - 1):
            return 'right'
        
        return None
    
    def get_move_button_rect(self):
        """获取移动按钮的矩形区域"""
        if not self.selected_region:
            return None
        # 如果正在录制且不允许移动，则不返回移动按钮区域
        if self.is_recording and not self.allow_move_during_recording:
            return None
        x, y, width, height = self.selected_region
        button_size = self.move_button_size
        # 根据关闭按钮的显示状态来计算位置（与绘制时的逻辑保持一致）
        if self.show_close_button:
            button_x = x + width - button_size - 30  # 在关闭按钮左侧
        else:
            button_x = x + width - button_size - 5  # 直接在右上角
        button_y = y + 5
        return QRect(button_x, button_y, button_size, button_size)
    
    def _is_click_in_interactive_area(self, pos):
        """检查点击位置是否在窗口的可交互区域内"""
        if not self.selected_region:
            return False
        
        x, y, width, height = self.selected_region
        
        # 检查是否在已选择区域内（包括边框）
        border_margin = self.resize_handle_size
        if (x - border_margin <= pos.x() <= x + width + border_margin and
            y - border_margin <= pos.y() <= y + height + border_margin):
            return True
        
        # 检查关闭按钮
        if self.show_close_button:
            close_button_size = 24
            close_button_x = x + width - close_button_size - 5
            close_button_y = y + 5
            close_button_rect = QRect(close_button_x, close_button_y, close_button_size, close_button_size)
            if close_button_rect.contains(pos):
                return True
        
        # 检查移动按钮
        move_button_rect = self.get_move_button_rect()
        if move_button_rect and move_button_rect.contains(pos):
            return True
        
        return False
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 如果正在录制，只响应窗口上的可交互元素的点击
            if self.is_recording:
                # 检查是否点击在可交互区域内
                if not self._is_click_in_interactive_area(event.pos()):
                    # 点击在窗口外，忽略事件，让点击穿透到下层窗口
                    event.ignore()
                    return
            
            if self.selected_region:
                # 检查是否点击了关闭按钮
                if self.show_close_button:
                    x, y, width, height = self.selected_region
                    close_button_size = 24
                    close_button_x = x + width - close_button_size - 5
                    close_button_y = y + 5
                    close_button_rect = QRect(close_button_x, close_button_y, close_button_size, close_button_size)
                    
                    if close_button_rect.contains(event.pos()):
                        # 点击了关闭按钮，关闭窗口
                        self.close()
                        return
                
                # 检查是否点击了移动按钮
                move_button_rect = self.get_move_button_rect()
                if move_button_rect and move_button_rect.contains(event.pos()):
                    # get_move_button_rect已经检查了是否允许移动，如果返回了区域就可以移动
                    print(f"DEBUG: 点击了移动按钮，开始移动窗口")
                    self.moving = True
                    self.move_start_pos = event.pos()
                    self.move_start_region = self.selected_region
                    return
                
                # 检查是否点击了调整大小区域
                resize_type = self.get_resize_type(event.pos())
                if resize_type:
                    # 录制时可以调整大小
                    self.resizing = True
                    self.resize_type = resize_type
                    self.resize_start_pos = event.pos()
                    self.resize_start_region = self.selected_region
                    return
            
            # 正常的选择操作（仅在非录制状态时允许）
            if not self.is_recording:
                self.start_point = event.pos()
                self.selecting = True
                self.end_point = self.start_point  # 初始化终点为起点
                self.selected_region = None  # 清空之前的选择
                self.moving = False
                self.resizing = False
                self.update()
    
    def mouseMoveEvent(self, event):
        if self.resizing:
            # 正在调整大小
            if not self.resize_start_region:
                return
            
            x, y, width, height = self.resize_start_region
            dx = event.pos().x() - self.resize_start_pos.x()
            dy = event.pos().y() - self.resize_start_pos.y()
            
            resize_type = self.resize_type
            new_x, new_y, new_width, new_height = x, y, width, height
            
            # 根据调整类型计算新区域
            if 'left' in resize_type:
                new_x = x + dx
                new_width = width - dx
                if new_width < 10:  # 最小宽度
                    new_width = 10
                    new_x = x + width - 10
                if new_x < 0:  # 不能超出左边界
                    new_x = 0
                    new_width = x + width
            if 'right' in resize_type:
                new_width = width + dx
                if new_width < 10:
                    new_width = 10
            if 'top' in resize_type:
                new_y = y + dy
                new_height = height - dy
                if new_height < 10:  # 最小高度
                    new_height = 10
                    new_y = y + height - 10
                if new_y < 0:  # 不能超出上边界
                    new_y = 0
                    new_height = y + height
            if 'bottom' in resize_type:
                new_height = height + dy
                if new_height < 10:
                    new_height = 10
            
            # 获取屏幕边界
            screen_rect = QApplication.desktop().screenGeometry()
            
            # 确保区域不超出屏幕边界
            if new_x < 0:
                new_x = 0
            if new_y < 0:
                new_y = 0
            if new_x + new_width > screen_rect.width():
                new_width = screen_rect.width() - new_x
            if new_y + new_height > screen_rect.height():
                new_height = screen_rect.height() - new_y
            
            # 确保最小尺寸（在边界检查之后）
            if new_width < 10:
                new_width = 10
                # 如果宽度被限制为最小，调整x位置以保持区域在屏幕内
                if new_x + new_width > screen_rect.width():
                    new_x = screen_rect.width() - new_width
            if new_height < 10:
                new_height = 10
                # 如果高度被限制为最小，调整y位置以保持区域在屏幕内
                if new_y + new_height > screen_rect.height():
                    new_y = screen_rect.height() - new_height
            
            # 更新区域
            self.selected_region = (new_x, new_y, new_width, new_height)
            self.region_selected.emit(self.selected_region)
            
            # 在录制时，更新窗口区域
            if self.is_recording and sys.platform == 'win32':
                self._update_click_through_region()
            
            # 在调整大小时保持相应的光标
            if resize_type in ['top-left', 'bottom-right']:
                self.setCursor(Qt.SizeFDiagCursor)
            elif resize_type in ['top-right', 'bottom-left']:
                self.setCursor(Qt.SizeBDiagCursor)
            elif resize_type in ['top', 'bottom']:
                self.setCursor(Qt.SizeVerCursor)
            elif resize_type in ['left', 'right']:
                self.setCursor(Qt.SizeHorCursor)
            
            self.update()
            
        elif self.moving:
            # 正在移动窗口
            if not self.move_start_region:
                return
            
            x, y, width, height = self.move_start_region
            dx = event.pos().x() - self.move_start_pos.x()
            dy = event.pos().y() - self.move_start_pos.y()
            
            new_x = x + dx
            new_y = y + dy
            
            # 确保窗口不超出屏幕边界
            screen_rect = QApplication.desktop().screenGeometry()
            new_x = max(0, min(new_x, screen_rect.width() - width))
            new_y = max(0, min(new_y, screen_rect.height() - height))
            
            # 更新区域
            self.selected_region = (new_x, new_y, width, height)
            # 发送区域更新信号（录制时也会更新）
            self.region_selected.emit(self.selected_region)
            
            # 在录制时，更新窗口区域
            if self.is_recording and sys.platform == 'win32':
                self._update_click_through_region()
            
            # 在移动时保持移动光标
            self.unsetCursor()
            self.setCursor(Qt.SizeAllCursor)
            
            self.update()
            
        elif self.selecting:
            self.end_point = event.pos()
            self.update()
            # 确保鼠标光标为十字形
            self.setCursor(Qt.CrossCursor)
        elif self.selected_region:
            # 检查鼠标位置并更新光标和悬停状态
            pos = event.pos()
            resize_type = self.get_resize_type(pos)
            
            # 检查关闭按钮
            x, y, width, height = self.selected_region
            close_button_size = 24
            close_button_x = x + width - close_button_size - 5
            close_button_y = y + 5
            close_button_rect = QRect(close_button_x, close_button_y, close_button_size, close_button_size)
            was_close_hovered = self.close_button_hovered
            self.close_button_hovered = close_button_rect.contains(pos)
            
            # 检查移动按钮
            move_button_rect = self.get_move_button_rect()
            was_move_hovered = self.move_button_hovered
            # 如果get_move_button_rect返回了区域，说明允许移动，直接检查是否包含鼠标位置
            if move_button_rect:
                self.move_button_hovered = move_button_rect.contains(pos)
            else:
                self.move_button_hovered = False
            
            # 如果悬停状态改变，需要重绘
            if (was_close_hovered != self.close_button_hovered or 
                was_move_hovered != self.move_button_hovered):
                self.update()
            
            # 设置光标（优先级：关闭按钮 > 移动按钮 > 调整大小边框 > 默认）
            # 使用unsetCursor然后setCursor确保光标变化生效
            if self.close_button_hovered:
                self.unsetCursor()
                self.setCursor(Qt.PointingHandCursor)
            elif self.move_button_hovered:
                self.unsetCursor()
                self.setCursor(Qt.SizeAllCursor)  # 移动光标
            elif resize_type:
                # 根据调整类型设置光标
                self.unsetCursor()
                if resize_type in ['top-left', 'bottom-right']:
                    self.setCursor(Qt.SizeFDiagCursor)  # 对角线调整
                elif resize_type in ['top-right', 'bottom-left']:
                    self.setCursor(Qt.SizeBDiagCursor)  # 对角线调整
                elif resize_type in ['top', 'bottom']:
                    self.setCursor(Qt.SizeVerCursor)  # 垂直调整
                elif resize_type in ['left', 'right']:
                    self.setCursor(Qt.SizeHorCursor)  # 水平调整
            else:
                self.setCursor(Qt.ArrowCursor)
        else:
            # 没有选择区域时，恢复正常光标
            self.setCursor(Qt.ArrowCursor)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.resizing:
                # 结束调整大小
                self.resizing = False
                self.resize_type = None
                self.resize_start_pos = None
                self.resize_start_region = None
            elif self.moving:
                # 结束移动
                self.moving = False
                self.move_start_pos = None
                self.move_start_region = None
            elif self.selecting:
                self.selecting = False
                self.setCursor(Qt.ArrowCursor)  # 恢复正常光标
                if self.start_point and self.end_point:
                    x = min(self.start_point.x(), self.end_point.x())
                    y = min(self.start_point.y(), self.end_point.y())
                    width = abs(self.end_point.x() - self.start_point.x())
                    height = abs(self.end_point.y() - self.start_point.y())
                    
                    if width >= 10 and height >= 10:  # 最小区域10x10
                        # 输出调试信息
                        print(f"DEBUG: 选择区域: x={x}, y={y}, width={width}, height={height}")
                        
                        # 保存选择的区域，用于持续显示
                        self.selected_region = (x, y, width, height)
                        
                        # 发送选择区域信号（但不关闭窗口）
                        self.region_selected.emit((x, y, width, height))
                        
                        # 立即重绘以显示最终选择的虚线框和关闭按钮
                        self.update()
                    else:
                        # 区域太小，不接受选择，清空并继续
                        print(f"DEBUG: 选择区域太小 ({width}x{height})，需要至少10x10像素")
                        self.start_point = None
                        self.end_point = None
                        self.update()
    
    def set_show_close_button(self, show):
        """设置关闭按钮的显示状态"""
        if self.show_close_button != show:
            self.show_close_button = show
            self.update()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 发出信号通知主窗口窗口正在关闭
        self.window_closing.emit()
        event.accept()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
    
    def paintEvent(self, event):
        # 正常绘制虚线框（现在采用收缩录制区域的方法，虚线框不会出现在录制视频中）
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 首先绘制半透明遮罩覆盖整个屏幕 - 进一步降低透明度以提高可视性
        painter.fillRect(self.rect(), QColor(0, 0, 0, 30))  # 更通透的半透明黑色背景
        
        # 优先使用最终选择的区域（如果有）
        if self.selected_region:
            x, y, width, height = self.selected_region
            x1, y1, x2, y2 = x, y, x + width, y + height
        elif self.start_point and self.end_point:
            # 计算选择区域
            x1 = min(self.start_point.x(), self.end_point.x())
            y1 = min(self.start_point.y(), self.end_point.y())
            x2 = max(self.start_point.x(), self.end_point.x())
            y2 = max(self.start_point.y(), self.end_point.y())
        else:
            return
        
        # 创建选择区域
        selection_rect = QRect(x1, y1, x2 - x1, y2 - y1)
        
        # 在选择区域内清除半透明遮罩，让原始屏幕内容显示出来
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(selection_rect, Qt.transparent)
        
        # 恢复正常绘制模式
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        
        # 绘制边框 - 使用红色虚线边框
        pen = QPen(QColor(255, 58, 58), 2, Qt.DashLine)  # 红色虚线边框，2像素宽
        # 设置虚线样式，确保虚线更清晰可见
        pen.setDashPattern([4, 2])  # 4像素实线，2像素空白的虚线模式
        painter.setPen(pen)
        painter.drawRect(selection_rect)
        
        # 添加角标记，增强可视性
        corner_size = 15
        # 左上角
        painter.drawLine(x1, y1, x1 + corner_size, y1)
        painter.drawLine(x1, y1, x1, y1 + corner_size)
        # 右上角
        painter.drawLine(x2 - corner_size, y1, x2, y1)
        painter.drawLine(x2, y1, x2, y1 + corner_size)
        # 左下角
        painter.drawLine(x1, y2 - corner_size, x1, y2)
        painter.drawLine(x1, y2, x1 + corner_size, y2)
        # 右下角
        painter.drawLine(x2 - corner_size, y2, x2, y2)
        painter.drawLine(x2, y2 - corner_size, x2, y2)
        
        # 如果已选择区域，绘制关闭按钮和移动按钮
        if self.selected_region:
            # 绘制关闭按钮（仅在show_close_button为True时）
            if self.show_close_button:
                close_button_size = 24
                close_button_x = x2 - close_button_size - 5
                close_button_y = y1 + 5
                
                # 绘制关闭按钮背景（圆形）
                button_color = QColor(255, 58, 58)  # 红色
                if self.close_button_hovered:
                    button_color = QColor(255, 100, 100)  # 悬停时更亮的红色
                
                painter.setBrush(QBrush(button_color))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(close_button_x, close_button_y, close_button_size, close_button_size)
                
                # 绘制X符号
                painter.setPen(QPen(QColor(255, 255, 255), 2))  # 白色X，2像素宽
                offset = 6  # X符号的偏移量
                painter.drawLine(
                    close_button_x + offset, 
                    close_button_y + offset,
                    close_button_x + close_button_size - offset,
                    close_button_y + close_button_size - offset
                )
                painter.drawLine(
                    close_button_x + close_button_size - offset,
                    close_button_y + offset,
                    close_button_x + offset,
                    close_button_y + close_button_size - offset
                )
            
            # 绘制移动按钮（圆点）
            # 如果正在录制且不允许移动，则不显示移动按钮
            should_show_move_button = not (self.is_recording and not self.allow_move_during_recording)
            print(f"DEBUG: 绘制移动按钮判断 - is_recording: {self.is_recording}, allow_move_during_recording: {self.allow_move_during_recording}, should_show: {should_show_move_button}")
            
            if should_show_move_button:
                move_button_size = self.move_button_size
                # 如果关闭按钮显示，移动按钮在关闭按钮左侧；否则在右上角
                if self.show_close_button:
                    move_button_x = x2 - move_button_size - 30  # 在关闭按钮左侧
                else:
                    move_button_x = x2 - move_button_size - 5  # 直接在右上角
                move_button_y = y1 + 5
                
                print(f"DEBUG: 绘制移动按钮 - 位置: ({move_button_x}, {move_button_y}), 大小: {move_button_size}")
                
                # 移动按钮颜色（始终使用绿色）
                move_button_color = QColor(76, 175, 80)  # 绿色
                if self.move_button_hovered:
                    move_button_color = QColor(102, 187, 106)  # 悬停时更亮的绿色
                
                # 绘制按钮背景和边框
                painter.setBrush(QBrush(move_button_color))
                painter.setPen(QPen(QColor(255, 255, 255), 1.5))  # 白色边框，使其更明显
                painter.drawEllipse(move_button_x, move_button_y, move_button_size, move_button_size)


class RecordingThread(QThread):
    """录屏线程 - 使用 FFmpeg 实现，类似 ShareX"""
    recording_failed = pyqtSignal(str)  # 录制失败信号，传递错误信息
    video_processing_complete = pyqtSignal(str, int)  # 视频处理完成信号，传递文件路径和文件大小
    merge_progress = pyqtSignal(str, int, int)  # 合并进度信号，传递消息、当前进度、总进度
    
    def __init__(self, region, filepath, fps=30, microphone_enabled=False, audio_enabled=True, 
                 microphone_device=None, audio_device=None, quality='高质量', audio_quality='高音质', show_cursor=True, 
                 camera_device=None, camera_enabled=False):
        super().__init__()
        self.region = region
        self.filepath = filepath
        self.fps = fps
        self.microphone_enabled = microphone_enabled
        self.audio_enabled = audio_enabled
        self.microphone_device = microphone_device
        self.audio_device = audio_device
        self.quality = quality  # 视频质量：原画质、高质量、中等质量、低质量
        self.audio_quality = audio_quality  # 音频质量：无损音质、高音质、中等音质、低音质
        self.show_cursor = show_cursor  # 是否显示鼠标指针
        self.camera_device = camera_device  # 摄像头设备名称
        self.camera_enabled = camera_enabled  # 是否启用摄像头录制
        self.running = False
        self.paused = False
        self.ffmpeg_process = None
        self.video_encoder = None  # 将检测到的视频编码器
        self.region_lock = threading.Lock()  # 用于保护区域更新的锁
        
        # FFmpeg进程跟踪（用于确保所有进程都被关闭）
        self.ffmpeg_processes = []  # 跟踪所有创建的FFmpeg进程
        self.ffmpeg_process_lock = threading.Lock()  # 保护进程列表的锁
        
        # 分段录制支持（用于实时更新录制区域）
        self.video_segments = []  # 存储视频片段文件路径
        self.segment_index = 0  # 当前片段索引
        self.base_filepath = filepath  # 原始文件路径
        import tempfile
        self.segment_dir = tempfile.mkdtemp(prefix='recording_segments_')  # 片段存储目录
        print(f"DEBUG: 创建片段存储目录: {self.segment_dir}")
        
        # 片段列表管理（序列化）
        self.segment_list_file = os.path.join(self.segment_dir, 'segment_list.json')  # 片段列表文件
        self.segment_list = []  # 片段列表：[{"index": 0, "video_path": "...", "start_time": 0.0, "end_time": 10.5}, ...]
        self.recording_start_time = None  # 录制开始时间（用于计算音频时间范围）
        self.last_segment_end_time = 0.0  # 上一个片段的结束时间（用于计算音频时间范围）
        
        # 初始化系统音频录制器
        self.system_audio_recorder = SystemAudioRecorder() if HAS_PYAUDIO_WPATCH else None
        
        # 初始化麦克风音频录制器（参考SystemAudioRecorder实现）
        self.microphone_audio_recorder = None
        if self.microphone_enabled and self.microphone_device:
            try:
                self.microphone_audio_recorder = MicrophoneAudioRecorder(device_name=self.microphone_device)
                print(f"DEBUG: 初始化麦克风音频录制器，设备: {self.microphone_device}")
            except Exception as e:
                print(f"DEBUG: 初始化麦克风音频录制器失败: {e}")
                self.microphone_audio_recorder = None
        
        # 音频录制器操作锁（防止多线程同时操作导致崩溃）
        self.audio_recorder_lock = threading.Lock()
        self.audio_stopping = False  # 标记是否正在停止音频录制
        
        # 动态音频控制标志
        self.microphone_muted = False  # 麦克风是否静音（录制过程中动态控制）
        
        # 保存音频文件信息，用于后台处理
        self.system_audio_file = None
        self.microphone_audio_file = None  # 麦克风音频文件
        self.audio_saved = False
        self.microphone_audio_saved = False  # 麦克风音频保存状态
    
    def _get_ffmpeg_dshow_audio_device(self, system_device_name):
        """获取FFmpeg可用的dshow音频设备名称（通过匹配系统设备名称）"""
        if not system_device_name:
            return None
        
        try:
            import subprocess
            # 使用FFmpeg列出所有dshow音频设备
            test_cmd = ['ffmpeg', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy']
            test_result = subprocess.run(
                test_cmd,
                capture_output=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            test_output = test_result.stderr.decode('utf-8', errors='ignore')
            
            # 查找音频设备列表
            # FFmpeg输出格式示例：
            # [dshow @ 0x...] "Microphone (Realtek Audio)" (audio)
            audio_devices = []
            capturing_audio = False
            for line in test_output.split('\n'):
                line_lower = line.lower()
                if 'audio' in line_lower and 'dshow' in line_lower:
                    capturing_audio = True
                if capturing_audio and '"' in line:
                    # 提取设备名称（在引号中）
                    start = line.find('"')
                    end = line.rfind('"')
                    if start >= 0 and end > start:
                        device_name = line[start+1:end]
                        # 移除可能的 "(audio)" 后缀
                        if ' (audio)' in device_name:
                            device_name = device_name.replace(' (audio)', '')
                        if device_name and device_name not in audio_devices:
                            audio_devices.append(device_name)
            
            print(f"DEBUG: FFmpeg检测到的dshow音频设备: {audio_devices}")
            print(f"DEBUG: 系统设备名称: {system_device_name}")
            
            # 尝试精确匹配
            for device in audio_devices:
                if device == system_device_name:
                    print(f"DEBUG: 精确匹配到设备: {device}")
                    return device
            
            # 尝试部分匹配（移除括号内容后匹配）
            system_name_clean = system_device_name.split(' (')[0].strip()
            for device in audio_devices:
                device_clean = device.split(' (')[0].strip()
                if device_clean == system_name_clean:
                    print(f"DEBUG: 部分匹配到设备: {device} (系统名称: {system_device_name})")
                    return device
            
            # 尝试包含匹配
            for device in audio_devices:
                if system_device_name.lower() in device.lower() or device.lower() in system_device_name.lower():
                    print(f"DEBUG: 包含匹配到设备: {device} (系统名称: {system_device_name})")
                    return device
            
            # 如果都匹配不上，返回第一个可用的设备（作为备选）
            if audio_devices:
                print(f"DEBUG: 无法匹配设备，使用第一个可用设备: {audio_devices[0]}")
                return audio_devices[0]
            
            print(f"DEBUG: 未找到FFmpeg可用的音频设备")
            return None
        except Exception as e:
            print(f"DEBUG: 获取FFmpeg dshow音频设备失败: {e}")
            return None

    def detect_available_video_encoder(self):
        """检测可用的视频编码器"""
        try:
            # 检查 FFmpeg 支持的编码器
            result = subprocess.run(
                ['ffmpeg', '-encoders'],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode == 0:
                encoder_output = result.stdout + result.stderr
                # 优先级列表：优先使用硬件编码器，然后软件编码器
                encoder_priority = [
                    'libx264',      # 最常用的 H.264 编码器（如果可用）
                    'libopenh264',  # OpenH264 编码器（软件编码器，可靠）
                    'mpeg4',        # MPEG-4 编码器（通用编码器）
                    'libx265',      # H.265/HEVC 编码器
                    'libvpx',       # VP8/VP9 编码器
                    'h264_qsv',     # Intel Quick Sync 硬件编码器
                    'h264_amf',     # AMD 硬件编码器
                    'h264_nvenc',   # NVIDIA 硬件编码器（最后尝试，可能有兼容性问题）
                ]
                
                # 优先查找软件编码器（更可靠）
                software_encoders = ['libx264', 'libopenh264', 'mpeg4', 'libx265', 'libvpx']
                for encoder in software_encoders:
                    if encoder in encoder_output:
                        for line in encoder_output.split('\n'):
                            if encoder in line and line.strip().startswith('V'):
                                print(f"DEBUG: 找到可用软件编码器: {encoder}")
                                return encoder
                
                # 如果没有找到软件编码器，再尝试硬件编码器
                hardware_encoders = ['h264_qsv', 'h264_amf', 'h264_nvenc']
                for encoder in hardware_encoders:
                    if encoder in encoder_output:
                        for line in encoder_output.split('\n'):
                            if encoder in line and line.strip().startswith('V'):
                                print(f"DEBUG: 找到硬件编码器: {encoder} (可能不稳定)")
                                return encoder
                
                # 最后尝试优先级列表中的其他编码器
                for encoder in encoder_priority:
                    if encoder not in software_encoders + hardware_encoders:
                        if encoder in encoder_output:
                            for line in encoder_output.split('\n'):
                                if encoder in line and line.strip().startswith('V'):
                                    print(f"DEBUG: 找到可用编码器: {encoder}")
                                    return encoder
                
                print("DEBUG: 警告：未找到常用编码器，尝试查找任何视频编码器")
                # 如果优先列表都没有，尝试找第一个可用的视频编码器
                for line in encoder_output.split('\n'):
                    if line.strip().startswith('V') and '264' in line:
                        parts = line.split()
                        if len(parts) > 1:
                            encoder_name = parts[1]
                            print(f"DEBUG: 找到 H.264 编码器: {encoder_name}")
                            return encoder_name
                
                print("DEBUG: 错误：未找到可用的视频编码器")
                return None
        except Exception as e:
            print(f"DEBUG: 检测编码器时出错: {e}")
        
        return None
    
    def _save_segment_list(self):
        """保存片段列表到JSON文件"""
        try:
            with open(self.segment_list_file, 'w', encoding='utf-8') as f:
                json.dump(self.segment_list, f, indent=2, ensure_ascii=False)
            print(f"DEBUG: 片段列表已保存，共 {len(self.segment_list)} 个片段")
        except Exception as e:
            print(f"DEBUG: 保存片段列表失败: {e}")
    
    def _load_segment_list(self):
        """从JSON文件加载片段列表"""
        try:
            if os.path.exists(self.segment_list_file):
                with open(self.segment_list_file, 'r', encoding='utf-8') as f:
                    self.segment_list = json.load(f)
                print(f"DEBUG: 片段列表已加载，共 {len(self.segment_list)} 个片段")
                # 同步到video_segments列表
                self.video_segments = [seg['video_path'] for seg in self.segment_list if os.path.exists(seg['video_path'])]
                return True
        except Exception as e:
            print(f"DEBUG: 加载片段列表失败: {e}")
        return False
    
    def _add_segment_to_list(self, video_path, start_time=None, end_time=None):
        """添加片段到列表"""
        try:
            if not os.path.exists(video_path):
                print(f"DEBUG: 警告：片段文件不存在，跳过添加: {video_path}")
                return False
            
            # 如果已经存在，跳过
            for seg in self.segment_list:
                if seg['video_path'] == video_path:
                    print(f"DEBUG: 片段已在列表中，跳过: {video_path}")
                    return False
            
            # 计算时间范围
            if start_time is None:
                start_time = self.last_segment_end_time
            if end_time is None:
                # 使用当前时间作为结束时间（实际结束时间会在暂停或停止时更新）
                if self.recording_start_time:
                    end_time = time.time() - self.recording_start_time - (self.system_audio_recorder.total_pause_duration if self.system_audio_recorder else 0)
                else:
                    end_time = start_time + 1.0  # 默认1秒
            
            segment_info = {
                "index": len(self.segment_list),
                "video_path": video_path,
                "start_time": start_time,
                "end_time": end_time
            }
            
            self.segment_list.append(segment_info)
            self.last_segment_end_time = end_time
            
            # 同步到video_segments列表
            if video_path not in self.video_segments:
                self.video_segments.append(video_path)
            
            # 保存到文件
            self._save_segment_list()
            
            print(f"DEBUG: 已添加片段到列表: index={segment_info['index']}, path={video_path}, time={start_time:.2f}-{end_time:.2f}")
            return True
        except Exception as e:
            print(f"DEBUG: 添加片段到列表失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _update_last_segment_end_time(self, end_time):
        """更新最后一个片段的结束时间"""
        try:
            if len(self.segment_list) > 0:
                self.segment_list[-1]['end_time'] = end_time
                self.last_segment_end_time = end_time
                self._save_segment_list()
        except Exception as e:
            print(f"DEBUG: 更新片段结束时间失败: {e}")
    
    def _force_close_ffmpeg_process(self, process, timeout=5):
        """强制关闭FFmpeg进程，确保进程被完全关闭"""
        if process is None:
            return True
        
        try:
            # 检查进程是否还在运行
            if process.poll() is not None:
                # 进程已经结束，从列表中移除
                with self.ffmpeg_process_lock:
                    if process in self.ffmpeg_processes:
                        self.ffmpeg_processes.remove(process)
                return True
            
            # 尝试优雅关闭
            try:
                if process.stdin:
                    try:
                        process.stdin.write(b'q\n')
                        process.stdin.flush()
                        process.stdin.close()
                    except:
                        pass
            except:
                pass
            
            # 等待进程结束
            try:
                process.wait(timeout=timeout)
                # 从列表中移除
                with self.ffmpeg_process_lock:
                    if process in self.ffmpeg_processes:
                        self.ffmpeg_processes.remove(process)
                return True
            except subprocess.TimeoutExpired:
                pass
            
            # 如果优雅关闭失败，尝试终止
            try:
                process.terminate()
                try:
                    process.wait(timeout=3)
                    # 从列表中移除
                    with self.ffmpeg_process_lock:
                        if process in self.ffmpeg_processes:
                            self.ffmpeg_processes.remove(process)
                    return True
                except subprocess.TimeoutExpired:
                    pass
            except:
                pass
            
            # 如果终止也失败，强制杀死
            try:
                process.kill()
                process.wait(timeout=2)
                # 从列表中移除
                with self.ffmpeg_process_lock:
                    if process in self.ffmpeg_processes:
                        self.ffmpeg_processes.remove(process)
                return True
            except:
                pass
            
            # 如果所有方法都失败，尝试使用Windows API强制终止
            try:
                if sys.platform == 'win32':
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    # 获取进程ID
                    pid = process.pid
                    # 打开进程
                    handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
                    if handle:
                        # 终止进程
                        kernel32.TerminateProcess(handle, 1)
                        kernel32.CloseHandle(handle)
                        process.wait(timeout=1)
                        # 从列表中移除
                        with self.ffmpeg_process_lock:
                            if process in self.ffmpeg_processes:
                                self.ffmpeg_processes.remove(process)
                        print(f"DEBUG: 使用Windows API强制终止FFmpeg进程: {pid}")
                        return True
            except Exception as win_error:
                print(f"DEBUG: 使用Windows API终止进程失败: {win_error}")
            
            # 如果所有方法都失败，从列表中移除并返回False
            with self.ffmpeg_process_lock:
                if process in self.ffmpeg_processes:
                    self.ffmpeg_processes.remove(process)
            print(f"DEBUG: 警告：无法完全关闭FFmpeg进程 (PID: {process.pid})")
            return False
        except Exception as e:
            print(f"DEBUG: 关闭FFmpeg进程时出错: {e}")
            # 确保从列表中移除
            with self.ffmpeg_process_lock:
                if process in self.ffmpeg_processes:
                    self.ffmpeg_processes.remove(process)
            return False
    
    def _cleanup_all_ffmpeg_processes(self):
        """清理所有残留的FFmpeg进程"""
        with self.ffmpeg_process_lock:
            processes_to_close = list(self.ffmpeg_processes)
            self.ffmpeg_processes.clear()
        
        for process in processes_to_close:
            if process and process.poll() is None:
                print(f"DEBUG: 清理残留的FFmpeg进程 (PID: {process.pid})")
                self._force_close_ffmpeg_process(process, timeout=2)
        
        # 也清理当前进程
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            print(f"DEBUG: 清理当前FFmpeg进程 (PID: {self.ffmpeg_process.pid})")
            self._force_close_ffmpeg_process(self.ffmpeg_process, timeout=2)
            self.ffmpeg_process = None
    
    def try_ffmpeg_recording(self):
        """使用 FFmpeg 进行录制（类似 ShareX 的实现方式）"""
        try:
            # 检查 ffmpeg 是否可用
            try:
                result = subprocess.run(['ffmpeg', '-version'], 
                                      capture_output=True, timeout=2,
                                      creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                if result.returncode != 0:
                    return False
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print("DEBUG: FFmpeg 未安装或不可用")
                return False
            
            # 使用锁读取区域参数
            with self.region_lock:
                recording_region = self.region.copy()
            
            # 确保宽度和高度是偶数（H.264编码器要求）
            original_width = recording_region['width']
            original_height = recording_region['height']
            adjusted_width = original_width if original_width % 2 == 0 else original_width - 1
            adjusted_height = original_height if original_height % 2 == 0 else original_height - 1
            
            if adjusted_width != original_width or adjusted_height != original_height:
                print(f"DEBUG: 调整区域尺寸从 {original_width}x{original_height} 到 {adjusted_width}x{adjusted_height} (H.264要求偶数尺寸)")
                recording_region['width'] = adjusted_width
                recording_region['height'] = adjusted_height
                # 更新self.region
                with self.region_lock:
                    self.region['width'] = adjusted_width
                    self.region['height'] = adjusted_height
            
            # 启动系统音频录制（如果启用且可用）
            # 检查是否已经在录制（恢复暂停时不需要重新启动）
            system_audio_file = None
            microphone_audio_file = None  # 麦克风音频文件
            
            if self.audio_enabled and self.system_audio_recorder:
                # 检查系统音频录制器是否已经在运行
                if hasattr(self.system_audio_recorder, 'is_recording') and self.system_audio_recorder.is_recording:
                    print("DEBUG: 系统音频录制器已在运行（恢复暂停），继续使用")
                    # 生成临时音频文件路径（应该已经存在）
                    import tempfile
                    system_audio_file = os.path.join(tempfile.gettempdir(), "system_audio_recording.wav")
                    # 保存到实例变量
                    self.system_audio_file = system_audio_file
                else:
                    # 生成临时音频文件路径
                    import tempfile
                    system_audio_file = os.path.join(tempfile.gettempdir(), "system_audio_recording.wav")
                    # 保存到实例变量
                    self.system_audio_file = system_audio_file
                    print(f"DEBUG: 准备启动系统音频录制，音频文件路径: {system_audio_file}")
                    print(f"DEBUG: audio_enabled={self.audio_enabled}, system_audio_recorder={self.system_audio_recorder is not None}")
                    if self.system_audio_recorder.start_recording():
                        print("DEBUG: 系统音频录制已启动")
                    else:
                        print("DEBUG: 无法启动系统音频录制，将使用FFmpeg直接录制音频")
                        system_audio_file = None
                        self.system_audio_file = None
            elif not self.audio_enabled:
                print("DEBUG: 音频录制已禁用（audio_enabled=False）")
                self.system_audio_file = None
            elif not self.system_audio_recorder:
                print("DEBUG: 系统音频录制器不可用（pyaudiowpatch未安装或初始化失败）")
                self.system_audio_file = None
            
            # 启动麦克风音频录制器（如果启用）
            if self.microphone_enabled and self.microphone_audio_recorder and not self.microphone_muted:
                # 检查麦克风音频录制器是否已经在运行
                if hasattr(self.microphone_audio_recorder, 'is_recording') and self.microphone_audio_recorder.is_recording:
                    print("DEBUG: 麦克风音频录制器已在运行（恢复暂停），继续使用")
                    import tempfile
                    microphone_audio_file = os.path.join(tempfile.gettempdir(), "microphone_audio_recording.wav")
                    self.microphone_audio_file = microphone_audio_file
                else:
                    # 生成临时麦克风音频文件路径
                    import tempfile
                    microphone_audio_file = os.path.join(tempfile.gettempdir(), "microphone_audio_recording.wav")
                    self.microphone_audio_file = microphone_audio_file
                    print(f"DEBUG: 准备启动麦克风音频录制，音频文件路径: {microphone_audio_file}")
                    if self.microphone_audio_recorder.start_recording():
                        print("DEBUG: 麦克风音频录制已启动")
                    else:
                        print("DEBUG: 无法启动麦克风音频录制")
                        microphone_audio_file = None
                        self.microphone_audio_file = None
            elif self.microphone_enabled and self.microphone_muted:
                print("DEBUG: 麦克风已静音，不启动录制")
            elif not self.microphone_audio_recorder:
                print("DEBUG: 麦克风音频录制器不可用")
            
            # 检测可用的视频编码器
            self.video_encoder = self.detect_available_video_encoder()
            if not self.video_encoder:
                print("DEBUG: 错误：无法找到可用的视频编码器，录制将失败")
                # 停止系统音频录制
                if system_audio_file and self.system_audio_recorder:
                    self.system_audio_recorder.stop_recording()
                return False
            
            # 使用 FFmpeg 录制
            self.running = True
            # 记录录制开始时间（用于计算片段时间范围）
            if self.recording_start_time is None:
                self.recording_start_time = time.time()
                self.last_segment_end_time = 0.0
                print(f"DEBUG: 录制开始时间已记录: {self.recording_start_time}")
            
            # 注意：首次录制时使用原始文件路径，只有在区域改变时才使用片段路径
            # update_region方法会负责设置新的片段路径
            
            # 构建 FFmpeg 命令
            cmd = ['ffmpeg']
            
            # 视频输入（屏幕捕获）
            # recording_region已经在上面读取并调整了尺寸
            video_input_index = 0
            if sys.platform == 'win32':
                # Windows 使用 gdigrab
                print(f"DEBUG: 使用区域参数开始录制: offset_x={recording_region['left']}, offset_y={recording_region['top']}, size={recording_region['width']}x{recording_region['height']}")
                gdigrab_options = [
                    '-f', 'gdigrab',
                    '-framerate', str(self.fps),
                    '-offset_x', str(recording_region['left']),
                    '-offset_y', str(recording_region['top']),
                    '-video_size', f"{recording_region['width']}x{recording_region['height']}",
                ]
                # 如果不需要显示鼠标指针，添加 draw_mouse=0
                if not self.show_cursor:
                    gdigrab_options.extend(['-draw_mouse', '0'])
                gdigrab_options.append('-i')
                gdigrab_options.append('desktop')
                cmd.extend(gdigrab_options)
            else:
                # Linux 使用 x11grab
                x11grab_options = [
                    '-f', 'x11grab',
                    '-framerate', str(self.fps),
                    '-video_size', f"{self.region['width']}x{self.region['height']}",
                ]
                # 如果不需要显示鼠标指针，添加 show_region=0
                if not self.show_cursor:
                    x11grab_options.extend(['-show_region', '0'])
                x11grab_options.extend(['-i', f":0.0+{self.region['left']},{self.region['top']}"])
                cmd.extend(x11grab_options)
            
            # 摄像头输入（如果启用）
            camera_input_index = None
            print(f"DEBUG: 检查摄像头录制 - camera_enabled={self.camera_enabled}, camera_device={self.camera_device}")
            if self.camera_enabled and self.camera_device:
                print(f"DEBUG: 添加摄像头输入: {self.camera_device}")
                if sys.platform == 'win32':
                    # Windows 使用 dshow 捕获摄像头
                    camera_input_index = len(cmd)  # 记录摄像头输入的位置
                    # 注意：FFmpeg的dshow设备名称可能需要使用不同的格式
                    # 尝试使用设备名称，如果失败可能需要使用设备索引
                    camera_input = f'video="{self.camera_device}"'
                    cmd.extend([
                        '-f', 'dshow',
                        '-video_size', '640x480',  # 摄像头分辨率
                        '-framerate', '30',
                        '-i', camera_input
                    ])
                    print(f"DEBUG: 已添加Windows摄像头输入: {camera_input}")
                else:
                    # Linux 使用 v4l2
                    camera_input_index = len(cmd)
                    cmd.extend([
                        '-f', 'v4l2',
                        '-video_size', '640x480',
                        '-framerate', '30',
                        '-i', self.camera_device
                    ])
                    print(f"DEBUG: 已添加Linux/Mac摄像头输入: {self.camera_device}")
            elif self.camera_enabled and not self.camera_device:
                print(f"DEBUG: 警告：摄像头已启用但未选择设备，无法录制摄像头")
            
            # 音频输入
            has_audio = False
            audio_inputs = []
            audio_input_indices = []  # 记录每个音频输入的索引位置
            
            # 只有当 audio_enabled=True 时才添加音频输入
            # 系统音频（扬声器）- 使用用户选择的设备或默认设备
            # 如果pyaudiowpatch录制失败或不可用，回退到使用FFmpeg直接录制
            if self.audio_enabled and (not self.system_audio_recorder or not system_audio_file):  # 只有在没有使用新的系统音频录制器或录制失败时才使用旧的方法
                if sys.platform == 'win32':
                    # Windows: 优先尝试 WASAPI loopback（Windows 10+ 推荐方式）
                    audio_captured = False
                    
                    # 首先尝试 WASAPI loopback
                    try:
                        # 测试 WASAPI 是否可用
                        test_cmd = ['ffmpeg', '-list_devices', 'true', '-f', 'wasapi', '-i', 'dummy']
                        test_result = subprocess.run(
                            test_cmd,
                            capture_output=True,
                            timeout=3,
                            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                        )
                        test_output = test_result.stderr.decode('utf-8', errors='ignore')
                        
                        # WASAPI loopback 设备列表格式示例：
                        # [wasapi @ 0x...] "扬声器 (Realtek Audio) (loopback)"
                        # 查找所有 loopback 设备
                        loopback_devices = []
                        capturing_loopback = False
                        for line in test_output.split('\n'):
                            line_lower = line.lower()
                            if 'loopback' in line_lower:
                                capturing_loopback = True
                            if capturing_loopback and '"' in line:
                                # 提取设备名称（在引号中）
                                start = line.find('"')
                                end = line.rfind('"')
                                if start >= 0 and end > start:
                                    device_name = line[start+1:end]
                                    if device_name and '(loopback)' in device_name:
                                        # 提取不带 (loopback) 的设备名称
                                        clean_name = device_name.replace(' (loopback)', '').strip()
                                        loopback_devices.append({
                                            'full': device_name,
                                            'clean': clean_name
                                        })
                        
                        # 尝试匹配用户选择的设备
                        matched_device = None
                        if self.audio_device:
                            # 首先尝试精确匹配（完整名称）
                            for device in loopback_devices:
                                if self.audio_device.lower() == device['clean'].lower():
                                    matched_device = device['full']
                                    break
                            
                            # 如果没有精确匹配，尝试部分匹配
                            if not matched_device:
                                for device in loopback_devices:
                                    if self.audio_device.lower() in device['clean'].lower():
                                        matched_device = device['full']
                                        break
                        
                        # 如果没有匹配到用户选择的设备，使用第一个可用的 loopback 设备
                        if not matched_device and loopback_devices:
                            matched_device = loopback_devices[0]['full']
                            print(f"DEBUG: 未找到用户选择的设备，使用第一个可用的 loopback 设备: {matched_device}")
                        
                        if matched_device:
                            # 使用 WASAPI loopback 录制系统音频
                            audio_inputs.append({
                                'type': 'wasapi',
                                'device': matched_device,
                                'index': len(cmd)
                            })
                            cmd.extend(['-f', 'wasapi', '-i', f'audio="{matched_device}"'])
                            audio_input_indices.append(len(cmd) - 1)
                            has_audio = True
                            audio_captured = True
                            print(f"DEBUG: 使用 WASAPI loopback 录制系统音频: {matched_device}")
                    
                    except Exception as e:
                        print(f"DEBUG: WASAPI loopback 检测失败: {e}")
                    
                    # 如果 WASAPI 失败，回退到 dshow（立体声混音）
                    if not audio_captured:
                        try:
                            # 测试 dshow 设备
                            test_cmd = ['ffmpeg', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy']
                            test_result = subprocess.run(
                                test_cmd,
                                capture_output=True,
                                timeout=3,
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                            )
                            test_output = test_result.stderr.decode('utf-8', errors='ignore')
                            
                            # 查找立体声混音设备
                            stereo_mix_names = ['立体声混音', 'Stereo Mix', 'stereo mix']
                            device_name = None
                            
                            # 首先检查用户选择的设备是否在列表中
                            if self.audio_device and self.audio_device in test_output:
                                device_name = self.audio_device
                            else:
                                # 查找立体声混音
                                for name in stereo_mix_names:
                                    if name in test_output:
                                        # 提取完整设备名称（可能在引号中）
                                        lines = test_output.split('\n')
                                        for line in lines:
                                            if name in line and '"' in line:
                                                start = line.find('"')
                                                end = line.rfind('"')
                                                if start >= 0 and end > start:
                                                    device_name = line[start+1:end]
                                                    break
                                        if device_name:
                                            break
                            
                            if device_name:
                                audio_inputs.append({
                                    'type': 'dshow',
                                    'device': device_name,
                                    'index': len(cmd)
                                })
                                cmd.extend(['-f', 'dshow', '-i', f'audio="{device_name}"'])
                                audio_input_indices.append(len(cmd) - 1)
                                has_audio = True
                                audio_captured = True
                                print(f"DEBUG: 使用 dshow 录制系统音频: {device_name}")
                            else:
                                print(f"DEBUG: 警告：未找到可用的系统音频录制设备（立体声混音或 WASAPI loopback）")
                                print(f"DEBUG: 提示：Windows 可能需要启用立体声混音设备（在声音设置中启用）")
                        except Exception as e:
                            print(f"DEBUG: dshow 检测失败: {e}")
                else:
                    # Linux/Mac 使用 pulse
                    audio_inputs.append({
                        'type': 'pulse',
                        'device': self.audio_device if self.audio_device else 'default',
                        'index': len(cmd)
                    })
                    cmd.extend(['-f', 'pulse', '-i', self.audio_device if self.audio_device else 'default'])
                    audio_input_indices.append(len(cmd) - 1)
                    has_audio = True
            
            # 麦克风音频（已移至独立录制器，不再从 FFmpeg 直接录制）
            # 注意：麦克风现在通过 MicrophoneAudioRecorder 单独录制
            # 录制完成后在后台线程中与系统音频混合
            print(f"DEBUG: 麦克风状态 - microphone_enabled={self.microphone_enabled}, microphone_audio_recorder={self.microphone_audio_recorder is not None}, microphone_muted={self.microphone_muted}")
            if self.microphone_enabled and not self.microphone_audio_recorder:
                print(f"DEBUG: 警告：麦克风已启用但录制器不可用，麦克风音频将不会被录制")
            elif self.microphone_enabled and self.microphone_muted:
                print(f"DEBUG: 麦克风已静音，不录制麦克风音频")
            
            # 根据质量设置和编码器类型确定编码参数
            # CRF 值范围：0-51，值越小质量越高（适用于 libx264, libopenh264 等）
            quality_crf_map = {
                '原画质': '18',      # 接近无损
                '高质量': '23',      # 高质量（默认）
                '中等质量': '28',    # 中等质量
                '低质量': '32'       # 低质量
            }
            crf_value = quality_crf_map.get(self.quality, '23')
            
            # 根据编码器类型调整编码参数
            # libopenh264 使用 -b:v (bitrate) 而不是 -crf
            use_bitrate = False
            use_cq = False
            if self.video_encoder == 'libopenh264':
                # OpenH264 使用码率控制
                quality_bitrate_map = {
                    '原画质': '10000k',
                    '高质量': '5000k',
                    '中等质量': '3000k',
                    '低质量': '1500k'
                }
                bitrate_value = quality_bitrate_map.get(self.quality, '5000k')
                use_bitrate = True
            elif 'nvenc' in self.video_encoder:
                # NVIDIA 硬件编码器使用 -cq (constant quality) 或 -b:v
                # h264_nvenc 使用 -cq 参数而不是 -crf
                quality_cq_map = {
                    '原画质': '18',
                    '高质量': '23',
                    '中等质量': '28',
                    '低质量': '32'
                }
                cq_value = quality_cq_map.get(self.quality, '23')
                use_bitrate = False  # 使用 CQ 而不是码率
                use_cq = True
            elif 'qsv' in self.video_encoder or 'amf' in self.video_encoder:
                # Intel/AMD 硬件编码器使用码率控制
                quality_bitrate_map = {
                    '原画质': '8000k',
                    '高质量': '4000k',
                    '中等质量': '2500k',
                    '低质量': '1200k'
                }
                bitrate_value = quality_bitrate_map.get(self.quality, '4000k')
                use_bitrate = True
                use_cq = False
            
            # 编码设置
            # 注意：不使用 -movflags +faststart，因为它在录制时可能导致文件不完整
            # 录制完成后可以使用 ffmpeg 重新处理来添加 faststart
            
            # 计算输入流索引
            # 视频输入：0
            # 摄像头输入（如果有）：1
            # 音频输入：从摄像头之后开始（如果有摄像头则从2开始，否则从1开始）
            video_stream_index = 0
            camera_stream_index = 1 if camera_input_index is not None else None
            audio_start_index = 2 if camera_input_index is not None else 1
            
            if not has_audio:
                # 仅视频（可能包含摄像头）
                if camera_input_index is not None:
                    # 有摄像头：需要合成视频
                    # 使用 filter_complex 将屏幕和摄像头合成
                    filter_complex = f"[0:v]scale={self.region['width']}:{self.region['height']}[screen];" \
                                   f"[1:v]scale=320:240[camera];" \
                                   f"[screen][camera]overlay=W-w-10:10[v]"
                    # 构建编码参数
                    encoder_params = ['-c:v', self.video_encoder]
                    
                    # 根据编码器类型设置参数
                    if use_cq and 'nvenc' in self.video_encoder:
                        # h264_nvenc 需要特殊参数
                        encoder_params.extend(['-pix_fmt', 'nv12', '-preset', 'p4', '-cq', cq_value])
                    else:
                        encoder_params.extend(['-pix_fmt', 'yuv420p'])
                        if use_bitrate:
                            encoder_params.extend(['-b:v', bitrate_value])
                        else:
                            encoder_params.extend(['-preset', 'medium', '-crf', crf_value])
                            if self.video_encoder == 'libx264':
                                encoder_params.extend(['-profile:v', 'high', '-level', '4.0'])
                    
                    cmd.extend([
                        '-filter_complex', filter_complex,
                        '-map', '[v]'
                    ])
                    cmd.extend(encoder_params)
                    cmd.extend(['-f', 'mp4', '-y', self.filepath])
                else:
                    # 无摄像头：仅屏幕录制
                    # 构建编码参数
                    encoder_params = ['-c:v', self.video_encoder]
                    
                    # 根据编码器类型设置参数
                    if use_cq and 'nvenc' in self.video_encoder:
                        # h264_nvenc 需要特殊参数
                        encoder_params.extend(['-pix_fmt', 'nv12', '-preset', 'p4', '-cq', cq_value])
                    else:
                        encoder_params.extend(['-pix_fmt', 'yuv420p'])
                        if use_bitrate:
                            encoder_params.extend(['-b:v', bitrate_value])
                        else:
                            encoder_params.extend(['-preset', 'medium', '-crf', crf_value])
                            if self.video_encoder == 'libx264':
                                encoder_params.extend(['-profile:v', 'high', '-level', '4.0'])
                    
                    cmd.extend(encoder_params)
                    cmd.extend(['-f', 'mp4', '-y', self.filepath])
            else:
                # 视频 + 音频（可能包含摄像头）
                filter_parts = []
                map_parts = []
                
                # 视频部分
                if camera_input_index is not None:
                    # 有摄像头：合成屏幕和摄像头
                    filter_parts.append(f"[0:v]scale={self.region['width']}:{self.region['height']}[screen]")
                    filter_parts.append(f"[1:v]scale=320:240[camera]")
                    filter_parts.append(f"[screen][camera]overlay=W-w-10:10[v]")
                    map_parts.extend(['-map', '[v]'])
                else:
                    # 无摄像头：仅屏幕
                    map_parts.extend(['-map', '0:v'])
                
                # 音频部分
                if len(audio_inputs) > 1:
                    # 多个音频输入，需要混音
                    audio_filter_parts = []
                    for i, audio_input in enumerate(audio_inputs):
                        audio_stream_idx = audio_start_index + i
                        audio_filter_parts.append(f'[{audio_stream_idx}:a]')
                    audio_filter = ''.join(audio_filter_parts) + f'amix=inputs={len(audio_inputs)}:duration=longest[a]'
                    filter_parts.append(audio_filter)
                    map_parts.extend(['-map', '[a]'])
                else:
                    # 单个音频输入
                    map_parts.extend(['-map', f'{audio_start_index}:a'])
                
                # 组合所有 filter
                if filter_parts:
                    cmd.extend(['-filter_complex', ';'.join(filter_parts)])
                
                # 添加映射和编码参数
                cmd.extend(map_parts)
                
                # 构建视频编码参数
                video_encoder_params = ['-c:v', self.video_encoder]
                
                # 根据编码器类型设置参数
                if use_cq and 'nvenc' in self.video_encoder:
                    # h264_nvenc 需要特殊参数
                    video_encoder_params.extend(['-pix_fmt', 'nv12', '-preset', 'p4', '-cq', cq_value])
                else:
                    video_encoder_params.extend(['-pix_fmt', 'yuv420p'])
                    if use_bitrate:
                        video_encoder_params.extend(['-b:v', bitrate_value])
                    else:
                        video_encoder_params.extend(['-preset', 'medium', '-crf', crf_value])
                        # 只有 libx264 支持这些参数
                        if self.video_encoder == 'libx264':
                            video_encoder_params.extend(['-profile:v', 'high', '-level', '4.0'])
                
                cmd.extend(video_encoder_params)
                
                # 获取音频质量参数
                audio_params = self._get_audio_quality_params()
                cmd.extend(audio_params)
                
                cmd.extend([
                    '-f', 'mp4',
                    '-shortest',
                    '-y',
                    self.filepath
                ])
            
            print(f"DEBUG: 使用 FFmpeg 录制，命令: {' '.join(cmd)}")
            
            # 启动 FFmpeg 进程
            # 注意：stderr 需要实时读取，否则缓冲区可能满导致进程阻塞
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                bufsize=0,  # 无缓冲
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            # 在后台线程中读取 stderr，避免缓冲区满
            stderr_lines = []
            def read_stderr():
                try:
                    for line in iter(self.ffmpeg_process.stderr.readline, b''):
                        if line:
                            stderr_lines.append(line.decode('utf-8', errors='ignore'))
                except:
                    pass
            
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()
            
            # 等待一小段时间，检查FFmpeg是否正常启动
            time.sleep(0.5)
            if self.ffmpeg_process and self.ffmpeg_process.poll() is not None:
                # FFmpeg进程已经退出，说明启动失败
                print("DEBUG: 错误：FFmpeg进程启动失败，立即退出")
                # 等待stderr线程读取错误信息
                time.sleep(0.5)
                stderr_thread.join(timeout=1)
                stderr_output = '\n'.join(stderr_lines)
                if stderr_output:
                    print(f"DEBUG: FFmpeg错误输出: {stderr_output[-1000:]}")
                
                # 检查是否是摄像头设备错误，如果是，尝试重新构建命令（不包含摄像头）
                if self.camera_enabled and self.camera_device and 'Could not find video device' in stderr_output:
                    print(f"DEBUG: 检测到摄像头设备错误，尝试重新录制（不包含摄像头）")
                    # 停止系统音频录制
                    if system_audio_file and self.system_audio_recorder:
                        try:
                            self.system_audio_recorder.stop_recording()
                            self.system_audio_recorder.close()
                        except:
                            pass
                    
                    # 禁用摄像头，重新构建命令
                    self.camera_enabled = False
                    self.camera_device = None
                    print(f"DEBUG: 已禁用摄像头，重新尝试录制")
                    # 重新调用录制方法（不包含摄像头）
                    return self.try_ffmpeg_recording()
                
                # 停止系统音频录制
                if system_audio_file and self.system_audio_recorder:
                    try:
                        self.system_audio_recorder.stop_recording()
                        self.system_audio_recorder.close()
                    except:
                        pass
                return False
            
            # 等待进程结束或停止
            pause_handled = False  # 标记是否已处理暂停
            while self.running:
                if self.paused:
                    # 暂停时停止当前 FFmpeg 进程（只处理一次）
                    if not pause_handled and self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                        print("DEBUG: 暂停录制，停止当前 FFmpeg 进程...")
                        pause_handled = True
                        
                        # 暂停系统音频录制
                        if self.system_audio_recorder and self.system_audio_recorder.is_recording:
                            self.system_audio_recorder.pause_recording()
                        
                        # 暂停麦克风音频录制
                        if self.microphone_audio_recorder and self.microphone_audio_recorder.is_recording:
                            self.microphone_audio_recorder.pause_recording()
                            print("DEBUG: 麦克风音频录制已暂停")
                        
                        # 计算当前片段的结束时间
                        current_time = time.time()
                        if self.recording_start_time:
                            segment_end_time = current_time - self.recording_start_time - (self.system_audio_recorder.total_pause_duration if self.system_audio_recorder else 0)
                        else:
                            segment_end_time = self.last_segment_end_time + 1.0
                        
                        # 强制关闭FFmpeg进程，确保进程被完全关闭
                        self._force_close_ffmpeg_process(self.ffmpeg_process, timeout=5)
                        
                        # 等待文件写入完成
                        time.sleep(0.5)
                        
                        # 保存当前片段到列表
                        if os.path.exists(self.filepath):
                            # 如果这是第一个片段（使用原始文件路径），需要先复制到片段目录
                            if self.filepath == self.base_filepath:
                                first_segment = os.path.join(self.segment_dir, f'segment_{self.segment_index:04d}.mp4')
                                import shutil
                                shutil.copy2(self.filepath, first_segment)
                                # 添加到片段列表
                                self._add_segment_to_list(first_segment, start_time=self.last_segment_end_time, end_time=segment_end_time)
                                self.segment_index += 1
                            else:
                                # 更新最后一个片段的结束时间
                                self._update_last_segment_end_time(segment_end_time)
                                # 如果还没有添加到列表，添加它
                                if self.filepath not in self.video_segments:
                                    self._add_segment_to_list(self.filepath, start_time=self.last_segment_end_time, end_time=segment_end_time)
                        else:
                            print(f"DEBUG: 警告：片段文件不存在: {self.filepath}")
                        
                        # 创建新的片段文件路径（恢复时使用）
                        current_segment = os.path.join(self.segment_dir, f'segment_{self.segment_index:04d}.mp4')
                        self.segment_index += 1
                        self.filepath = current_segment
                        print(f"DEBUG: 准备恢复时使用新片段文件: {self.filepath}")
                        
                        # 清空 FFmpeg 进程引用（进程已关闭，从列表中移除）
                        old_process = self.ffmpeg_process
                        self.ffmpeg_process = None
                        if old_process:
                            # 确保进程真的被关闭
                            try:
                                if old_process.poll() is None:
                                    print(f"DEBUG: 警告：暂停时进程仍在运行 (PID: {old_process.pid})，强制关闭...")
                                    self._force_close_ffmpeg_process(old_process, timeout=2)
                            except:
                                pass
                            # 从列表中移除
                            with self.ffmpeg_process_lock:
                                if old_process in self.ffmpeg_processes:
                                    self.ffmpeg_processes.remove(old_process)
                    
                    # 等待恢复
                    time.sleep(0.1)
                else:
                    # 如果暂停后恢复，需要重新启动 FFmpeg
                    if pause_handled and self.ffmpeg_process is None and self.running:
                        print("DEBUG: 恢复录制，重新启动 FFmpeg 进程...")
                        pause_handled = False  # 重置标记
                        
                        # 恢复系统音频录制
                        if self.system_audio_recorder and self.system_audio_recorder.is_recording:
                            self.system_audio_recorder.resume_recording()
                        
                        # 恢复麦克风音频录制
                        if self.microphone_audio_recorder and self.microphone_audio_recorder.is_recording:
                            self.microphone_audio_recorder.resume_recording()
                            print("DEBUG: 麦克风音频录制已恢复")
                        
                        # 恢复录制时，在主线程中直接启动FFmpeg进程（不启动新的while循环）
                        try:
                            # 确保旧进程已完全关闭（双重检查）
                            if self.ffmpeg_process is not None:
                                print("DEBUG: 恢复录制前，确保旧FFmpeg进程已关闭...")
                                self._force_close_ffmpeg_process(self.ffmpeg_process, timeout=3)
                                self.ffmpeg_process = None
                            
                            # 等待一小段时间，确保旧进程完全关闭
                            time.sleep(0.3)
                            
                            # 直接启动FFmpeg进程（不启动while循环）
                            if self.ffmpeg_process is None:
                                if self._start_ffmpeg_process_only():
                                    print("DEBUG: FFmpeg进程已成功启动（恢复录制）")
                                else:
                                    print("DEBUG: 警告：FFmpeg进程启动失败（恢复录制）")
                            else:
                                print("DEBUG: FFmpeg进程已存在，跳过重新启动")
                        except Exception as e:
                            print(f"DEBUG: 恢复录制时出错: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    # 检查进程是否还在运行
                    if self.ffmpeg_process:
                        poll_result = self.ffmpeg_process.poll()
                        if poll_result is not None:
                            # 进程已结束，从列表中移除
                            old_process = self.ffmpeg_process
                            self.ffmpeg_process = None
                            with self.ffmpeg_process_lock:
                                if old_process in self.ffmpeg_processes:
                                    self.ffmpeg_processes.remove(old_process)
                            print(f"DEBUG: FFmpeg进程已结束 (返回码: {poll_result})")
                            break
                    time.sleep(0.1)
            
            # 停止 FFmpeg - 使用强制关闭方法确保进程被完全关闭
            if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                # 计算当前片段的结束时间
                current_time = time.time()
                if self.recording_start_time:
                    segment_end_time = current_time - self.recording_start_time - (self.system_audio_recorder.total_pause_duration if self.system_audio_recorder else 0)
                else:
                    segment_end_time = self.last_segment_end_time + 1.0
                
                # 强制关闭FFmpeg进程
                self._force_close_ffmpeg_process(self.ffmpeg_process, timeout=15)
            
            # 等待文件写入完成
            time.sleep(0.5)
            
            # 如果有片段列表，说明有暂停/恢复，需要保存最后一个片段
            if len(self.segment_list) > 0 or self.filepath != self.base_filepath:
                # 如果当前文件路径不是基础路径，说明是片段文件，需要保存
                if self.filepath != self.base_filepath:
                    # 检查文件是否存在（可能已被移动或清理，这是正常的）
                    if os.path.exists(self.filepath):
                        # 计算结束时间
                        current_time = time.time()
                        if self.recording_start_time:
                            segment_end_time = current_time - self.recording_start_time - (self.system_audio_recorder.total_pause_duration if self.system_audio_recorder else 0)
                        else:
                            segment_end_time = self.last_segment_end_time + 1.0
                        
                        # 添加到片段列表
                        self._add_segment_to_list(self.filepath, start_time=self.last_segment_end_time, end_time=segment_end_time)
                    else:
                        print(f"DEBUG: 最后一个片段文件不存在（可能已被移动）: {self.filepath}")
                else:
                    print(f"DEBUG: 当前文件路径是基础路径，不保存: {self.filepath}")
            
            # 停止系统音频录制 - 优化资源释放（使用锁保护，避免多线程冲突）
            audio_saved = False
            microphone_audio_saved = False  # 麦克风音频保存状态
            
            # 使用锁保护，确保同一时间只有一个线程操作音频录制器
            with self.audio_recorder_lock:
                # 检查是否已经在停止中，避免重复操作
                if self.audio_stopping:
                    print(f"DEBUG: 音频录制器正在停止中，跳过重复操作")
                else:
                    self.audio_stopping = True
                    
                    # === 停止系统音频录制器 ===
                    # 保存本地引用，避免在stop()方法中被清空
                    audio_recorder = self.system_audio_recorder
                    # 使用实例变量而不是局部变量，因为中途启用音频时会设置实例变量
                    if self.system_audio_file and audio_recorder:
                        try:
                            print(f"DEBUG: 开始停止并保存系统音频录制...")
                            # 先停止录制
                            try:
                                audio_recorder.stop_recording()
                            except Exception as stop_error:
                                print(f"DEBUG: 停止系统音频录制时出错: {stop_error}")
                                import traceback
                                traceback.print_exc()
                            
                            # 等待一小段时间确保线程完全结束
                            time.sleep(0.5)
                            
                            # 保存录制
                            try:
                                audio_saved = audio_recorder.save_recording(self.system_audio_file)
                                if audio_saved:
                                    print(f"DEBUG: 系统音频已成功保存到: {self.system_audio_file}")
                                    # 检查文件是否存在和大小
                                    if os.path.exists(self.system_audio_file):
                                        file_size = os.path.getsize(self.system_audio_file)
                                        print(f"DEBUG: 系统音频文件大小: {file_size} 字节 ({file_size / 1024:.2f} KB)")
                                    else:
                                        print(f"DEBUG: 警告：系统音频文件不存在: {self.system_audio_file}")
                                        audio_saved = False
                                else:
                                    print(f"DEBUG: 警告：系统音频保存失败")
                            except Exception as save_error:
                                print(f"DEBUG: 保存系统音频录制时出错: {save_error}")
                                import traceback
                                traceback.print_exc()
                                audio_saved = False
                            
                            # 关闭资源
                            try:
                                audio_recorder.close()
                            except Exception as close_error:
                                print(f"DEBUG: 关闭系统音频录制器时出错: {close_error}")
                                import traceback
                                traceback.print_exc()
                            
                            # 清空引用（仅在成功保存后）
                            if audio_saved:
                                self.system_audio_recorder = None
                        except Exception as e:
                            print(f"DEBUG: 停止系统音频录制时出错: {e}")
                            import traceback
                            traceback.print_exc()
                            # 即使出错也尝试清理
                            try:
                                if audio_recorder:
                                    audio_recorder.close()
                            except:
                                pass
                            finally:
                                # 确保清空引用
                                self.system_audio_recorder = None
                    else:
                        print(f"DEBUG: 系统音频录制器或文件路径不存在，跳过停止操作")
                    
                    # === 停止麦克风音频录制器 ===
                    microphone_recorder = self.microphone_audio_recorder
                    if self.microphone_audio_file and microphone_recorder:
                        try:
                            print(f"DEBUG: 开始停止并保存麦克风音频录制...")
                            # 先停止录制
                            try:
                                microphone_recorder.stop_recording()
                            except Exception as stop_error:
                                print(f"DEBUG: 停止麦克风音频录制时出错: {stop_error}")
                                import traceback
                                traceback.print_exc()
                            
                            # 等待一小段时间确保线程完全结束
                            time.sleep(0.5)
                            
                            # 保存录制
                            try:
                                microphone_audio_saved = microphone_recorder.save_recording(self.microphone_audio_file)
                                if microphone_audio_saved:
                                    print(f"DEBUG: 麦克风音频已成功保存到: {self.microphone_audio_file}")
                                    # 检查文件是否存在和大小
                                    if os.path.exists(self.microphone_audio_file):
                                        file_size = os.path.getsize(self.microphone_audio_file)
                                        print(f"DEBUG: 麦克风音频文件大小: {file_size} 字节 ({file_size / 1024:.2f} KB)")
                                    else:
                                        print(f"DEBUG: 警告：麦克风音频文件不存在: {self.microphone_audio_file}")
                                        microphone_audio_saved = False
                                else:
                                    print(f"DEBUG: 警告：麦克风音频保存失败")
                            except Exception as save_error:
                                print(f"DEBUG: 保存麦克风音频录制时出错: {save_error}")
                                import traceback
                                traceback.print_exc()
                                microphone_audio_saved = False
                            
                            # 关闭资源
                            try:
                                microphone_recorder.close()
                            except Exception as close_error:
                                print(f"DEBUG: 关闭麦克风音频录制器时出错: {close_error}")
                                import traceback
                                traceback.print_exc()
                            
                            # 清空引用（仅在成功保存后）
                            if microphone_audio_saved:
                                self.microphone_audio_recorder = None
                        except Exception as e:
                            print(f"DEBUG: 停止麦克风音频录制时出错: {e}")
                            import traceback
                            traceback.print_exc()
                            # 即使出错也尝试清理
                            try:
                                if microphone_recorder:
                                    microphone_recorder.close()
                            except:
                                pass
                            finally:
                                # 确保清空引用
                                self.microphone_audio_recorder = None
                    else:
                        print(f"DEBUG: 麦克风音频录制器或文件路径不存在，跳过停止操作")
                    
                    self.audio_stopping = False
            
            # 保存音频保存状态，用于后台处理线程
            self.audio_saved = audio_saved
            self.microphone_audio_saved = microphone_audio_saved
            
            # 注意：音视频合并现在移到后台处理线程中进行，在片段合并之后
            # 这样可以确保使用正确的文件路径（base_filepath）

            # 等待 stderr 读取线程结束
            stderr_thread.join(timeout=1)
            
            # 获取 FFmpeg 的错误输出
            stderr_output = '\n'.join(stderr_lines)
            if stderr_output:
                # 只显示最后500字符，避免输出过长
                print(f"DEBUG: FFmpeg 输出: {stderr_output[-500:]}")
                # 检查是否有错误
                if 'error' in stderr_output.lower() or 'failed' in stderr_output.lower():
                    print(f"DEBUG: FFmpeg 可能遇到错误，完整输出: {stderr_output}")
            
            # 检查返回码
            return_code = self.ffmpeg_process.returncode
            print(f"DEBUG: FFmpeg 进程返回码: {return_code}")
            
            # 等待文件系统同步（重要：确保文件完全写入磁盘）
            time.sleep(1.0)  # 增加等待时间
            
            # 检查文件是否存在
            # 注意：如果有片段列表，文件可能已被移动到片段目录，这是正常的
            if len(self.video_segments) > 0:
                # 有片段列表，说明使用了分段录制，文件可能已被移动
                # 这种情况下，只要FFmpeg进程正常结束，就认为录制成功
                if self.ffmpeg_process and self.ffmpeg_process.returncode == 0:
                    print(f"DEBUG: FFmpeg 录制完成（分段录制模式），片段已保存")
                    return True
                else:
                    print(f"DEBUG: FFmpeg 录制失败（分段录制模式），返回码: {self.ffmpeg_process.returncode if self.ffmpeg_process else 'None'}")
                    return False
            elif os.path.exists(self.filepath):
                # 没有片段列表，检查最终文件
                file_size = os.path.getsize(self.filepath)
                if file_size > 1024:  # 至少 1KB
                    print(f"DEBUG: FFmpeg 录制完成，文件保存至: {self.filepath}, 大小: {file_size / 1024 / 1024:.2f} MB")
                    
                    # 验证文件格式
                    try:
                        with open(self.filepath, 'rb') as f:
                            header = f.read(12)
                            if b'ftyp' in header or header[:4] == b'\x00\x00\x00' or header[4:8] == b'ftyp':
                                print("DEBUG: 文件格式验证通过（MP4）")
                            else:
                                print(f"DEBUG: 警告：文件格式可能不正确，文件头: {header[:12].hex()}")
                    except Exception as e:
                        print(f"DEBUG: 警告：无法读取文件进行验证: {e}")
                    
                    return True
                else:
                    print(f"DEBUG: 警告：文件存在但大小异常（{file_size} 字节）")
                    return False
            else:
                # 文件不存在，但如果FFmpeg正常结束，可能是分段录制模式
                if self.ffmpeg_process and self.ffmpeg_process.returncode == 0:
                    print(f"DEBUG: FFmpeg 录制完成，但文件不存在（可能是分段录制模式）: {self.filepath}")
                    return True  # 分段录制模式下，文件可能已被移动，这是正常的
                else:
                    print(f"DEBUG: 错误：FFmpeg 录制完成，但文件不存在: {self.filepath}")
                    return False
            
        except Exception as e:
            print(f"DEBUG: FFmpeg 录制失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self):
        """执行录屏"""
        if self.try_ffmpeg_recording():
            return
        else:
            error_msg = "FFmpeg 录制失败，请确保已安装 FFmpeg"
            print(f"ERROR: {error_msg}")
            # 发出录制失败信号
            self.recording_failed.emit(error_msg)
    
    def stop(self):
        """停止录制"""
        self.running = False
        
        # 强制关闭FFmpeg进程，确保进程被完全关闭
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self._force_close_ffmpeg_process(self.ffmpeg_process, timeout=10)
        
        # 等待文件写入完成
        time.sleep(0.5)
        
        # 计算最后一个片段的结束时间
        current_time = time.time()
        if self.recording_start_time:
            segment_end_time = current_time - self.recording_start_time - (self.system_audio_recorder.total_pause_duration if self.system_audio_recorder else 0)
        else:
            segment_end_time = self.last_segment_end_time + 1.0
        
        # 如果没有片段列表，说明没有暂停/恢复，文件已经在正确位置（base_filepath）
        # 但可能还需要合并音频，所以也启动处理线程
        if len(self.segment_list) == 0:
            print(f"DEBUG: 没有暂停/恢复，录制文件已在最终位置: {self.base_filepath}")
            # 启动后台线程处理可能的音频合并
            self._start_video_processing_thread()
            return
        
        # 如果有片段列表，需要保存最后一个片段
        if self.filepath != self.base_filepath:
            # 检查文件是否存在
            if os.path.exists(self.filepath):
                # 添加到片段列表（如果还没有添加）
                self._add_segment_to_list(self.filepath, start_time=self.last_segment_end_time, end_time=segment_end_time)
            else:
                print(f"DEBUG: 最后一个片段文件不存在（可能已被移动）: {self.filepath}")
        else:
            # 如果filepath是base_filepath，说明这是第一个片段，需要添加到列表
            if os.path.exists(self.filepath):
                first_segment = os.path.join(self.segment_dir, f'segment_{self.segment_index:04d}.mp4')
                import shutil
                if not os.path.exists(first_segment):
                    shutil.copy2(self.filepath, first_segment)
                self._add_segment_to_list(first_segment, start_time=0.0, end_time=segment_end_time)
                self.segment_index += 1
        
        # 等待音频文件保存完成（如果正在保存）- 优化：减少等待时间
        # 给音频保存一些额外时间，确保文件完全写入
        # 使用锁保护，避免与try_ffmpeg_recording中的音频停止操作冲突
        with self.audio_recorder_lock:
            if self.system_audio_recorder and not self.audio_stopping:
                print("DEBUG: 等待音频保存完成...")
                max_wait_time = 3  # 优化：最多等待3秒（从5秒减少）
                wait_interval = 0.1  # 每0.1秒检查一次
                waited_time = 0
                last_size = 0
                stable_count = 0
                while waited_time < max_wait_time:
                    if self.audio_saved:
                        print("DEBUG: 音频已保存完成")
                        break
                    # 检查音频文件是否存在
                    if self.system_audio_file and os.path.exists(self.system_audio_file):
                        file_size = os.path.getsize(self.system_audio_file)
                        if file_size > 0:
                            # 如果文件大小连续2次检查都相同，认为文件已保存完成
                            if file_size == last_size:
                                stable_count += 1
                                if stable_count >= 2:
                                    print(f"DEBUG: 检测到音频文件已存在且稳定，大小: {file_size} 字节")
                                    self.audio_saved = True
                                    break
                            else:
                                stable_count = 0
                            last_size = file_size
                    time.sleep(wait_interval)
                    waited_time += wait_interval
                if not self.audio_saved:
                    print("DEBUG: 警告：等待音频保存超时，但将继续处理")
            elif self.audio_stopping:
                print("DEBUG: 音频录制器正在停止中，等待完成...")
                # 等待停止完成（优化：减少等待时间）
                max_wait_time = 5  # 优化：最多等待5秒（从10秒减少）
                wait_interval = 0.1  # 优化：每0.1秒检查一次（从0.2秒减少）
                waited_time = 0
                while waited_time < max_wait_time and self.audio_stopping:
                    time.sleep(wait_interval)
                    waited_time += wait_interval
                if self.audio_stopping:
                    print("DEBUG: 警告：等待音频停止超时")
                else:
                    print("DEBUG: 音频停止完成")
        
        # 启动后台线程处理视频合并（避免阻塞）
        self._start_video_processing_thread()
        
        # 注意：不在这里停止音频录制器，让try_ffmpeg_recording()方法完成音频保存
        # 音频录制器会在try_ffmpeg_recording()完成后自动清理
    
    def _send_completion_signal(self):
        """发送完成信号的辅助函数"""
        try:
            if os.path.exists(self.base_filepath):
                file_size = os.path.getsize(self.base_filepath)
                if file_size > 0:
                    print(f"DEBUG: 准备发送视频处理完成信号，文件: {self.base_filepath}, 大小: {file_size} 字节")
                    try:
                        self.video_processing_complete.emit(self.base_filepath, file_size)
                    except Exception as emit_error:
                        print(f"DEBUG: 发送视频处理完成信号失败: {emit_error}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"DEBUG: 警告：最终文件大小为0: {self.base_filepath}")
                    try:
                        self.video_processing_complete.emit(self.base_filepath, 0)
                    except:
                        pass
            else:
                print(f"DEBUG: 警告：最终文件不存在: {self.base_filepath}")
                try:
                    # 创建一个空文件作为占位符
                    with open(self.base_filepath, 'w') as f:
                        pass
                    self.video_processing_complete.emit(self.base_filepath, 0)
                except Exception as fallback_error:
                    print(f"DEBUG: 创建占位符文件也失败: {fallback_error}")
        except Exception as signal_error:
            print(f"DEBUG: 发送完成信号时出错: {signal_error}")
            import traceback
            traceback.print_exc()
    
    def _start_video_processing_thread(self):
        """启动后台线程处理视频合并"""
        import threading
        
        def process_video():
            try:
                print("DEBUG: 开始处理视频...")
                # 确保所有异常都被捕获，避免闪退
                import sys
                
                # 尝试从文件加载片段列表（如果存在）
                if os.path.exists(self.segment_list_file):
                    self._load_segment_list()
                
                # 按照片段列表进行合并
                if len(self.segment_list) > 1:
                    print(f"DEBUG: 检测到 {len(self.segment_list)} 个视频片段（从列表文件），开始合并...")
                    try:
                        self._merge_segments()
                        print("DEBUG: 片段合并完成")
                    except Exception as merge_error:
                        print(f"DEBUG: 合并片段时出错: {merge_error}")
                        import traceback
                        traceback.print_exc()
                        # 即使合并失败，也尝试使用第一个片段作为最终文件
                        try:
                            if len(self.segment_list) > 0:
                                import shutil
                                first_segment = self.segment_list[0]['video_path']
                                if os.path.exists(first_segment) and os.path.getsize(first_segment) > 0:
                                    shutil.copy2(first_segment, self.base_filepath)
                                    print(f"DEBUG: 合并失败，已使用第一个片段作为最终文件: {first_segment}")
                        except Exception as fallback_error:
                            print(f"DEBUG: 使用第一个片段作为最终文件也失败: {fallback_error}")
                        # 无论是否成功，都继续执行后续的音视频合并和信号发送
                elif len(self.segment_list) == 1:
                    # 只有一个片段，直接移动到最终文件路径
                    try:
                        first_segment_path = self.segment_list[0]['video_path']
                        if os.path.exists(first_segment_path):
                            import shutil
                            shutil.move(first_segment_path, self.base_filepath)
                            print(f"DEBUG: 单个片段，直接移动到最终文件: {self.base_filepath}")
                        else:
                            print(f"DEBUG: 警告：片段文件不存在: {first_segment_path}")
                            # 即使文件不存在，也发送完成信号
                            self._send_completion_signal()
                            return
                    except Exception as move_error:
                        print(f"DEBUG: 移动片段文件时出错: {move_error}")
                        import traceback
                        traceback.print_exc()
                        # 即使移动失败，也发送完成信号
                        self._send_completion_signal()
                        return
                elif len(self.video_segments) > 1:
                    # 如果没有片段列表但有video_segments，使用旧的合并方式
                    print(f"DEBUG: 检测到 {len(self.video_segments)} 个视频片段（旧格式），开始合并...")
                    try:
                        self._merge_segments()
                        print("DEBUG: 片段合并完成")
                    except Exception as merge_error:
                        print(f"DEBUG: 合并片段时出错: {merge_error}")
                        import traceback
                        traceback.print_exc()
                else:
                    print("DEBUG: 警告：没有视频片段")
                    # 没有片段时，检查文件是否存在，如果存在则继续处理音频合并
                    if os.path.exists(self.base_filepath):
                        print("DEBUG: 文件已存在，继续处理音频合并")
                        # 继续执行后续的音视频合并逻辑
                    else:
                        # 文件不存在时，发送完成信号
                        self._send_completion_signal()
                        return
                
                # 片段合并完成后，如果有系统音频，进行音视频合并
                final_video_file = self.base_filepath
                print(f"DEBUG: 检查音视频合并条件:")
                print(f"DEBUG:   audio_enabled={self.audio_enabled}")
                print(f"DEBUG:   system_audio_file={self.system_audio_file}")
                print(f"DEBUG:   audio_saved={self.audio_saved}")
                
                # 检查音频文件是否存在和有效（不依赖audio_saved标志，因为可能还没设置）
                # 如果音频文件还没保存完成，等待一段时间（优化：减少等待时间）
                audio_file_valid = False
                if self.system_audio_file:
                    # 如果audio_saved为False或文件不存在，等待音频文件保存完成
                    if not self.audio_saved or not os.path.exists(self.system_audio_file):
                        print("DEBUG:   音频文件可能还在保存中，等待...")
                        import time
                        max_wait_time = 5  # 优化：最多等待5秒（从10秒减少）
                        wait_interval = 0.1  # 优化：每0.1秒检查一次（从0.2秒减少，响应更快）
                        waited_time = 0
                        last_size = 0
                        stable_count = 0  # 文件大小稳定的次数
                        while waited_time < max_wait_time:
                            if os.path.exists(self.system_audio_file):
                                file_size = os.path.getsize(self.system_audio_file)
                                if file_size > 0:
                                    # 如果文件大小连续2次检查都相同，认为文件已保存完成
                                    if file_size == last_size:
                                        stable_count += 1
                                        if stable_count >= 2:
                                            print(f"DEBUG:   音频文件已保存，大小: {file_size} 字节")
                                            self.audio_saved = True
                                            audio_file_valid = True
                                            break
                                    else:
                                        stable_count = 0
                                    last_size = file_size
                            time.sleep(wait_interval)
                            waited_time += wait_interval
                        if not audio_file_valid:
                            # 如果超时但文件存在且大小>0，仍然认为有效
                            if os.path.exists(self.system_audio_file) and os.path.getsize(self.system_audio_file) > 0:
                                print("DEBUG:   等待超时但文件存在，继续使用")
                                audio_file_valid = True
                            else:
                                print("DEBUG:   警告：等待音频文件保存超时")
                    else:
                        # audio_saved为True，直接检查文件
                        if os.path.exists(self.system_audio_file):
                            audio_file_size = os.path.getsize(self.system_audio_file)
                            print(f"DEBUG:   音频文件存在: True, 大小: {audio_file_size} 字节")
                            if audio_file_size > 0:
                                audio_file_valid = True
                        else:
                            print(f"DEBUG:   音频文件存在: False（audio_saved=True但文件不存在）")
                
                # 检查麦克风音频文件是否存在和有效（优化：减少等待时间）
                microphone_file_valid = False
                if self.microphone_audio_file:
                    # 如果麦克风音频文件还没保存完成，等待一段时间
                    if not self.microphone_audio_saved or not os.path.exists(self.microphone_audio_file):
                        print("DEBUG:   麦克风音频文件可能还在保存中，等待...")
                        import time
                        max_wait_time = 5  # 优化：最多等待5秒（从10秒减少）
                        wait_interval = 0.1  # 优化：每0.1秒检查一次（从0.2秒减少，响应更快）
                        waited_time = 0
                        last_size = 0
                        stable_count = 0  # 文件大小稳定的次数
                        while waited_time < max_wait_time:
                            if os.path.exists(self.microphone_audio_file):
                                file_size = os.path.getsize(self.microphone_audio_file)
                                if file_size > 0:
                                    # 如果文件大小连续2次检查都相同，认为文件已保存完成
                                    if file_size == last_size:
                                        stable_count += 1
                                        if stable_count >= 2:
                                            print(f"DEBUG:   麦克风音频文件已保存，大小: {file_size} 字节")
                                            self.microphone_audio_saved = True
                                            microphone_file_valid = True
                                            break
                                    else:
                                        stable_count = 0
                                    last_size = file_size
                            time.sleep(wait_interval)
                            waited_time += wait_interval
                        if not microphone_file_valid:
                            # 如果超时但文件存在且大小>0，仍然认为有效
                            if os.path.exists(self.microphone_audio_file) and os.path.getsize(self.microphone_audio_file) > 0:
                                print("DEBUG:   等待超时但文件存在，继续使用")
                                microphone_file_valid = True
                            else:
                                print("DEBUG:   警告：等待麦克风音频文件保存超时")
                    else:
                        # microphone_audio_saved为True，直接检查文件
                        if os.path.exists(self.microphone_audio_file):
                            microphone_file_size = os.path.getsize(self.microphone_audio_file)
                            print(f"DEBUG:   麦克风音频文件存在: True, 大小: {microphone_file_size} 字节")
                            if microphone_file_size > 0:
                                microphone_file_valid = True
                        else:
                            print(f"DEBUG:   麦克风音频文件存在: False（microphone_audio_saved=True但文件不存在）")
                
                if not microphone_file_valid and self.microphone_audio_file:
                    print(f"DEBUG:   麦克风音频文件存在: False 或无效")
                
                print(f"DEBUG:   最终视频文件存在: {os.path.exists(final_video_file)}")
                print(f"DEBUG:   系统音频文件有效: {audio_file_valid}")
                print(f"DEBUG:   麦克风音频文件有效: {microphone_file_valid}")
                
                # 决定是否需要合并音频及合并方式
                has_system_audio = self.system_audio_file and audio_file_valid
                has_microphone_audio = self.microphone_audio_file and microphone_file_valid
                
                # 如果有任何音频文件存在且有效，就进行音视频合并
                if (has_system_audio or has_microphone_audio) and os.path.exists(final_video_file):
                    print(f"DEBUG: 检测到音频文件，正在进行音视频合并... (系统音频: {has_system_audio}, 麦克风音频: {has_microphone_audio})")
                    
                    # 发送进度信号
                    try:
                        self.merge_progress.emit("正在合并音视频...", 0, 100)
                    except:
                        pass
                    
                    # 创建临时视频文件路径，确保在同一磁盘上
                    import tempfile
                    temp_video_file = os.path.join(os.path.dirname(final_video_file), "temp_video_without_audio.mp4")
                    temp_mixed_audio = None  # 混合后的音频文件（如果需要）
                    
                    # 将视频文件重命名为临时文件
                    try:
                        os.rename(final_video_file, temp_video_file)
                        
                        # 根据音频文件情况决定合并策略
                        if has_system_audio and has_microphone_audio:
                            # 情况1：同时有系统音频和麦克风音频，需要先混合
                            print("DEBUG: 同时有系统音频和麦克风音频，先混合音频...")
                            temp_mixed_audio = os.path.join(os.path.dirname(final_video_file), "temp_mixed_audio.wav")
                            
                            # 使用 FFmpeg 混合两个音频源（amix 滴器）- 优化速度
                            mix_cmd = [
                                'ffmpeg',
                                '-i', self.system_audio_file,  # 系统音频（扬声器）
                                '-i', self.microphone_audio_file,  # 麦克风音频
                                '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=1[aout]',  # 减少dropout_transition以加快处理
                                '-map', '[aout]',
                                '-c:a', 'pcm_s16le',  # 使用PCM编码以保证质量
                                '-ar', '44100',  # 标准采样率（比48000处理更快）
                                '-ac', '2',  # 双声道
                                '-threads', '0',  # 使用所有可用CPU线程
                                '-y',  # 覆盖输出文件
                                temp_mixed_audio  # 输出文件
                            ]
                            
                            print(f"DEBUG: 混合音频命令: {' '.join(mix_cmd)}")
                            mix_process = subprocess.Popen(
                                mix_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                stdin=subprocess.PIPE,
                                text=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                            )
                            
                            # 等待混合完成（优化：减少超时时间，因为处理应该更快）
                            stdout, stderr = mix_process.communicate(timeout=180)  # 优化：3分钟超时（从5分钟减少）
                            if mix_process.returncode == 0:
                                print("DEBUG: 音频混合成功")
                                audio_source = temp_mixed_audio
                                try:
                                    self.merge_progress.emit("音频混合完成，正在合并视频...", 50, 100)
                                except:
                                    pass
                            else:
                                print(f"DEBUG: 音频混合失败，返回码: {mix_process.returncode}")
                                print(f"DEBUG: 错误输出: {stderr[-500:] if stderr else '无错误信息'}")
                                # 如果混合失败，仅使用系统音频
                                print("DEBUG: 回退到仅使用系统音频")
                                audio_source = self.system_audio_file
                        elif has_system_audio:
                            # 情况2：仅有系统音频
                            print("DEBUG: 仅有系统音频，直接合并")
                            audio_source = self.system_audio_file
                        else:
                            # 情况3：仅有麦克风音频
                            print("DEBUG: 仅有麦克风音频，直接合并")
                            audio_source = self.microphone_audio_file
                        
                        # 使用 FFmpeg 合并音视频 - 优化速度
                        merge_cmd = [
                            'ffmpeg',
                            '-i', temp_video_file,  # 视频文件
                            '-i', audio_source,  # 音频文件（已混合或单一源）
                            '-c:v', 'copy',  # 复制视频流（不重新编码，最快）
                            '-c:a', 'aac',   # 音频编码为 AAC
                            '-b:a', '192k',  # 优化比特率（192k足够，编码更快）
                            '-ac', '2',      # 双声道
                            '-ar', '44100',  # 标准采样率（比48000编码更快）
                            '-preset', 'fast',  # 使用快速编码预设
                            '-threads', '0',  # 使用所有可用CPU线程
                            '-af', 'aresample=async=1',  # 音频重采样
                            '-shortest',     # 以较短的流为准
                            '-y',  # 覆盖输出文件
                            final_video_file  # 最终输出文件
                        ]
                        
                        print(f"DEBUG: 合并命令: {' '.join(merge_cmd)}")
                        merge_process = None
                        try:
                            print("DEBUG: 开始执行音视频合并...")
                            merge_process = subprocess.Popen(
                                merge_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                stdin=subprocess.PIPE,
                                text=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                            )
                            
                            # 等待进程完成，带超时（优化：减少超时时间）
                            try:
                                stdout, stderr = merge_process.communicate(timeout=300)  # 优化：5分钟超时（从10分钟减少，因为编码更快了）
                                return_code = merge_process.returncode
                                print(f"DEBUG: 音视频合并进程返回码: {return_code}")
                                
                                if return_code == 0:
                                    print("DEBUG: 音视频合并成功")
                                    try:
                                        self.merge_progress.emit("音视频合并完成", 100, 100)
                                    except:
                                        pass
                                    # 验证最终文件
                                    if os.path.exists(final_video_file):
                                        final_size = os.path.getsize(final_video_file)
                                        print(f"DEBUG: 最终视频文件大小: {final_size / 1024 / 1024:.2f} MB")
                                    # 删除临时文件
                                    try:
                                        if os.path.exists(temp_video_file):
                                            os.remove(temp_video_file)
                                        if self.system_audio_file and os.path.exists(self.system_audio_file):
                                            os.remove(self.system_audio_file)
                                        if self.microphone_audio_file and os.path.exists(self.microphone_audio_file):
                                            os.remove(self.microphone_audio_file)
                                        if temp_mixed_audio and os.path.exists(temp_mixed_audio):
                                            os.remove(temp_mixed_audio)
                                    except Exception as e:
                                        print(f"DEBUG: 删除临时文件失败: {e}")
                                else:
                                    error_output = stderr[-1000:] if stderr else '无错误信息'
                                    print(f"DEBUG: 音视频合并失败，返回码: {return_code}")
                                    print(f"DEBUG: 错误输出: {error_output}")
                                    # 恢复原始视频文件
                                    try:
                                        if os.path.exists(temp_video_file):
                                            os.rename(temp_video_file, final_video_file)
                                            print("DEBUG: 已恢复原始视频文件（无音频）")
                                    except Exception as e:
                                        print(f"DEBUG: 恢复原始视频文件失败: {e}")
                            except subprocess.TimeoutExpired:
                                print("DEBUG: 音视频合并超时（10分钟），尝试终止进程...")
                                # 强制关闭进程
                                if merge_process:
                                    self._force_close_ffmpeg_process(merge_process, timeout=5)
                                # 恢复原始视频文件
                                try:
                                    if os.path.exists(temp_video_file):
                                        os.rename(temp_video_file, final_video_file)
                                        print("DEBUG: 已恢复原始视频文件（无音频）")
                                except Exception as e:
                                    print(f"DEBUG: 恢复原始视频文件失败: {e}")
                        except Exception as merge_error:
                            print(f"DEBUG: 音视频合并过程异常: {merge_error}")
                            import traceback
                            traceback.print_exc()
                            # 确保进程被关闭
                            if merge_process:
                                try:
                                    self._force_close_ffmpeg_process(merge_process, timeout=3)
                                except:
                                    pass
                            # 恢复原始视频文件
                            try:
                                if os.path.exists(temp_video_file):
                                    os.rename(temp_video_file, final_video_file)
                                    print("DEBUG: 已恢复原始视频文件（无音频）")
                            except Exception as e:
                                print(f"DEBUG: 恢复原始视频文件失败: {e}")
                    except Exception as e:
                        print(f"DEBUG: 音视频合并过程出错: {e}")
                        import traceback
                        traceback.print_exc()
                        # 恢复原始视频文件
                        try:
                            if os.path.exists(temp_video_file):
                                os.rename(temp_video_file, final_video_file)
                                print("DEBUG: 已恢复原始视频文件（无音频）")
                        except Exception as rename_error:
                            print(f"DEBUG: 恢复原始视频文件失败: {rename_error}")
                
                # 清理临时目录（延迟清理，避免文件被占用）
                try:
                    import time
                    time.sleep(1)  # 等待1秒，确保所有文件操作完成
                    if os.path.exists(self.segment_dir):
                        import shutil
                        # 尝试多次删除，因为可能有文件被占用
                        max_retries = 3
                        for retry in range(max_retries):
                            try:
                                shutil.rmtree(self.segment_dir)
                                print(f"DEBUG: 清理临时片段目录: {self.segment_dir}")
                                break
                            except Exception as rm_error:
                                if retry < max_retries - 1:
                                    print(f"DEBUG: 清理临时目录失败（重试 {retry + 1}/{max_retries}）: {rm_error}")
                                    time.sleep(0.5)
                                else:
                                    print(f"DEBUG: 清理临时目录最终失败: {rm_error}")
                                    # 不抛出异常，避免影响后续处理
                except Exception as e:
                    print(f"DEBUG: 清理临时目录异常: {e}")
                    import traceback
                    traceback.print_exc()
                    # 不抛出异常，避免影响后续处理
                
                # 检查最终文件是否存在并发送完成信号
                # 无论合并是否成功，只要文件存在就发送信号
                try:
                    if os.path.exists(self.base_filepath):
                        file_size = os.path.getsize(self.base_filepath)
                        if file_size > 0:
                            print(f"DEBUG: 准备发送视频处理完成信号，文件: {self.base_filepath}, 大小: {file_size} 字节")
                            try:
                                self.video_processing_complete.emit(self.base_filepath, file_size)
                            except Exception as emit_error:
                                print(f"DEBUG: 发送视频处理完成信号失败: {emit_error}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"DEBUG: 警告：最终文件大小为0: {self.base_filepath}")
                            # 即使文件大小为0，也发送信号，让UI知道处理完成
                            try:
                                self.video_processing_complete.emit(self.base_filepath, 0)
                            except:
                                pass
                    else:
                        print(f"DEBUG: 警告：最终文件不存在: {self.base_filepath}")
                        # 文件不存在时，尝试发送一个空信号，让UI知道处理完成
                        try:
                            # 创建一个空文件作为占位符
                            with open(self.base_filepath, 'w') as f:
                                pass
                            self.video_processing_complete.emit(self.base_filepath, 0)
                        except Exception as fallback_error:
                            print(f"DEBUG: 创建占位符文件也失败: {fallback_error}")
                except Exception as signal_error:
                    print(f"DEBUG: 发送完成信号时出错: {signal_error}")
                    import traceback
                    traceback.print_exc()
            except Exception as e:
                print(f"DEBUG: 视频处理线程出错: {e}")
                import traceback
                import sys
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_exception(exc_type, exc_value, exc_traceback)
                # 即使出错，也尝试发送完成信号（如果文件存在）
                try:
                    if os.path.exists(self.base_filepath):
                        file_size = os.path.getsize(self.base_filepath)
                        if file_size > 0:
                            self.video_processing_complete.emit(self.base_filepath, file_size)
                        else:
                            # 即使文件大小为0，也发送信号
                            self.video_processing_complete.emit(self.base_filepath, 0)
                    else:
                        # 文件不存在时，尝试创建占位符并发送信号
                        try:
                            with open(self.base_filepath, 'w') as f:
                                pass
                            self.video_processing_complete.emit(self.base_filepath, 0)
                        except:
                            pass
                except Exception as final_error:
                    print(f"DEBUG: 最终错误处理也失败: {final_error}")
                    import traceback
                    traceback.print_exc()
            except BaseException as be:
                # 捕获所有异常，包括KeyboardInterrupt和SystemExit
                print(f"DEBUG: 视频处理线程发生严重错误: {be}")
                import traceback
                import sys
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_exception(exc_type, exc_value, exc_traceback)
                # 尝试发送完成信号
                try:
                    if os.path.exists(self.base_filepath):
                        file_size = os.path.getsize(self.base_filepath)
                        self.video_processing_complete.emit(self.base_filepath, file_size if file_size > 0 else 0)
                except:
                    pass
        
        # 保存线程引用，避免被垃圾回收
        if not hasattr(self, '_processing_threads'):
            self._processing_threads = []
        thread = threading.Thread(target=process_video, daemon=False)  # 不使用daemon，确保完成
        self._processing_threads.append(thread)
        thread.start()
    
    def _merge_segments(self):
        """合并所有视频片段（按照片段列表文件）- 优化版本支持进度显示"""
        try:
            # 优先使用片段列表文件，如果没有则使用video_segments
            segments_to_merge = []
            if len(self.segment_list) > 0:
                # 按照索引排序，确保顺序正确
                sorted_segments = sorted(self.segment_list, key=lambda x: x['index'])
                print(f"DEBUG: 准备合并 {len(sorted_segments)} 个片段（从列表文件）:")
                for seg_info in sorted_segments:
                    segments_to_merge.append(seg_info['video_path'])
                    print(f"DEBUG: 片段 {seg_info['index']}: {seg_info['video_path']}, 时间: {seg_info['start_time']:.2f}-{seg_info['end_time']:.2f}秒")
            else:
                # 使用旧的video_segments列表
                segments_to_merge = self.video_segments.copy()
                print(f"DEBUG: 准备合并 {len(segments_to_merge)} 个片段（旧格式）:")
            
            # 先去重，保留第一次出现的片段
            seen_segments = set()
            unique_segments = []
            for segment in segments_to_merge:
                if segment not in seen_segments:
                    seen_segments.add(segment)
                    unique_segments.append(segment)
                else:
                    print(f"DEBUG: 发现重复片段，跳过: {segment}")
            
            if len(unique_segments) != len(segments_to_merge):
                print(f"DEBUG: 去重后从 {len(segments_to_merge)} 个片段减少到 {len(unique_segments)} 个片段")
                segments_to_merge = unique_segments
            
            # 验证片段有效性
            valid_segments = []
            for i, segment in enumerate(segments_to_merge):
                if os.path.exists(segment):
                    file_size = os.path.getsize(segment)
                    if file_size > 0:
                        print(f"DEBUG: 片段 {i}: {segment}, 大小: {file_size / 1024 / 1024:.2f} MB")
                        valid_segments.append(segment)
                    else:
                        print(f"DEBUG: 警告：片段 {i} 大小为0，跳过: {segment}")
                else:
                    print(f"DEBUG: 警告：片段 {i} 不存在，跳过: {segment}")
            
            if len(valid_segments) == 0:
                print("DEBUG: 错误：没有有效的视频片段可以合并")
                return
            
            if len(valid_segments) != len(segments_to_merge):
                print(f"DEBUG: 警告：只有 {len(valid_segments)}/{len(segments_to_merge)} 个片段有效")
                segments_to_merge = valid_segments
            
            # 更新video_segments以保持兼容性
            self.video_segments = valid_segments
            
            # 发送开始合并的进度信号
            total_segments = len(segments_to_merge)
            try:
                self.merge_progress.emit(f"正在合并 {total_segments} 个录制片段...", 0, 100)
            except:
                pass
            
            # 创建concat文件列表（按照序列号顺序）
            concat_file = os.path.join(self.segment_dir, 'concat_list.txt')
            with open(concat_file, 'w', encoding='utf-8') as f:
                for segment in segments_to_merge:
                    if os.path.exists(segment) and os.path.getsize(segment) > 0:
                        # 转义文件路径中的特殊字符
                        segment_path = segment.replace('\\', '/')
                        f.write(f"file '{segment_path}'\n")
            
            # 读取并打印concat文件内容，用于调试
            with open(concat_file, 'r', encoding='utf-8') as f:
                concat_content = f.read()
                print(f"DEBUG: concat文件内容:\n{concat_content}")
            
            # 使用FFmpeg concat demuxer合并片段 - 优化参数（进一步提升速度）
            merge_cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',  # 直接复制流，不重新编码（最快）
                '-fflags', '+genpts',  # 生成presentation timestamps，提高兼容性
                '-movflags', '+faststart',  # 优化MP4，将元数据移到文件开头，加快播放
                '-threads', '0',  # 使用所有可用CPU线程
                '-loglevel', 'error',  # 减少日志输出，提升性能
                '-y',
                self.base_filepath
            ]
            
            print(f"DEBUG: 合并片段命令: {' '.join(merge_cmd)}")
            
            # 使用Popen以便实时读取进度
            try:
                merge_process = subprocess.Popen(
                    merge_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                
                # 读取stderr以获取进度信息
                stderr_lines = []
                last_progress = 0
                
                def read_stderr():
                    nonlocal last_progress
                    for line in iter(merge_process.stderr.readline, ''):
                        if line:
                            stderr_lines.append(line)
                            # 尝试解析FFmpeg的进度信息
                            # FFmpeg输出格式: frame=  123 fps= 30 q=-1.0 size=    1024kB time=00:00:04.10 ...
                            if 'time=' in line:
                                try:
                                    # 简单的进度估算：每处理一定数据，增加进度
                                    progress = min(last_progress + 5, 90)  # 最多到90%，留10%给最后处理
                                    if progress > last_progress:
                                        last_progress = progress
                                        try:
                                            self.merge_progress.emit(f"正在合并片段... ({progress}%)", progress, 100)
                                        except:
                                            pass
                                except:
                                    pass
                
                # 启动stderr读取线程
                import threading
                stderr_thread = threading.Thread(target=read_stderr, daemon=True)
                stderr_thread.start()
                
                # 等待进程完成（增加超时时间）
                try:
                    merge_process.wait(timeout=900)  # 15分钟超时，适应大文件
                except subprocess.TimeoutExpired:
                    print(f"DEBUG: 合并片段超时")
                    merge_process.kill()
                    merge_process.wait()
                    raise Exception("合并超时")
                
                # 等待stderr读取完成
                stderr_thread.join(timeout=2)
                
                # 检查返回码
                if merge_process.returncode == 0:
                    if os.path.exists(self.base_filepath):
                        final_size = os.path.getsize(self.base_filepath)
                        print(f"DEBUG: 成功合并 {len(segments_to_merge)} 个片段到: {self.base_filepath}, 最终大小: {final_size / 1024 / 1024:.2f} MB")
                        try:
                            self.merge_progress.emit("片段合并完成", 100, 100)
                        except:
                            pass
                    else:
                        print(f"DEBUG: 警告：合并成功但文件不存在: {self.base_filepath}")
                else:
                    error_output = ''.join(stderr_lines[-50:]) if stderr_lines else '无错误信息'
                    print(f"DEBUG: 合并片段失败，返回码: {merge_process.returncode}")
                    print(f"DEBUG: 错误输出: {error_output}")
                    # 如果合并失败，尝试使用concat filter方法
                    print("DEBUG: 尝试使用concat filter方法...")
                    try:
                        self.merge_progress.emit("正在尝试备用合并方法...", 50, 100)
                    except:
                        pass
                    self._merge_segments_with_filter()
                    
            except subprocess.TimeoutExpired as timeout_error:
                print(f"DEBUG: 合并片段超时: {timeout_error}")
                import traceback
                traceback.print_exc()
                # 超时时，尝试使用第一个有效片段作为最终文件
                if len(self.video_segments) > 0:
                    try:
                        import shutil
                        first_segment = self.video_segments[0]
                        if os.path.exists(first_segment) and os.path.getsize(first_segment) > 0:
                            shutil.copy2(first_segment, self.base_filepath)
                            print(f"DEBUG: 合并超时，已使用第一个片段作为最终文件: {first_segment}")
                    except Exception as fallback_error:
                        print(f"DEBUG: 使用第一个片段作为最终文件也失败: {fallback_error}")
                raise  # 重新抛出异常，让外层处理
            except Exception as subprocess_error:
                print(f"DEBUG: subprocess调用失败: {subprocess_error}")
                import traceback
                traceback.print_exc()
                # subprocess调用失败时，尝试使用第一个有效片段作为最终文件
                if len(self.video_segments) > 0:
                    try:
                        import shutil
                        first_segment = self.video_segments[0]
                        if os.path.exists(first_segment) and os.path.getsize(first_segment) > 0:
                            shutil.copy2(first_segment, self.base_filepath)
                            print(f"DEBUG: subprocess调用失败，已使用第一个片段作为最终文件: {first_segment}")
                    except Exception as fallback_error:
                        print(f"DEBUG: 使用第一个片段作为最终文件也失败: {fallback_error}")
                raise  # 重新抛出异常，让外层处理
                
        except Exception as e:
            print(f"DEBUG: 合并片段时出错: {e}")
            import traceback
            traceback.print_exc()
            # 即使出错，也尝试使用第一个有效片段作为最终文件
            try:
                if len(self.video_segments) > 0:
                    import shutil
                    first_segment = self.video_segments[0]
                    if os.path.exists(first_segment) and os.path.getsize(first_segment) > 0:
                        shutil.copy2(first_segment, self.base_filepath)
                        print(f"DEBUG: 合并异常，已使用第一个片段作为最终文件: {first_segment}")
            except Exception as fallback_error:
                print(f"DEBUG: 回退也失败: {fallback_error}")
                import traceback
                traceback.print_exc()
    
    def _merge_segments_with_filter(self):
        """使用concat filter合并片段（备用方法）"""
        try:
            # 使用与_merge_segments相同的片段列表
            segments_to_merge = self.video_segments if len(self.video_segments) > 0 else []
            if len(self.segment_list) > 0:
                sorted_segments = sorted(self.segment_list, key=lambda x: x['index'])
                segments_to_merge = [seg_info['video_path'] for seg_info in sorted_segments if os.path.exists(seg_info['video_path'])]
            
            if len(segments_to_merge) == 0:
                print("DEBUG: 错误：没有有效的视频片段可以合并（filter方法）")
                return
            
            # 构建输入参数
            inputs = []
            for segment in segments_to_merge:
                if os.path.exists(segment):
                    inputs.extend(['-i', segment])
            
            # 构建filter_complex参数
            filter_parts = []
            for i in range(len(segments_to_merge)):
                filter_parts.append(f"[{i}:v][{i}:a]")
            filter_complex = ''.join(filter_parts) + f"concat=n={len(segments_to_merge)}:v=1:a=1[outv][outa]"
            
            merge_cmd = [
                'ffmpeg'
            ] + inputs + [
                '-filter_complex', filter_complex,
                '-map', '[outv]',
                '-map', '[outa]',
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-y',
                self.base_filepath
            ]
            
            print(f"DEBUG: 使用filter方法合并片段")
            # 增加超时时间，长视频合并可能需要更长时间
            merge_process = subprocess.run(
                merge_cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 增加到10分钟，适应长视频
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            if merge_process.returncode == 0:
                print(f"DEBUG: 成功使用filter方法合并片段")
            else:
                error_output = merge_process.stderr[-1000:] if merge_process.stderr else '无错误信息'
                print(f"DEBUG: filter方法合并也失败: {error_output}")
                # 即使合并失败，也尝试使用第一个有效片段作为最终文件
                if len(segments_to_merge) > 0:
                    try:
                        import shutil
                        first_segment = segments_to_merge[0]
                        if os.path.exists(first_segment) and os.path.getsize(first_segment) > 0:
                            shutil.copy2(first_segment, self.base_filepath)
                            print(f"DEBUG: filter方法合并失败，已使用第一个片段作为最终文件: {first_segment}")
                    except Exception as fallback_error:
                        print(f"DEBUG: 使用第一个片段作为最终文件也失败: {fallback_error}")
                        import traceback
                        traceback.print_exc()
        except Exception as e:
            print(f"DEBUG: filter方法合并出错: {e}")
            import traceback
            traceback.print_exc()
            # 即使出错，也尝试使用第一个有效片段作为最终文件
            try:
                # 尝试获取片段列表
                segments_to_merge = self.video_segments if len(self.video_segments) > 0 else []
                if len(self.segment_list) > 0:
                    sorted_segments = sorted(self.segment_list, key=lambda x: x['index'])
                    segments_to_merge = [seg_info['video_path'] for seg_info in sorted_segments if os.path.exists(seg_info['video_path'])]
                
                if len(segments_to_merge) > 0:
                    import shutil
                    first_segment = segments_to_merge[0]
                    if os.path.exists(first_segment) and os.path.getsize(first_segment) > 0:
                        shutil.copy2(first_segment, self.base_filepath)
                        print(f"DEBUG: filter方法合并异常，已使用第一个片段作为最终文件: {first_segment}")
            except Exception as final_fallback_error:
                print(f"DEBUG: 最终回退也失败: {final_fallback_error}")
                import traceback
                traceback.print_exc()

    def pause(self):
        """暂停录制（FFmpeg 不支持真正的暂停，这里只是标记状态）"""
        self.paused = True
    
    def _get_audio_quality_params(self):
        """根据音频质量设置返回相应的编码参数"""
        # 音频质量参数映射
        audio_quality_map = {
            '无损音质': {
                'codec': 'flac',
                'bitrate': None,  # FLAC不需要指定比特率
                'channels': 2,
                'sample_rate': 48000
            },
            '高音质': {
                'codec': 'aac',
                'bitrate': '320k',
                'channels': 2,
                'sample_rate': 48000
            },
            '中等音质': {
                'codec': 'aac',
                'bitrate': '192k',
                'channels': 2,
                'sample_rate': 44100
            },
            '低音质': {
                'codec': 'aac',
                'bitrate': '128k',
                'channels': 1,  # 单声道
                'sample_rate': 44100
            }
        }
        
        # 获取当前音频质量设置，默认使用高音质
        params = audio_quality_map.get(self.audio_quality, audio_quality_map['高音质'])
        
        # 构建参数列表
        result = ['-c:a', params['codec']]
        
        # 添加比特率参数（如果有）
        if params['bitrate']:
            result.extend(['-b:a', params['bitrate']])
        
        # 添加声道和采样率参数
        result.extend(['-ac', str(params['channels'])])
        result.extend(['-ar', str(params['sample_rate'])])
        
        return result
    
    def resume(self):
        """恢复录制"""
        self.paused = False
    
    def update_region(self, new_region):
        """更新录制区域（使用分段录制方案：保存当前片段，使用新区域继续录制）"""
        with self.region_lock:
            old_region = self.region.copy()
            self.region = new_region.copy()
            print(f"DEBUG: 更新录制区域从 {old_region} 到 {new_region}")
            
            # 如果FFmpeg正在运行，需要保存当前片段并重新启动
            if self.running and self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                print("DEBUG: 区域改变，保存当前片段并使用新区域继续录制")
                
                # 停止当前FFmpeg进程并保存片段（使用强制关闭方法）
                old_filepath = self.filepath
                old_process = self.ffmpeg_process
                self.ffmpeg_process = None  # 先清空引用，避免重复关闭
                
                # 使用强制关闭方法确保进程被完全关闭
                self._force_close_ffmpeg_process(old_process, timeout=5)
                
                # 等待文件写入完成
                time.sleep(0.3)
                
                # 如果文件存在，添加到片段列表
                if os.path.exists(old_filepath):
                    # 如果这是第一次区域改变（使用原始文件路径），需要先复制到片段目录
                    if old_filepath == self.base_filepath:
                        # 这是第一次区域改变，将原始文件复制为第一个片段
                        first_segment = os.path.join(self.segment_dir, f'segment_{self.segment_index:04d}.mp4')
                        import shutil
                        shutil.copy2(old_filepath, first_segment)
                        self.video_segments.append(first_segment)
                        self.segment_index += 1
                        print(f"DEBUG: 第一次区域改变，保存原始文件为第一个片段: {first_segment}")
                    else:
                        # 已经是片段文件，直接添加
                        self.video_segments.append(old_filepath)
                        print(f"DEBUG: 保存片段: {old_filepath}")
                
                # 创建新的片段文件路径
                current_segment = os.path.join(self.segment_dir, f'segment_{self.segment_index:04d}.mp4')
                self.segment_index += 1
                self.filepath = current_segment
                
                # 重新启动FFmpeg（在后台线程中）
                threading.Thread(target=self._restart_recording, daemon=True).start()
    
    def _restart_ffmpeg_only(self):
        """只重新启动FFmpeg进程（不包含while循环），用于暂停恢复"""
        try:
            # 等待一小段时间确保前一个进程完全停止
            time.sleep(0.5)
            
            # 使用锁读取最新的区域参数
            with self.region_lock:
                current_region = self.region.copy()
                current_filepath = self.filepath
            
            if not self.running:
                print("DEBUG: 录制已停止，不再重新启动FFmpeg")
                return
            
            if self.ffmpeg_process is not None:
                print("DEBUG: FFmpeg进程已存在，跳过重新启动")
                return
            
            print(f"DEBUG: 重新启动FFmpeg进程，使用区域: {current_region}, 文件路径: {current_filepath}")
            
            # 注意：由于FFmpeg命令构建逻辑很复杂，我们暂时不在这里重新构建命令
            # 而是设置一个标志，让主线程知道需要重新启动FFmpeg进程
            # 但实际上，由于主线程的while循环还在运行，我们可以直接在这里启动FFmpeg进程
            # 但为了避免代码重复，我们暂时不实现，而是让主线程处理
            # 实际上，更好的方法是：修改恢复录制的逻辑，使其直接在主线程中重新启动FFmpeg进程
            
            # 临时解决方案：由于无法在这里重新构建FFmpeg命令，我们暂时不启动进程
            # 而是让主线程的while循环检测到pause_handled=False后，继续循环
            # 但这样会导致FFmpeg进程不会被启动
            # 所以我们需要修改逻辑，让主线程能够重新启动FFmpeg进程
            
            # 实际上，由于我们已经有了filepath，我们可以直接重新启动FFmpeg进程
            # 但需要重新构建命令，这很复杂
            # 所以暂时不实现，而是让主线程处理
            print("DEBUG: 注意：_restart_ffmpeg_only暂未实现完整的FFmpeg启动逻辑")
        except Exception as e:
            print(f"DEBUG: _restart_ffmpeg_only出错: {e}")
            import traceback
            traceback.print_exc()
    
    def set_audio_enabled(self, enabled):
        """动态控制系统音频录制（录制过程中）"""
        print(f"DEBUG: RecordingThread - 设置音频状态: {enabled}")
        with self.audio_recorder_lock:
            if self.system_audio_recorder and self.system_audio_recorder.is_recording:
                if enabled:
                    self.system_audio_recorder.unmute_audio()
                    print("DEBUG: 已启用系统音频录制")
                else:
                    self.system_audio_recorder.mute_audio()
                    print("DEBUG: 已禁用系统音频录制")
                return True
            elif enabled and self.system_audio_recorder and not self.system_audio_recorder.is_recording:
                # 录制过程中首次启用音频，需要启动系统音频录制器
                print("DEBUG: 录制过程中首次启用音频，动态启动系统音频录制器")
                import tempfile
                import time
                if not self.system_audio_file:
                    self.system_audio_file = os.path.join(tempfile.gettempdir(), "system_audio_recording.wav")
                print(f"DEBUG: 系统音频文件路径: {self.system_audio_file}")
                
                # 计算从录制开始到现在的时间差（排除暂停时间）
                elapsed_time = 0.0
                if self.recording_start_time:
                    current_time = time.time()
                    elapsed_time = current_time - self.recording_start_time
                    # 排除暂停时间
                    if self.system_audio_recorder and hasattr(self.system_audio_recorder, 'total_pause_duration'):
                        elapsed_time -= self.system_audio_recorder.total_pause_duration
                    print(f"DEBUG: 录制已进行 {elapsed_time:.2f} 秒，需要预填充静音数据")
                
                # 启动音频录制器
                if self.system_audio_recorder.start_recording():
                    print("DEBUG: 系统音频录制器已成功启动")
                    
                    # 如果已经录制了一段时间，需要预填充静音数据以对齐时间轴
                    if elapsed_time > 0:
                        # 计算需要填充多少个chunk的静音数据
                        chunk_duration = self.system_audio_recorder.chunk / self.system_audio_recorder.sample_rate
                        silence_chunks_needed = int(elapsed_time / chunk_duration)
                        
                        if silence_chunks_needed > 0:
                            print(f"DEBUG: 预填充 {silence_chunks_needed} 个静音chunk，对齐 {elapsed_time:.2f} 秒的时间差")
                            # 生成静音数据
                            silence_chunk = self.system_audio_recorder._generate_silence_chunk()
                            # 填充到录制数据列表
                            for _ in range(silence_chunks_needed):
                                self.system_audio_recorder.recording_data.append(silence_chunk)
                            print(f"DEBUG: 静音数据填充完成，当前总chunk数: {len(self.system_audio_recorder.recording_data)}")
                    
                    return True
                else:
                    print("DEBUG: 系统音频录制器启动失败")
                    return False
            else:
                print("DEBUG: 系统音频录制器不可用或未开始录制")
                return False
    
    def set_microphone_enabled(self, enabled):
        """动态控制麦克风录制（录制过程中）"""
        print(f"DEBUG: RecordingThread - 设置麦克风状态: {enabled}")
        with self.audio_recorder_lock:
            # 更新microphone_enabled标志（不仅仅是microphone_muted）
            if enabled:
                self.microphone_enabled = True
                self.microphone_muted = False
                print("DEBUG: 已启用麦克风录制")
                
                # 如果麦克风音频录制器不存在，但microphone_device存在，尝试创建录制器
                if not self.microphone_audio_recorder and self.microphone_device:
                    try:
                        # MicrophoneAudioRecorder 类在同一个文件中定义，可以直接使用
                        self.microphone_audio_recorder = MicrophoneAudioRecorder(device_name=self.microphone_device)
                        print(f"DEBUG: 动态创建麦克风音频录制器，设备: {self.microphone_device}")
                    except Exception as e:
                        print(f"DEBUG: 动态创建麦克风音频录制器失败: {e}")
                        import traceback
                        traceback.print_exc()
                        return False
                
                # 如果麦克风音频录制器存在且正在录制，取消静音
                if self.microphone_audio_recorder and self.microphone_audio_recorder.is_recording:
                    self.microphone_audio_recorder.unmute_audio()
                    print("DEBUG: 麦克风音频录制器已取消静音")
                    return True
                elif enabled and self.microphone_audio_recorder and not self.microphone_audio_recorder.is_recording:
                    # 录制过程中首次启用麦克风，需要启动麦克风音频录制器
                    print("DEBUG: 录制过程中首次启用麦克风，动态启动麦克风音频录制器")
                    import tempfile
                    import time
                    if not self.microphone_audio_file:
                        self.microphone_audio_file = os.path.join(tempfile.gettempdir(), "microphone_audio_recording.wav")
                    print(f"DEBUG: 麦克风音频文件路径: {self.microphone_audio_file}")
                    
                    # 计算从录制开始到现在的时间差（排除暂停时间）
                    elapsed_time = 0.0
                    if self.recording_start_time:
                        current_time = time.time()
                        elapsed_time = current_time - self.recording_start_time
                        # 排除暂停时间（如果有系统音频录制器，使用它的暂停时间；否则假设没有暂停）
                        if self.system_audio_recorder and hasattr(self.system_audio_recorder, 'total_pause_duration'):
                            elapsed_time -= self.system_audio_recorder.total_pause_duration
                        elif self.microphone_audio_recorder and hasattr(self.microphone_audio_recorder, 'total_pause_duration'):
                            elapsed_time -= self.microphone_audio_recorder.total_pause_duration
                        print(f"DEBUG: 录制已进行 {elapsed_time:.2f} 秒，需要预填充静音数据")
                    
                    # 启动麦克风音频录制器
                    if self.microphone_audio_recorder.start_recording():
                        print("DEBUG: 麦克风音频录制器已成功启动")
                        
                        # 如果已经录制了一段时间，需要预填充静音数据以对齐时间轴
                        if elapsed_time > 0:
                            # 计算需要填充多少个chunk的静音数据
                            chunk_duration = self.microphone_audio_recorder.chunk / self.microphone_audio_recorder.sample_rate
                            silence_chunks_needed = int(elapsed_time / chunk_duration)
                            
                            if silence_chunks_needed > 0:
                                print(f"DEBUG: 预填充 {silence_chunks_needed} 个静音chunk，对齐 {elapsed_time:.2f} 秒的时间差")
                                # 生成静音数据
                                silence_chunk = self.microphone_audio_recorder._generate_silence_chunk()
                                # 填充到录制数据列表
                                for _ in range(silence_chunks_needed):
                                    self.microphone_audio_recorder.recording_data.append(silence_chunk)
                                print(f"DEBUG: 静音数据填充完成，当前总chunk数: {len(self.microphone_audio_recorder.recording_data)}")
                        
                        return True
                    else:
                        print("DEBUG: 麦克风音频录制器启动失败")
                        return False
                elif not self.microphone_device:
                    print("DEBUG: 未选择麦克风设备，无法启动录制")
                    return False
                else:
                    print("DEBUG: 麦克风音频录制器不可用")
                    return False
            else:
                self.microphone_muted = True
                print("DEBUG: 已禁用麦克风录制")
                # 如果麦克风音频录制器存在且正在录制，静音
                if self.microphone_audio_recorder and self.microphone_audio_recorder.is_recording:
                    self.microphone_audio_recorder.mute_audio()
                    print("DEBUG: 麦克风音频录制器已静音")
                
                return True
    
    def _trigger_segment_switch(self):
        """触发片段切换（用于麦克风状态改变）"""
        try:
            if not self.running or not self.ffmpeg_process:
                return
            
            print("DEBUG: 开始片段切换...")
            
            # 记录当前片段的结束时间
            current_time = time.time()
            if self.recording_start_time:
                segment_end_time = current_time - self.recording_start_time - (self.system_audio_recorder.total_pause_duration if self.system_audio_recorder else 0)
            else:
                segment_end_time = self.last_segment_end_time + 1.0
            
            # 停止当前FFmpeg进程
            old_process = self.ffmpeg_process
            old_filepath = self.filepath
            
            # 强制关闭FFmpeg进程
            self._force_close_ffmpeg_process(old_process, timeout=3)
            
            # 等待文件写入完成
            time.sleep(0.3)
            
            # 保存当前片段到列表
            if os.path.exists(old_filepath):
                if old_filepath == self.base_filepath:
                    # 第一个片段，复制到片段目录
                    new_segment_path = os.path.join(self.segment_dir, f'segment_0.mp4')
                    import shutil
                    shutil.copy2(old_filepath, new_segment_path)
                    self._add_segment_to_list(new_segment_path, start_time=0.0, end_time=segment_end_time)
                    self.segment_index = 1
                else:
                    # 后续片段，直接添加
                    self._add_segment_to_list(old_filepath, end_time=segment_end_time)
            
            # 生成新的片段文件名
            self.filepath = os.path.join(self.segment_dir, f'segment_{self.segment_index}.mp4')
            self.segment_index += 1
            
            # 重新启动FFmpeg进程（使用新的麦克风状态）
            self.try_ffmpeg_recording()
            
            print(f"DEBUG: 片段切换完成，新片段: {self.filepath}")
            
        except Exception as e:
            print(f"DEBUG: 片段切换失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _start_ffmpeg_process_only(self):
        """只启动FFmpeg进程，不启动while循环（用于恢复录制）
        注意：这个方法复用 try_ffmpeg_recording 的命令构建逻辑，但只启动进程
        """
        try:
            # 使用锁读取最新的区域参数
            with self.region_lock:
                recording_region = self.region.copy()
                current_filepath = self.filepath
            
            # 确保宽度和高度是偶数（H.264编码器要求）
            original_width = recording_region['width']
            original_height = recording_region['height']
            adjusted_width = original_width if original_width % 2 == 0 else original_width - 1
            adjusted_height = original_height if original_height % 2 == 0 else original_height - 1
            
            if adjusted_width != original_width or adjusted_height != original_height:
                recording_region['width'] = adjusted_width
                recording_region['height'] = adjusted_height
                with self.region_lock:
                    self.region['width'] = adjusted_width
                    self.region['height'] = adjusted_height
            
            # 构建 FFmpeg 命令（复用 try_ffmpeg_recording 的逻辑，但简化音频处理）
            # 因为恢复录制时，系统音频通常已经通过 pyaudiowpatch 在录制
            cmd = ['ffmpeg']
            
            # 视频输入（屏幕捕获）
            if sys.platform == 'win32':
                gdigrab_options = [
                    '-f', 'gdigrab',
                    '-framerate', str(self.fps),
                    '-offset_x', str(recording_region['left']),
                    '-offset_y', str(recording_region['top']),
                    '-video_size', f"{recording_region['width']}x{recording_region['height']}",
                ]
                if not self.show_cursor:
                    gdigrab_options.extend(['-draw_mouse', '0'])
                gdigrab_options.append('-i')
                gdigrab_options.append('desktop')
                cmd.extend(gdigrab_options)
            
            # 摄像头输入（如果启用）
            camera_input_index = None
            if self.camera_enabled and self.camera_device:
                if sys.platform == 'win32':
                    camera_input_index = len(cmd)
                    camera_input = f'video="{self.camera_device}"'
                    cmd.extend([
                        '-f', 'dshow',
                        '-video_size', '640x480',
                        '-framerate', '30',
                        '-i', camera_input
                    ])
            
            # 音频输入（简化：恢复录制时通常系统音频已通过pyaudiowpatch录制，所以这里不添加音频输入）
            # 但如果需要，可以添加简单的音频输入
            has_audio = False
            audio_inputs = []
            if self.audio_enabled and (not self.system_audio_recorder or not self.system_audio_file):
                # 只有在没有使用pyaudiowpatch时才添加FFmpeg音频输入
                if sys.platform == 'win32':
                    # 简化：尝试添加WASAPI loopback
                    try:
                        cmd.extend(['-f', 'wasapi', '-i', 'audio="default"'])
                        has_audio = True
                    except:
                        pass
            
            # 构建编码参数
            quality_crf_map = {
                '原画质': '18',
                '高质量': '23',
                '中等质量': '28',
                '低质量': '32'
            }
            crf_value = quality_crf_map.get(self.quality, '23')
            
            use_bitrate = False
            use_cq = False
            if self.video_encoder == 'libopenh264':
                bitrate_value = '5000k'
                use_bitrate = True
            elif 'nvenc' in self.video_encoder:
                cq_value = crf_value
                use_cq = True
            elif 'qsv' in self.video_encoder or 'amf' in self.video_encoder:
                bitrate_value = '4000k'
                use_bitrate = True
            
            # 视频编码参数
            video_encoder_params = ['-c:v', self.video_encoder]
            if use_cq and 'nvenc' in self.video_encoder:
                video_encoder_params.extend(['-pix_fmt', 'nv12', '-preset', 'p4', '-cq', cq_value])
            else:
                video_encoder_params.extend(['-pix_fmt', 'yuv420p'])
                if use_bitrate:
                    video_encoder_params.extend(['-b:v', bitrate_value])
                else:
                    video_encoder_params.extend(['-preset', 'medium', '-crf', crf_value])
                    if self.video_encoder == 'libx264':
                        video_encoder_params.extend(['-profile:v', 'high', '-level', '4.0'])
            
            cmd.extend(video_encoder_params)
            
            # 音频编码参数（如果有音频）
            if has_audio:
                audio_params = self._get_audio_quality_params()
                cmd.extend(audio_params)
                cmd.extend(['-f', 'mp4', '-shortest', '-y', current_filepath])
            else:
                cmd.extend(['-f', 'mp4', '-y', current_filepath])
            
            print(f"DEBUG: 恢复录制 - 启动FFmpeg进程，命令: {' '.join(cmd[:15])}...")
            
            # 启动 FFmpeg 进程
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                bufsize=0,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            # 添加到进程列表
            with self.ffmpeg_process_lock:
                if self.ffmpeg_process not in self.ffmpeg_processes:
                    self.ffmpeg_processes.append(self.ffmpeg_process)
                    print(f"DEBUG: 已添加FFmpeg进程到跟踪列表 (PID: {self.ffmpeg_process.pid})")
            
            # 在后台线程中读取 stderr（避免缓冲区满）
            stderr_lines = []
            def read_stderr():
                try:
                    for line in iter(self.ffmpeg_process.stderr.readline, b''):
                        if line:
                            stderr_lines.append(line.decode('utf-8', errors='ignore'))
                except:
                    pass
            
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()
            
            # 等待一小段时间，检查FFmpeg是否正常启动
            time.sleep(0.5)
            if self.ffmpeg_process and self.ffmpeg_process.poll() is not None:
                print("DEBUG: 错误：FFmpeg进程启动失败")
                # 读取错误信息
                time.sleep(0.2)
                stderr_thread.join(timeout=0.5)
                if stderr_lines:
                    error_output = '\n'.join(stderr_lines)
                    print(f"DEBUG: FFmpeg错误输出: {error_output[-500:]}")
                return False
            
            print(f"DEBUG: FFmpeg进程已成功启动 (PID: {self.ffmpeg_process.pid})")
            return True
            
        except Exception as e:
            print(f"DEBUG: 启动FFmpeg进程时出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _restart_recording(self):
        """在后台线程中重新启动录制（用于暂停恢复或区域更新）"""
        # 等待一小段时间确保前一个进程完全停止
        time.sleep(0.5)
        
        # 使用锁读取最新的区域参数
        with self.region_lock:
            current_region = self.region.copy()
            current_filepath = self.filepath
        
        # 重新启动录制（只重新启动 FFmpeg，不重新初始化系统音频录制器）
        if self.running:
            print(f"DEBUG: 重新启动录制，使用新区域: {current_region}, 文件路径: {current_filepath}")
            # 注意：这里调用try_ffmpeg_recording会启动新的while循环，但主线程的while循环还在运行
            # 这会导致多个FFmpeg进程和片段重复保存的问题
            # 但由于FFmpeg命令构建逻辑很复杂，暂时保留原来的方式
            # 增加检查避免重复启动
            if self.ffmpeg_process is None:
                # 重新启动 FFmpeg 录制
                # 注意：系统音频录制器应该继续运行，不需要重新初始化
                # 但调用try_ffmpeg_recording会启动新的while循环，这会导致问题
                # 暂时保留原来的方式，但会在主线程的while循环中检测到FFmpeg进程已启动
                try:
                    self.try_ffmpeg_recording()
                except Exception as e:
                    print(f"DEBUG: _restart_recording调用try_ffmpeg_recording时出错: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("DEBUG: FFmpeg进程已存在，跳过重新启动")
        else:
            print("DEBUG: 录制已停止，不再重新启动")


class CameraPreviewWindow(QWidget):
    """摄像头预览窗口 - 400x400大小，显示在桌面右下角"""
    def __init__(self, camera_index=0, parent=None):
        super().__init__(None)  # 独立窗口
        self.setWindowTitle('摄像头预览')
        self.setFixedSize(400, 400)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.camera_index = camera_index
        self.camera = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.camera_init_thread = None  # 摄像头初始化线程
        
        # 窗口拖动功能
        self.dragging = False
        self.drag_position = QPoint()
        
        # 初始化UI
        self.init_ui()
        
        # 将窗口移动到桌面右下角
        self.move_to_bottom_right()
        
        # 异步打开摄像头（避免阻塞UI）
        QTimer.singleShot(50, self.start_camera_async)
    
    def init_ui(self):
        """初始化UI"""
        # 创建主容器
        main_widget = QWidget()
        main_widget.setStyleSheet(
            "background-color: #1a1a21; "
            "border-radius: 8px;"
        )
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(main_widget)
        
        # 创建内容布局
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 创建标题栏（包含关闭按钮）
        title_bar = QWidget()
        title_bar.setFixedHeight(32)
        title_bar.setStyleSheet("background-color: #1a1a21; border-top-left-radius: 8px; border-top-right-radius: 8px;")
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 0, 12, 0)
        title_layout.setSpacing(8)
        
        # 标题
        title_label = QLabel('摄像头预览')
        title_label.setStyleSheet("color: #FFFFFF; font-family: 'Microsoft YaHei'; font-size: 12px; font-weight: 500;")
        
        # 关闭按钮
        close_button = QPushButton('×')
        close_button.setFixedSize(24, 24)
        close_button.setStyleSheet(
            "background-color: transparent; "
            "color: #9CA3AF; "
            "font-size: 16px; "
            "border: none;"
        )
        close_button.setToolTip('关闭')
        close_button.clicked.connect(self.close)
        
        # 关闭按钮悬停效果
        def close_enter(event):
            close_button.setStyleSheet(
                "background-color: #EF4444; "
                "color: #FFFFFF; "
                "font-size: 16px; "
                "border-radius: 4px; "
                "border: none;"
            )
            event.accept()
        
        def close_leave(event):
            close_button.setStyleSheet(
                "background-color: transparent; "
                "color: #9CA3AF; "
                "font-size: 16px; "
                "border: none;"
            )
            event.accept()
        
        close_button.enterEvent = close_enter
        close_button.leaveEvent = close_leave
        
        # 标题栏布局
        title_layout.addWidget(title_label, 1)
        title_layout.addWidget(close_button)
        
        # 窗口拖动功能（在标题栏上，但不影响关闭按钮）
        def title_bar_mouse_press(event):
            if event.button() == Qt.LeftButton:
                self.dragging = True
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
        
        def title_bar_mouse_move(event):
            if self.dragging and event.buttons() == Qt.LeftButton:
                self.move(event.globalPos() - self.drag_position)
                event.accept()
        
        def title_bar_mouse_release(event):
            self.dragging = False
        
        title_bar.mousePressEvent = title_bar_mouse_press
        title_bar.mouseMoveEvent = title_bar_mouse_move
        title_bar.mouseReleaseEvent = title_bar_mouse_release
        
        layout.addWidget(title_bar)
        
        # 创建视频显示标签
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("正在加载摄像头...")
        self.video_label.setStyleSheet(
            "background-color: #000000; "
            "border-bottom-left-radius: 8px; "
            "border-bottom-right-radius: 8px; "
            "color: #FFFFFF; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 14px;"
        )
        layout.addWidget(self.video_label)
    
    def start_camera_async(self):
        """异步启动摄像头（在后台线程中初始化）"""
        if not HAS_CV2:
            self.video_label.setText("OpenCV未安装，无法使用摄像头")
            print("DEBUG: OpenCV未安装，无法使用摄像头")
            return
        
        # 使用线程初始化摄像头，避免阻塞UI
        def init_camera():
            camera = None
            try:
                print(f"DEBUG: 开始初始化摄像头 {self.camera_index}")
                # 先尝试使用DirectShow后端（Windows推荐）
                try:
                    camera = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                    if not camera.isOpened():
                        print(f"DEBUG: DirectShow后端打开失败，尝试默认后端")
                        camera.release()
                        camera = cv2.VideoCapture(self.camera_index)
                except Exception as e:
                    print(f"DEBUG: DirectShow后端异常: {e}，使用默认后端")
                    camera = cv2.VideoCapture(self.camera_index)
                
                if camera and camera.isOpened():
                    # 设置摄像头分辨率（使用较低分辨率加快速度）
                    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    # 设置缓冲区大小为1，减少延迟
                    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # 在主线程中启动定时器
                    self.camera = camera
                    QTimer.singleShot(0, self._start_timer)
                    print(f"DEBUG: 摄像头 {self.camera_index} 初始化完成")
                else:
                    error_msg = "无法打开摄像头"
                    print(f"DEBUG: {error_msg} {self.camera_index}")
                    QTimer.singleShot(0, lambda msg=error_msg: self.video_label.setText(msg))
                    if camera:
                        camera.release()
            except Exception as e:
                error_msg = f"摄像头错误: {str(e)}"
                print(f"DEBUG: 启动摄像头失败: {e}")
                import traceback
                traceback.print_exc()
                QTimer.singleShot(0, lambda msg=error_msg: self.video_label.setText(msg))
                if camera:
                    try:
                        camera.release()
                    except:
                        pass
        
        self.camera_init_thread = threading.Thread(target=init_camera, daemon=True)
        self.camera_init_thread.start()
    
    def _start_timer(self):
        """在主线程中启动定时器"""
        print(f"DEBUG: _start_timer 被调用, camera={self.camera}")
        if self.camera:
            is_opened = self.camera.isOpened()
            print(f"DEBUG: camera.isOpened() = {is_opened}")
            if is_opened:
                # 启动定时器，每33ms更新一次（约30fps）
                self.timer.start(33)
                print(f"DEBUG: 摄像头定时器已启动")
            else:
                print(f"DEBUG: 摄像头已关闭，无法启动定时器")
        else:
            print(f"DEBUG: camera 为 None，无法启动定时器")
    
    def update_frame(self):
        """更新视频帧"""
        if self.camera is None or not HAS_CV2:
            return
        
        try:
            ret, frame = self.camera.read()
            if ret:
                # 将BGR转换为RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # 调整大小以适应窗口
                height, width = frame_rgb.shape[:2]
                # 计算缩放比例，保持宽高比
                scale = min(400 / width, 400 / height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame_resized = cv2.resize(frame_rgb, (new_width, new_height))
                
                # 转换为QImage
                h, w, ch = frame_resized.shape
                bytes_per_line = ch * w
                qt_image = QImage(frame_resized.data, w, h, bytes_per_line, QImage.Format_RGB888)
                
                # 转换为QPixmap并显示
                pixmap = QPixmap.fromImage(qt_image)
                self.video_label.setPixmap(pixmap)
            else:
                print("DEBUG: 无法读取摄像头帧")
        except Exception as e:
            print(f"DEBUG: 更新视频帧失败: {e}")
    
    def move_to_bottom_right(self):
        """将窗口移动到桌面右下角"""
        screen = QDesktopWidget().screenGeometry()
        window_geometry = self.frameGeometry()
        x = screen.width() - window_geometry.width() - 20
        y = screen.height() - window_geometry.height() - 20
        self.move(x, y)
    
    def mousePressEvent(self, event):
        """鼠标按下事件 - 用于拖动窗口"""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 用于拖动窗口"""
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        self.dragging = False
    
    def closeEvent(self, event):
        """窗口关闭事件 - 释放摄像头资源"""
        self.stop_camera()
        event.accept()
    
    def stop_camera(self):
        """停止摄像头"""
        # 停止定时器
        if self.timer:
            self.timer.stop()
        
        # 等待初始化线程完成（如果还在运行）
        if self.camera_init_thread and self.camera_init_thread.is_alive():
            try:
                self.camera_init_thread.join(timeout=1.0)
            except Exception as e:
                print(f"DEBUG: 等待摄像头初始化线程失败: {e}")
        
        # 释放摄像头
        if self.camera:
            try:
                if HAS_CV2:
                    self.camera.release()
                    print(f"DEBUG: 摄像头 {self.camera_index} 已释放")
            except Exception as e:
                print(f"DEBUG: 释放摄像头失败: {e}")
            self.camera = None


class SystemAudioRecorder:
    def __init__(self):
        self.pa = None
        self.stream = None
        self.recording_thread = None
        self.is_recording = False
        self.recording_data = []
        # 使用更高的位深度以提高音质
        self.format = pyaudio.paInt24 if hasattr(pyaudio, 'paInt24') else pyaudio.paInt16
        self.channels = 2
        # 默认使用更高的采样率
        self.sample_rate = 48000
        # 进一步增大缓冲区以彻底解决卡顿问题
        self.chunk = 8192  # 从4096增大到8192，提供更好的稳定性
        self.loopback_device = None
        
        # 新增：用于连续录制的变量
        self.last_read_time = 0  # 记录上次读取时间
        self.chunk_duration = self.chunk / self.sample_rate  # 每个chunk的时长(秒)
        self.silence_data = None  # 预生成的静音数据
        self.read_timeout = 0.1  # 读取超时时间(秒)
        self.initial_pa = None  # 保存初始的pyaudio实例
        self.paused = False  # 暂停标志
        self.pause_start_time = None  # 暂停开始时间
        self.total_pause_duration = 0.0  # 累计暂停时长
        
        # 线程安全保护
        self._operation_lock = threading.Lock()  # 保护关键操作
        self._saving = False  # 标记是否正在保存
        
        # 动态音频控制
        self.audio_muted = False  # 是否静音（录制过程中动态控制）
        
    def _generate_silence_chunk(self):
        """生成一个chunk的静音数据"""
        # 根据位深度计算静音数据大小
        bytes_per_sample = 3 if self.format == pyaudio.paInt24 else 2  # 24位为3字节，16位为2字节
        silence_size = self.chunk * self.channels * bytes_per_sample
        return b'\x00' * silence_size
    
    def start_recording(self):
        """开始录制系统声音 - 连续录制版本"""
        if not HAS_PYAUDIO_WPATCH:
            print("DEBUG: pyaudiowpatch未安装，无法录制系统音频")
            return False
            
        if self.is_recording:
            print("DEBUG: 已经在录制中")
            return False
        
        # 获取Loopback设备
        self.loopback_device = self._get_loopback_device()
        if not self.loopback_device:
            print("DEBUG: 未找到合适的Loopback设备")
            return False
        
        # 使用设备支持的实际采样率
        self.sample_rate = int(self.loopback_device['defaultSampleRate'])
        # 重新计算chunk时长
        self.chunk_duration = self.chunk / self.sample_rate
        # 预生成静音数据
        self.silence_data = self._generate_silence_chunk()
        
        print(f"DEBUG: 使用设备 {self.loopback_device['name']} 开始连续录制，采样率: {self.sample_rate}Hz")
        
        self.is_recording = True
        self.recording_data = []
        self.last_read_time = time.time()  # 初始化时间记录
        
        # 确保pyaudio实例已经初始化
        if not self.pa and HAS_PYAUDIO_WPATCH:
            self.pa = pyaudio.PyAudio()
            self.initial_pa = self.pa
        
        try:
            # 打开音频流 - 优化配置以减少延迟和提高稳定性
            self.stream = self.pa.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=int(self.loopback_device['index']),
                frames_per_buffer=self.chunk,
                stream_callback=None,
                start=False
            )
            
            # 启动流
            self.stream.start_stream()
            
        except Exception as e:
            print(f"DEBUG: 打开音频流失败: {e}")
            self.is_recording = False
            return False
        
        # 开始录制线程 - 使用更低优先级避免干扰主线程
        self.recording_thread = threading.Thread(target=self._continuous_record_thread)
        self.recording_thread.daemon = True
        try:
            import ctypes
            # 设置线程优先级为低于正常，减少对UI的影响
            thread_id = self.recording_thread.ident
            handle = ctypes.windll.kernel32.OpenThread(0x0200, False, thread_id)
            ctypes.windll.kernel32.SetThreadPriority(handle, 0x0001)  # THREAD_PRIORITY_LOWEST
        except:
            pass  # 如果设置优先级失败，继续执行
        
        self.recording_thread.start()
        
        return True
    
    def _continuous_record_thread(self):
        """连续录制线程 - 确保音频数据连续，修复卡顿问题"""
        import audioop  # 用于音频处理
        
        print("DEBUG: 开始连续音频录制线程")
        
        # 记录开始时间
        start_time = time.time()
        last_read_index = 0  # 记录最后读取的位置索引
        
        # 动态休眠时间 - 根据chunk大小调整，使用更短的休眠时间以提高响应性
        chunk_size_ms = int(self.chunk_duration * 1000 * 0.5)  # 使用chunk时长的50%作为基准休眠时间
        sleep_interval = max(0.001, chunk_size_ms / 1000.0)  # 最小1ms，提高读取频率
        
        # 减少日志输出以提高性能
        log_counter = 0
        
        # 连续读取计数器，用于检测是否有数据可读
        consecutive_empty_reads = 0
        max_empty_reads = 3  # 连续3次空读后才休眠
        
        while self.is_recording:
            try:
                current_time = time.time()
                # 如果暂停，不计算时间，暂停期间不补充静音
                if self.paused:
                    # 暂停期间，不读取数据，不补充静音，只休眠
                    time.sleep(0.1)
                    continue
                
                # 计算实际录制时长（排除暂停时间）
                elapsed = current_time - start_time - self.total_pause_duration
                
                # 计算当前应该有多少个chunk
                expected_chunks_current = int(elapsed / self.chunk_duration)
                
                # 优先读取音频数据，而不是先补充静音
                # 这样可以确保实际音频数据不会被静音覆盖
                data_read = False
                if self.stream and self.is_recording:
                    try:
                        # 检查流是否仍然活跃且未停止
                        if self.stream.is_active() and not self.stream.is_stopped():
                            # 更积极的读取策略：持续尝试读取，直到没有数据可读
                            # 使用循环读取多个chunk，避免数据积压
                            read_attempts = 0
                            max_read_attempts = 5  # 每次循环最多尝试读取5个chunk
                            
                            while read_attempts < max_read_attempts:
                                try:
                                    # 检查是否有数据可读（非阻塞检查）
                                    if self.stream.get_read_available() >= self.chunk:
                                        # 读取音频数据（非阻塞模式）
                                        data = self.stream.read(self.chunk, exception_on_overflow=False)
                                                                                
                                        # 检查是否静音，如果静音则替换为静音数据
                                        if self.audio_muted:
                                            data = self.silence_data
                                                                                
                                        # 检查数据是否有效
                                        if data and len(data) > 0:
                                            # 确保数据长度正确（防止不完整的数据）
                                            expected_size = self.chunk * self.channels * (3 if self.format == pyaudio.paInt24 else 2)
                                            if len(data) == expected_size:
                                                # 直接追加数据，不替换已有数据
                                                self.recording_data.append(data)
                                                last_read_index = len(self.recording_data) - 1
                                                data_read = True
                                                consecutive_empty_reads = 0
                                                
                                                # 更新最后读取时间
                                                self.last_read_time = current_time
                                                
                                                # 非常少地打印调试信息
                                                if len(self.recording_data) % 500 == 0:
                                                    rms = audioop.rms(data, 3) if len(data) >= 6 else 0
                                                    print(f"DEBUG: 音频电平: {rms}, 已录制: {len(self.recording_data)} chunks")
                                                
                                                read_attempts += 1
                                            else:
                                                # 数据长度不正确，跳过这个chunk
                                                if log_counter % 200 == 0:
                                                    print(f"DEBUG: 警告：音频数据长度不正确，期望: {expected_size}, 实际: {len(data)}")
                                                break
                                        else:
                                            # 没有数据可读，退出读取循环
                                            consecutive_empty_reads += 1
                                            break
                                    else:
                                        # 没有足够的数据可读，退出读取循环
                                        consecutive_empty_reads += 1
                                        break
                                        
                                except OSError as read_ex:
                                    # OSError通常表示流已关闭或没有数据
                                    error_str = str(read_ex)
                                    if "not open" in error_str.lower() or "closed" in error_str.lower():
                                        print("DEBUG: 音频流已关闭，停止读取")
                                        break
                                    consecutive_empty_reads += 1
                                    break
                                except Exception as read_ex:
                                    # 读取异常，记录但不中断
                                    error_str = str(read_ex)
                                    if "Input overflowed" in error_str:
                                        # 缓冲区溢出，说明数据积压，需要更频繁读取
                                        consecutive_empty_reads = 0
                                        if log_counter % 100 == 0:
                                            print(f"DEBUG: 音频缓冲区溢出，需要更频繁读取")
                                    elif log_counter % 100 == 0:
                                        print(f"DEBUG: 音频读取异常: {read_ex}")
                                    consecutive_empty_reads += 1
                                    break
                            
                            # 如果没有读取到数据，增加空读计数
                            if not data_read:
                                consecutive_empty_reads += 1
                    except OSError as read_error:
                        # OSError通常表示流已关闭，这是正常的，直接退出循环
                        error_str = str(read_error)
                        if "not open" in error_str.lower() or "closed" in error_str.lower():
                            print("DEBUG: 音频流已关闭，停止读取")
                            break
                        elif log_counter % 100 == 0:
                            print(f"DEBUG: 音频读取OSError: {error_str}")
                    except Exception as read_error:
                        # 其他读取错误，记录但不中断
                        error_str = str(read_error)
                        if "Input overflowed" not in error_str and log_counter % 100 == 0:
                            print(f"DEBUG: 音频读取错误: {error_str}")
                
                # 只有在没有读取到数据且数据不足时才补充静音
                # 这样可以避免用静音覆盖实际音频数据
                if not data_read:
                    needed_chunks = expected_chunks_current - len(self.recording_data)
                    if needed_chunks > 0:
                        # 只补充必要的静音，避免过度补充
                        # 限制每次最多补充10个chunk，避免一次性补充太多
                        chunks_to_add = min(needed_chunks, 10)
                        for _ in range(chunks_to_add):
                            self.recording_data.append(self.silence_data)
                        
                        # 减少日志输出频率
                        log_counter += 1
                        if log_counter % 50 == 0:
                            print(f"DEBUG: 补充静音，当前: {len(self.recording_data)}, 期望: {expected_chunks_current}")
                    
                    # 只有在没有读取到数据且流确实不活跃时才打印警告
                    # 注意：即使没有读取到数据，也可能是因为暂时没有新数据，不代表流不活跃
                    if self.stream and not self.stream.is_active():
                        if log_counter % 200 == 0:
                            print("DEBUG: 音频流不活跃")
                
                # 检查是否应该退出录制
                if not self.is_recording:
                    # 如果已停止录制，退出循环
                    break
                
                # 智能休眠 - 根据读取情况调整休眠时间
                # 如果刚刚读取到数据，使用更短的休眠时间以保持响应性
                if data_read:
                    # 读取到数据，使用短休眠以保持高频率读取
                    time.sleep(max(0.001, sleep_interval * 0.5))
                elif consecutive_empty_reads < max_empty_reads:
                    # 连续空读次数少，说明可能有数据，使用短休眠
                    time.sleep(max(0.001, sleep_interval * 0.7))
                elif len(self.recording_data) < expected_chunks_current - 5:
                    # 数据严重不足，减少休眠时间，加快处理
                    time.sleep(max(0.001, sleep_interval * 0.3))
                elif len(self.recording_data) > expected_chunks_current + 20:
                    # 数据过多，稍微增加休眠时间，避免内存占用过高
                    time.sleep(sleep_interval * 1.5)
                else:
                    # 数据正常，使用标准休眠时间
                    time.sleep(sleep_interval)
                
                # 限制内存使用 - 但保留更多数据以避免丢失
                if len(self.recording_data) > 10000:  # 提高阈值，保留更多数据
                    # 只清理最旧的数据，保留最近的数据
                    # 保留最后8000个chunk
                    self.recording_data = self.recording_data[-8000:]
                    if log_counter % 100 == 0:
                        print(f"DEBUG: 音频数据清理，当前: {len(self.recording_data)}")
                    
            except Exception as e:
                # 简化错误处理，避免复杂操作
                if log_counter % 500 == 0:
                    print(f"DEBUG: 录制线程错误: {e}")
                # 简单休眠避免CPU占用过高
                time.sleep(0.005)
        
        print(f"DEBUG: 连续录制线程结束，总共录制 {len(self.recording_data)} 个chunk")
    
    def pause_recording(self):
        """暂停录制（停止读取，但保留数据和流）"""
        if not self.is_recording:
            print("DEBUG: 没有在录制中，无法暂停")
            return False
        
        if self.paused:
            print("DEBUG: 音频录制已经暂停")
            return True
        
        print("DEBUG: 暂停音频录制")
        # 记录暂停开始时间
        self.pause_start_time = time.time()
        self.paused = True
        
        # 停止音频流，但保留流和数据
        if self.stream:
            try:
                if self.stream.is_active():
                    self.stream.stop_stream()
                    print("DEBUG: 音频流已暂停")
            except Exception as e:
                print(f"DEBUG: 暂停音频流时出错: {e}")
        
        return True
    
    def resume_recording(self):
        """恢复录制（重新启动音频流）"""
        if not self.is_recording:
            print("DEBUG: 没有在录制中，无法恢复")
            return False
        
        if not self.paused:
            print("DEBUG: 音频录制未暂停，无需恢复")
            return True
        
        print("DEBUG: 恢复音频录制")
        
        # 计算暂停时长并累加
        if self.pause_start_time:
            pause_duration = time.time() - self.pause_start_time
            self.total_pause_duration += pause_duration
            print(f"DEBUG: 暂停时长: {pause_duration:.2f}秒, 累计暂停时长: {self.total_pause_duration:.2f}秒")
            self.pause_start_time = None
        
        self.paused = False
        
        # 重新启动音频流
        if self.stream:
            try:
                # 检查流是否已关闭
                if self.stream.is_stopped():
                    # 尝试重新启动流
                    try:
                        self.stream.start_stream()
                        print("DEBUG: 音频流已恢复")
                    except Exception as e:
                        # 如果启动失败，可能是流已关闭，需要重新创建
                        print(f"DEBUG: 重新启动音频流失败: {e}，尝试重新创建流...")
                        try:
                            # 关闭旧流
                            if not self.stream.is_stopped():
                                self.stream.stop_stream()
                            self.stream.close()
                        except:
                            pass
                        
                        # 重新创建流
                        try:
                            self.stream = self.pa.open(
                                format=self.format,
                                channels=self.channels,
                                rate=self.sample_rate,
                                input=True,
                                input_device_index=int(self.loopback_device['index']),
                                frames_per_buffer=self.chunk,
                                stream_callback=None,
                                start=False
                            )
                            self.stream.start_stream()
                            print("DEBUG: 音频流已重新创建并启动")
                        except Exception as e2:
                            print(f"DEBUG: 重新创建音频流失败: {e2}")
                            return False
                elif not self.stream.is_active():
                    # 流未停止但未激活，尝试启动
                    try:
                        self.stream.start_stream()
                        print("DEBUG: 音频流已恢复")
                    except Exception as e:
                        print(f"DEBUG: 恢复音频流时出错: {e}")
                        return False
                else:
                    print("DEBUG: 音频流已在运行")
            except Exception as e:
                print(f"DEBUG: 恢复音频流时出错: {e}")
                return False
        else:
            print("DEBUG: 警告：音频流不存在，无法恢复")
            return False
        
        return True
    
    def mute_audio(self):
        """静音（录制过程中禁用音频）"""
        print("DEBUG: MicrophoneAudioRecorder - 静音音频")
        self.audio_muted = True
        
        # 立即清空音频流缓冲区，减少延迟
        if self.stream and self.stream.is_active():
            try:
                # 读取并丢弃当前缓冲区中的所有数据
                available = self.stream.get_read_available()
                if available > 0:
                    self.stream.read(available, exception_on_overflow=False)
                    print(f"DEBUG: 已清空麦克风缓冲区 {available} 帧，减少静音延迟")
            except Exception as e:
                print(f"DEBUG: 清空麦克风缓冲区失败: {e}")
        
        return True
    
    def unmute_audio(self):
        """取消静音（录制过程中启用音频）"""
        print("DEBUG: MicrophoneAudioRecorder - 取消静音")
        self.audio_muted = False
        
        # 立即清空音频流缓冲区，避免播放旧数据
        if self.stream and self.stream.is_active():
            try:
                # 读取并丢弃当前缓冲区中的所有数据
                available = self.stream.get_read_available()
                if available > 0:
                    self.stream.read(available, exception_on_overflow=False)
                    print(f"DEBUG: 已清空麦克风缓冲区 {available} 帧，避免播放旧数据")
            except Exception as e:
                print(f"DEBUG: 清空麦克风缓冲区失败: {e}")
        
        return True
    
    def stop_recording(self):
        """停止录制（线程安全）"""
        with self._operation_lock:
            if not self.is_recording:
                print("DEBUG: 没有在录制中")
                return False
            
            print("DEBUG: 停止连续音频录制")
            self.is_recording = False
            
            # 先停止音频流，避免继续读取数据
            if self.stream:
                try:
                    if self.stream.is_active():
                        self.stream.stop_stream()
                except Exception as e:
                    print(f"DEBUG: 停止音频流时出错: {e}")
            
            # 等待录制线程结束，增加等待时间并检查线程状态
            if self.recording_thread and self.recording_thread.is_alive():
                print("DEBUG: 等待录制线程结束...")
                self.recording_thread.join(timeout=5.0)  # 增加到5秒
                if self.recording_thread.is_alive():
                    print("DEBUG: 警告：录制线程未在超时时间内结束")
                else:
                    print("DEBUG: 录制线程已结束")
            
            # 关闭流（在线程结束后）
            if self.stream:
                try:
                    if not self.stream.is_stopped():
                        self.stream.stop_stream()
                    self.stream.close()
                    self.stream = None
                except Exception as e:
                    print(f"DEBUG: 关闭音频流时出错: {e}")
                    self.stream = None
            
            # 计算总时长
            total_duration = len(self.recording_data) * self.chunk_duration
            print(f"DEBUG: 音频录制完成，总时长: {total_duration:.2f}秒, 总数据量: {len(self.recording_data)} chunks")
            
            return True
    
    def save_recording(self, filename="system_audio.wav"):
        """保存录制的音频到WAV文件（线程安全）"""
        with self._operation_lock:
            # 检查是否正在保存，避免重复保存
            if self._saving:
                print("DEBUG: 音频正在保存中，跳过重复操作")
                return False
            
            if not self.recording_data:
                print("DEBUG: 没有录制数据可以保存")
                return False
            
            if not HAS_PYAUDIO_WPATCH:
                print("DEBUG: pyaudiowpatch未安装，无法保存音频")
                return False
            
            self._saving = True
            try:
                print(f"DEBUG: 正在保存音频到 {filename}...")
                print(f"DEBUG: 音频数据信息: {len(self.recording_data)} chunks, 采样率: {self.sample_rate}Hz")
                
                # 创建数据副本，避免在保存过程中数据被修改
                recording_data_copy = list(self.recording_data)
                
                import wave
                wf = wave.open(filename, 'wb')
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.pa.get_sample_size(self.format))
                wf.setframerate(self.sample_rate)
                
                # 写入所有数据
                total_frames = 0
                # 根据位深度计算每个样本的字节数
                bytes_per_sample = 3 if self.format == pyaudio.paInt24 else 2
                for chunk in recording_data_copy:
                    wf.writeframes(chunk)
                    total_frames += len(chunk) // (self.channels * bytes_per_sample)  # 计算帧数
                
                wf.close()
                
                actual_duration = total_frames / self.sample_rate
                print(f"DEBUG: 音频已保存到 {filename}, 时长: {actual_duration:.2f}秒, 总帧数: {total_frames}")
                return True
                
            except Exception as e:
                print(f"DEBUG: 保存音频失败: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                self._saving = False
    
    # 原有的其他方法保持不变
    def _get_loopback_device(self):
        """获取Loopback设备 - 优化PyAudio实例管理"""
        if not HAS_PYAUDIO_WPATCH:
            print("DEBUG: pyaudiowpatch未安装，无法录制系统音频")
            return None
        
        # 如果已有PyAudio实例，复用它；否则创建新实例
        temp_pa = None
        try:
            if not self.pa:
                temp_pa = pyaudio.PyAudio()
                self.pa = temp_pa
                self.initial_pa = temp_pa
            else:
                temp_pa = self.pa
            
            # 尝试查找特定名称的Loopback设备
            for i in range(temp_pa.get_device_count()):
                device_info = temp_pa.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0 and 'loopback' in device_info['name'].lower():
                    print(f"DEBUG: 找到Loopback设备: {device_info['name']}")
                    return device_info
            
            # 如果没找到特定名称的设备，尝试查找第一个可用的输入设备
            for i in range(temp_pa.get_device_count()):
                device_info = temp_pa.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    # 检查是否是默认输出设备的loopback
                    if device_info.get('isLoopbackDevice', False):
                        print(f"DEBUG: 找到默认Loopback设备: {device_info['name']}")
                        return device_info
            
            return None
        except Exception as e:
            print(f"DEBUG: 获取Loopback设备时出错: {e}")
            # 如果创建了临时实例但失败了，清理它
            if temp_pa and temp_pa != self.pa:
                try:
                    temp_pa.terminate()
                except:
                    pass
            return None
    
    def close(self):
        """关闭PyAudio资源 - 确保正确的资源释放顺序"""
        try:
            # 1. 先确保流已关闭
            if self.stream:
                try:
                    if self.stream.is_active():
                        self.stream.stop_stream()
                    if not self.stream.is_stopped():
                        self.stream.stop_stream()
                    self.stream.close()
                except Exception as e:
                    print(f"DEBUG: 关闭流时出错: {e}")
                finally:
                    self.stream = None
            
            # 2. 等待一小段时间确保资源释放
            time.sleep(0.1)
            
            # 3. 终止PyAudio实例
            if self.pa:
                try:
                    self.pa.terminate()
                except Exception as e:
                    print(f"DEBUG: 终止PyAudio时出错: {e}")
                finally:
                    self.pa = None
                    self.initial_pa = None
            
            # 4. 清理其他资源
            self.recording_thread = None
            self.recording_data = []
            self.loopback_device = None
            
            print("DEBUG: PyAudio资源已完全释放")
        except Exception as e:
            print(f"DEBUG: 关闭PyAudio资源时发生错误: {e}")
            # 强制清理
            self.stream = None
            self.pa = None
            self.initial_pa = None
            self.recording_thread = None


class MicrophoneAudioRecorder:
    """麦克风音频录制器 - 基于SystemAudioRecorder的实现"""
    def __init__(self, device_name=None):
        self.pa = None
        self.stream = None
        self.recording_thread = None
        self.is_recording = False
        self.recording_data = []
        # 使用更高的位深度以提高音质
        self.format = pyaudio.paInt24 if hasattr(pyaudio, 'paInt24') else pyaudio.paInt16
        self.channels = 1  # 麦克风通常使用单声道
        # 默认使用更高的采样率
        self.sample_rate = 48000
        # 进一步增大缓冲区以彻底解决卡顿问题
        self.chunk = 8192  # 从4096增大到8192，提供更好的稳定性
        self.microphone_device = None
        self.device_name = device_name  # 保存用户指定的设备名称
        
        # 新增：用于连续录制的变量
        self.last_read_time = 0  # 记录上次读取时间
        self.chunk_duration = self.chunk / self.sample_rate  # 每个chunk的时长(秒)
        self.silence_data = None  # 预生成的静音数据
        self.read_timeout = 0.1  # 读取超时时间(秒)
        self.initial_pa = None  # 保存初始的pyaudio实例
        self.paused = False  # 暂停标志
        self.pause_start_time = None  # 暂停开始时间
        self.total_pause_duration = 0.0  # 累计暂停时长
        
        # 线程安全保护
        self._operation_lock = threading.Lock()  # 保护关键操作
        self._saving = False  # 标记是否正在保存
        
        # 动态音频控制
        self.audio_muted = False  # 是否静音（录制过程中动态控制）
        
    def _generate_silence_chunk(self):
        """生成一个chunk的静音数据"""
        # 根据位深度计算静音数据大小
        bytes_per_sample = 3 if self.format == pyaudio.paInt24 else 2  # 24位为3字节，16位为2字节
        silence_size = self.chunk * self.channels * bytes_per_sample
        return b'\x00' * silence_size
    
    def start_recording(self):
        """开始录制麦克风音频 - 连续录制版本"""
        if not HAS_PYAUDIO_WPATCH:
            print("DEBUG: pyaudiowpatch未安装，尝试使用pyaudio")
            # 尝试使用标准pyaudio
            try:
                import pyaudio as standard_pyaudio
                self.pa = standard_pyaudio.PyAudio()
            except:
                print("DEBUG: pyaudio也未安装，无法录制麦克风音频")
                return False
        else:
            if not self.pa:
                self.pa = pyaudio.PyAudio()
                self.initial_pa = self.pa
            
        if self.is_recording:
            print("DEBUG: 麦克风已经在录制中")
            return False
        
        # 获取麦克风设备
        self.microphone_device = self._get_microphone_device()
        if not self.microphone_device:
            print("DEBUG: 未找到合适的麦克风设备")
            return False
        
        # 使用设备支持的实际采样率
        self.sample_rate = int(self.microphone_device['defaultSampleRate'])
        # 重新计算chunk时长
        self.chunk_duration = self.chunk / self.sample_rate
        # 预生成静音数据
        self.silence_data = self._generate_silence_chunk()
        
        print(f"DEBUG: 使用麦克风设备 {self.microphone_device['name']} 开始连续录制，采样率: {self.sample_rate}Hz")
        
        self.is_recording = True
        self.recording_data = []
        self.last_read_time = time.time()  # 初始化时间记录
        
        try:
            # 打开音频流 - 优化配置以减少延迟和提高稳定性
            self.stream = self.pa.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=int(self.microphone_device['index']),
                frames_per_buffer=self.chunk,
                stream_callback=None,
                start=False
            )
            
            # 启动流
            self.stream.start_stream()
            
        except Exception as e:
            print(f"DEBUG: 打开麦克风音频流失败: {e}")
            self.is_recording = False
            return False
        
        # 开始录制线程 - 使用更低优先级避免干扰主线程
        self.recording_thread = threading.Thread(target=self._continuous_record_thread)
        self.recording_thread.daemon = True
        try:
            import ctypes
            # 设置线程优先级为低于正常，减少对UI的影响
            thread_id = self.recording_thread.ident
            handle = ctypes.windll.kernel32.OpenThread(0x0200, False, thread_id)
            ctypes.windll.kernel32.SetThreadPriority(handle, 0x0001)  # THREAD_PRIORITY_LOWEST
        except:
            pass  # 如果设置优先级失败，继续执行
        
        self.recording_thread.start()
        
        return True
    
    def _continuous_record_thread(self):
        """连续录制线程 - 确保音频数据连续，修复卡顿问题"""
        import audioop  # 用于音频处理
        
        print("DEBUG: 开始麦克风连续音频录制线程")
        
        # 记录开始时间
        start_time = time.time()
        last_read_index = 0  # 记录最后读取的位置索引
        
        # 动态休眠时间 - 根据chunk大小调整，使用更短的休眠时间以提高响应性
        chunk_size_ms = int(self.chunk_duration * 1000 * 0.3)  # 使用chunk时长的30%作为基准休眠时间，减少延迟
        sleep_interval = max(0.001, chunk_size_ms / 1000.0)  # 最小1ms，提高读取频率
        
        # 减少日志输出以提高性能
        log_counter = 0
        
        # 连续读取计数器，用于检测是否有数据可读
        consecutive_empty_reads = 0
        max_empty_reads = 3  # 连续3次空读后才休眠
        
        while self.is_recording:
            try:
                current_time = time.time()
                # 如果暂停，不计算时间，暂停期间不补充静音
                if self.paused:
                    # 暂停期间，不读取数据，不补充静音，只休眠
                    time.sleep(0.1)
                    continue
                
                # 计算实际录制时长（排除暂停时间）
                elapsed = current_time - start_time - self.total_pause_duration
                
                # 计算当前应该有多少个chunk
                expected_chunks_current = int(elapsed / self.chunk_duration)
                
                # 优先读取音频数据，而不是先补充静音
                data_read = False
                if self.stream and self.is_recording:
                    try:
                        # 检查流是否仍然活跃且未停止
                        if self.stream.is_active() and not self.stream.is_stopped():
                            # 更积极的读取策略：持续尝试读取，直到没有数据可读
                            read_attempts = 0
                            max_read_attempts = 5  # 每次循环最多尝试读取5个chunk
                            
                            while read_attempts < max_read_attempts:
                                try:
                                    # 检查是否有数据可读（非阻塞检查）
                                    if self.stream.get_read_available() >= self.chunk:
                                        # 读取音频数据（非阻塞模式）
                                        data = self.stream.read(self.chunk, exception_on_overflow=False)
                                                                                
                                        # 检查是否静音，如果静音则替换为静音数据
                                        if self.audio_muted:
                                            data = self.silence_data
                                                                                
                                        # 检查数据是否有效
                                        if data and len(data) > 0:
                                            # 确保数据长度正确（防止不完整的数据）
                                            expected_size = self.chunk * self.channels * (3 if self.format == pyaudio.paInt24 else 2)
                                            if len(data) == expected_size:
                                                # 直接追加数据，不替换已有数据
                                                self.recording_data.append(data)
                                                last_read_index = len(self.recording_data) - 1
                                                data_read = True
                                                consecutive_empty_reads = 0
                                                
                                                # 更新最后读取时间
                                                self.last_read_time = current_time
                                                
                                                # 非常少地打印调试信息
                                                log_counter += 1
                                                if len(self.recording_data) % 500 == 0:
                                                    bytes_per_sample = 3 if self.format == pyaudio.paInt24 else 2
                                                    rms = audioop.rms(data, bytes_per_sample) if len(data) >= 6 else 0
                                                    print(f"DEBUG: 麦克风音频电平: {rms}, 已录制: {len(self.recording_data)} chunks")
                                                
                                                read_attempts += 1
                                            else:
                                                # 数据长度不正确，跳过这个chunk
                                                if log_counter % 200 == 0:
                                                    print(f"DEBUG: 警告：麦克风音频数据长度不正确，期望: {expected_size}, 实际: {len(data)}")
                                                break
                                        else:
                                            # 没有数据可读，退出读取循环
                                            consecutive_empty_reads += 1
                                            break
                                    else:
                                        # 没有足够的数据可读，退出读取循环
                                        consecutive_empty_reads += 1
                                        break
                                        
                                except OSError as read_ex:
                                    # OSError通常表示流已关闭或没有数据
                                    error_str = str(read_ex)
                                    if "not open" in error_str.lower() or "closed" in error_str.lower():
                                        print("DEBUG: 麦克风音频流已关闭，停止读取")
                                        break
                                    consecutive_empty_reads += 1
                                    break
                                except Exception as read_ex:
                                    # 读取异常，记录但不中断
                                    error_str = str(read_ex)
                                    if "Input overflowed" in error_str:
                                        # 缓冲区溢出，说明数据积压，需要更频繁读取
                                        consecutive_empty_reads = 0
                                        if log_counter % 100 == 0:
                                            print(f"DEBUG: 麦克风音频缓冲区溢出，需要更频繁读取")
                                    elif log_counter % 100 == 0:
                                        print(f"DEBUG: 麦克风音频读取异常: {read_ex}")
                                    consecutive_empty_reads += 1
                                    break
                            
                            # 如果没有读取到数据，增加空读计数
                            if not data_read:
                                consecutive_empty_reads += 1
                    except Exception as read_error:
                        # 其他读取错误，记录但不中断
                        error_str = str(read_error)
                        if "Input overflowed" not in error_str and log_counter % 100 == 0:
                            print(f"DEBUG: 麦克风音频读取错误: {error_str}")
                
                # 只有在没有读取到数据且数据不足时才补充静音
                if not data_read:
                    needed_chunks = expected_chunks_current - len(self.recording_data)
                    if needed_chunks > 0:
                        # 只补充必要的静音，避免过度补充
                        chunks_to_add = min(needed_chunks, 10)
                        for _ in range(chunks_to_add):
                            self.recording_data.append(self.silence_data)
                        
                        log_counter += 1
                        if log_counter % 50 == 0:
                            print(f"DEBUG: 麦克风补充静音，当前: {len(self.recording_data)}, 期望: {expected_chunks_current}")
                
                # 检查是否应该退出录制
                if not self.is_recording:
                    break
                
                # 智能休眠 - 根据读取情况调整休眠时间
                if data_read:
                    time.sleep(max(0.001, sleep_interval * 0.5))
                elif consecutive_empty_reads < max_empty_reads:
                    time.sleep(max(0.001, sleep_interval * 0.7))
                elif len(self.recording_data) < expected_chunks_current - 5:
                    time.sleep(max(0.001, sleep_interval * 0.3))
                elif len(self.recording_data) > expected_chunks_current + 20:
                    time.sleep(sleep_interval * 1.5)
                else:
                    time.sleep(sleep_interval)
                
                # 限制内存使用
                if len(self.recording_data) > 10000:
                    self.recording_data = self.recording_data[-8000:]
                    if log_counter % 100 == 0:
                        print(f"DEBUG: 麦克风音频数据清理，当前: {len(self.recording_data)}")
                    
            except Exception as e:
                if log_counter % 500 == 0:
                    print(f"DEBUG: 麦克风录制线程错误: {e}")
                time.sleep(0.005)
        
        print(f"DEBUG: 麦克风连续录制线程结束，总共录制 {len(self.recording_data)} 个chunk")
    
    def pause_recording(self):
        """暂停录制（停止读取，但保留数据和流）"""
        if not self.is_recording:
            print("DEBUG: 麦克风没有在录制中，无法暂停")
            return False
        
        if self.paused:
            print("DEBUG: 麦克风音频录制已经暂停")
            return True
        
        print("DEBUG: 暂停麦克风音频录制")
        # 记录暂停开始时间
        self.pause_start_time = time.time()
        self.paused = True
        
        # 停止音频流，但保留流和数据
        if self.stream:
            try:
                if self.stream.is_active():
                    self.stream.stop_stream()
                    print("DEBUG: 麦克风音频流已暂停")
            except Exception as e:
                print(f"DEBUG: 暂停麦克风音频流时出错: {e}")
        
        return True
    
    def resume_recording(self):
        """恢复录制（重新启动音频流）"""
        if not self.is_recording:
            print("DEBUG: 麦克风没有在录制中，无法恢复")
            return False
        
        if not self.paused:
            print("DEBUG: 麦克风音频录制未暂停，无需恢复")
            return True
        
        print("DEBUG: 恢复麦克风音频录制")
        
        # 计算暂停时长并累加
        if self.pause_start_time:
            pause_duration = time.time() - self.pause_start_time
            self.total_pause_duration += pause_duration
            print(f"DEBUG: 麦克风暂停时长: {pause_duration:.2f}秒, 累计暂停时长: {self.total_pause_duration:.2f}秒")
            self.pause_start_time = None
        
        self.paused = False
        
        # 重新启动音频流
        if self.stream:
            try:
                # 检查流是否已关闭
                if self.stream.is_stopped():
                    try:
                        self.stream.start_stream()
                        print("DEBUG: 麦克风音频流已恢复")
                    except Exception as e:
                        print(f"DEBUG: 重新启动麦克风音频流失败: {e}，尝试重新创建流...")
                        try:
                            if not self.stream.is_stopped():
                                self.stream.stop_stream()
                            self.stream.close()
                        except:
                            pass
                        
                        # 重新创建流
                        try:
                            self.stream = self.pa.open(
                                format=self.format,
                                channels=self.channels,
                                rate=self.sample_rate,
                                input=True,
                                input_device_index=int(self.microphone_device['index']),
                                frames_per_buffer=self.chunk,
                                stream_callback=None,
                                start=False
                            )
                            self.stream.start_stream()
                            print("DEBUG: 麦克风音频流已重新创建并启动")
                        except Exception as e2:
                            print(f"DEBUG: 重新创建麦克风音频流失败: {e2}")
                            return False
                elif not self.stream.is_active():
                    try:
                        self.stream.start_stream()
                        print("DEBUG: 麦克风音频流已恢复")
                    except Exception as e:
                        print(f"DEBUG: 恢复麦克风音频流时出错: {e}")
                        return False
                else:
                    print("DEBUG: 麦克风音频流已在运行")
            except Exception as e:
                print(f"DEBUG: 恢复麦克风音频流时出错: {e}")
                return False
        else:
            print("DEBUG: 警告：麦克风音频流不存在，无法恢复")
            return False
        
        return True
    
    def mute_audio(self):
        """静音（录制过程中禁用音频）"""
        print("DEBUG: MicrophoneAudioRecorder - 静音麦克风")
        self.audio_muted = True
        
        # 立即清空音频流缓冲区，减少延迟
        if self.stream and self.stream.is_active():
            try:
                # 读取并丢弃当前缓冲区中的所有数据
                available = self.stream.get_read_available()
                if available > 0:
                    self.stream.read(available, exception_on_overflow=False)
                    print(f"DEBUG: 已清空麦克风缓冲区 {available} 帧，减少静音延迟")
            except Exception as e:
                print(f"DEBUG: 清空麦克风缓冲区失败: {e}")
        
        return True
    
    def unmute_audio(self):
        """取消静音（录制过程中启用音频）"""
        print("DEBUG: MicrophoneAudioRecorder - 取消静音")
        self.audio_muted = False
        
        # 立即清空音频流缓冲区，避免播放旧数据
        if self.stream and self.stream.is_active():
            try:
                # 读取并丢弃当前缓冲区中的所有数据
                available = self.stream.get_read_available()
                if available > 0:
                    self.stream.read(available, exception_on_overflow=False)
                    print(f"DEBUG: 已清空麦克风缓冲区 {available} 帧，避免播放旧数据")
            except Exception as e:
                print(f"DEBUG: 清空麦克风缓冲区失败: {e}")
        
        return True
    
    def stop_recording(self):
        """停止录制（线程安全）"""
        with self._operation_lock:
            if not self.is_recording:
                print("DEBUG: 麦克风没有在录制中")
                return False
            
            print("DEBUG: 停止麦克风连续音频录制")
            self.is_recording = False
            
            # 先停止音频流，避免继续读取数据
            if self.stream:
                try:
                    if self.stream.is_active():
                        self.stream.stop_stream()
                except Exception as e:
                    print(f"DEBUG: 停止麦克风音频流时出错: {e}")
            
            # 等待录制线程结束
            if self.recording_thread and self.recording_thread.is_alive():
                print("DEBUG: 等待麦克风录制线程结束...")
                self.recording_thread.join(timeout=5.0)
                if self.recording_thread.is_alive():
                    print("DEBUG: 警告：麦克风录制线程未在超时时间内结束")
                else:
                    print("DEBUG: 麦克风录制线程已结束")
            
            # 关闭流（在线程结束后）
            if self.stream:
                try:
                    if not self.stream.is_stopped():
                        self.stream.stop_stream()
                    self.stream.close()
                    self.stream = None
                except Exception as e:
                    print(f"DEBUG: 关闭麦克风音频流时出错: {e}")
                    self.stream = None
            
            # 计算总时长
            total_duration = len(self.recording_data) * self.chunk_duration
            print(f"DEBUG: 麦克风音频录制完成，总时长: {total_duration:.2f}秒, 总数据量: {len(self.recording_data)} chunks")
            
            return True
    
    def save_recording(self, filename="microphone_audio.wav"):
        """保存录制的音频到WAV文件（线程安全）"""
        with self._operation_lock:
            # 检查是否正在保存，避免重复保存
            if self._saving:
                print("DEBUG: 麦克风音频正在保存中，跳过重复操作")
                return False
            
            if not self.recording_data:
                print("DEBUG: 没有麦克风录制数据可以保存")
                return False
            
            self._saving = True
            try:
                print(f"DEBUG: 正在保存麦克风音频到 {filename}...")
                print(f"DEBUG: 麦克风音频数据信息: {len(self.recording_data)} chunks, 采样率: {self.sample_rate}Hz")
                
                # 创建数据副本，避免在保存过程中数据被修改
                recording_data_copy = list(self.recording_data)
                
                import wave
                wf = wave.open(filename, 'wb')
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.pa.get_sample_size(self.format))
                wf.setframerate(self.sample_rate)
                
                # 写入所有数据
                total_frames = 0
                bytes_per_sample = 3 if self.format == pyaudio.paInt24 else 2
                for chunk in recording_data_copy:
                    wf.writeframes(chunk)
                    total_frames += len(chunk) // (self.channels * bytes_per_sample)
                
                wf.close()
                
                actual_duration = total_frames / self.sample_rate
                print(f"DEBUG: 麦克风音频已保存到 {filename}, 时长: {actual_duration:.2f}秒, 总帧数: {total_frames}")
                return True
                
            except Exception as e:
                print(f"DEBUG: 保存麦克风音频失败: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                self._saving = False
    
    def _get_microphone_device(self):
        """获取麦克风设备"""
        if not self.pa:
            print("DEBUG: PyAudio未初始化")
            return None
        
        try:
            # 如果用户指定了设备名称，尝试匹配
            if self.device_name:
                for i in range(self.pa.get_device_count()):
                    device_info = self.pa.get_device_info_by_index(i)
                    if device_info['maxInputChannels'] > 0:
                        # 尝试匹配设备名称
                        if self.device_name.lower() in device_info['name'].lower():
                            print(f"DEBUG: 找到匹配的麦克风设备: {device_info['name']}")
                            return device_info
            
            # 如果没有指定设备或未找到匹配，使用默认输入设备
            default_input_index = self.pa.get_default_input_device_info()['index']
            device_info = self.pa.get_device_info_by_index(default_input_index)
            print(f"DEBUG: 使用默认麦克风设备: {device_info['name']}")
            return device_info
            
        except Exception as e:
            print(f"DEBUG: 获取麦克风设备时出错: {e}")
            return None
    
    def close(self):
        """关闭PyAudio资源 - 确保正确的资源释放顺序"""
        try:
            # 1. 先确保流已关闭
            if self.stream:
                try:
                    if self.stream.is_active():
                        self.stream.stop_stream()
                    if not self.stream.is_stopped():
                        self.stream.stop_stream()
                    self.stream.close()
                except Exception as e:
                    print(f"DEBUG: 关闭麦克风流时出错: {e}")
                finally:
                    self.stream = None
            
            # 2. 等待一小段时间确保资源释放
            time.sleep(0.1)
            
            # 3. 终止PyAudio实例
            if self.pa:
                try:
                    self.pa.terminate()
                except Exception as e:
                    print(f"DEBUG: 终止麦克风PyAudio时出错: {e}")
                finally:
                    self.pa = None
                    self.initial_pa = None
            
            # 4. 清理其他资源
            self.recording_thread = None
            self.recording_data = []
            self.microphone_device = None
            
            print("DEBUG: 麦克风PyAudio资源已完全释放")
        except Exception as e:
            print(f"DEBUG: 关闭麦克风PyAudio资源时发生错误: {e}")
            # 强制清理
            self.stream = None
            self.pa = None
            self.initial_pa = None
            self.recording_thread = None


class FileListWindow(QWidget):
    """文件列表窗口 - 独立窗口"""
    def __init__(self, parent=None):
        super().__init__(None)  # 设置为None，使其成为独立窗口，不依赖父窗口
        self.setWindowTitle('文件列表')
        self.setFixedSize(800, 600)
        # 移除 WindowStaysOnTopHint，使其作为普通独立窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 录制文件保存目录（智能检测D盘或C盘）
        self.recordings_dir = self._get_default_recordings_dir()
        if not os.path.exists(self.recordings_dir):
            try:
                os.makedirs(self.recordings_dir)
                print(f"DEBUG: 文件列表窗口初始化时自动创建目录: {self.recordings_dir}")
            except Exception as e:
                print(f"DEBUG: 创建录制目录失败: {e}")
        
        # 窗口拖动功能
        self.dragging = False
        self.drag_position = QPoint()
        
        self.init_ui()
        self.load_file_list()
    
    def init_ui(self):
        """初始化UI"""
        # 创建中央部件
        central_widget = QWidget()
        central_widget.setStyleSheet(
            "background-color: #1a1a21; "
            "border-radius: 12px;"
        )
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(central_widget)
        
        # 创建主布局
        content_layout = QVBoxLayout(central_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 1. 标题栏
        title_bar = self.create_title_bar()
        content_layout.addWidget(title_bar)
        
        # 标题栏和文件列表区域之间的分割线
        divider1 = QLabel()
        divider1.setFixedHeight(1)
        divider1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        divider1.setStyleSheet("border: none; background-color: #1c2129; margin: 0; padding: 0;")
        content_layout.addWidget(divider1)
        
        # 2. 文件列表区域
        file_list_area = self.create_file_list_area()
        content_layout.addWidget(file_list_area)
        
        # 文件列表区域和底部操作栏之间的分割线
        divider2 = QLabel()
        divider2.setFixedHeight(1)
        divider2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        divider2.setStyleSheet("border: none; background-color: #1c2129; margin: 0; padding: 0;")
        content_layout.addWidget(divider2)
        
        # 3. 底部操作栏
        bottom_bar = self.create_bottom_bar()
        content_layout.addWidget(bottom_bar)
    
    def create_title_bar(self):
        """创建标题栏"""
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("background-color: #1a1a21; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px")
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)
        title_layout.setSpacing(8)
        
        # 标题
        title_label = QLabel('文件列表')
        title_label.setStyleSheet("color: #FFFFFF; font-family: 'Microsoft YaHei'; font-size: 14px; font-weight: 500;")
        
        # 右侧按钮
        right_layout = QHBoxLayout()
        right_layout.setAlignment(Qt.AlignRight)
        right_layout.setSpacing(12)
        
        # 关闭按钮
        close_button = QPushButton('×')
        close_button.setFixedSize(28, 28)
        close_button.setStyleSheet(
            "background-color: transparent; "
            "color: #9CA3AF; "
            "font-size: 18px; "
            "border: none;"
        )
        close_button.setToolTip('关闭')
        close_button.clicked.connect(self.close)
        
        # 关闭按钮悬停效果
        def close_enter(event):
            close_button.setStyleSheet(
                "background-color: #EF4444; "
                "color: #FFFFFF; "
                "font-size: 18px; "
                "border-radius: 4px; "
                "border: none;"
            )
            event.accept()
        
        def close_leave(event):
            close_button.setStyleSheet(
                "background-color: transparent; "
                "color: #9CA3AF; "
                "font-size: 18px; "
                "border: none;"
            )
            event.accept()
        
        close_button.enterEvent = close_enter
        close_button.leaveEvent = close_leave
        
        right_layout.addWidget(close_button)
        
        title_layout.addWidget(title_label, 1)
        title_layout.addLayout(right_layout)
        
        # 添加拖动事件
        title_bar.mousePressEvent = self.mouse_press_event
        title_bar.mouseMoveEvent = self.mouse_move_event
        title_bar.mouseReleaseEvent = self.mouse_release_event
        
        return title_bar
    
    def create_file_list_area(self):
        """创建文件列表区域"""
        container = QWidget()
        container.setStyleSheet("background-color: #13131a; border-top-left-radius: 0px; border-top-right-radius: 0px; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # 创建表格
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(3)
        self.file_table.setHorizontalHeaderLabels(['文件名', '大小', '创建时间'])
        
        # 设置表格样式 - 优化可见性
        self.file_table.setStyleSheet("""
            QTableWidget {
                background-color: #1a1a21;
                border: 1px solid #374151;
                border-radius: 8px;
                color: #FFFFFF;
                gridline-color: #374151;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
                selection-background-color: #2d2d38;
                selection-color: #FFFFFF;
            }
            QTableWidget::item {
                padding: 8px;
                border: none;
                background-color: #1a1a21;
            }
            QTableWidget::item:alternate {
                background-color: #13131a;
            }
            QTableWidget::item:selected {
                background-color: #3B82F6;
                color: #FFFFFF;
            }
            QTableWidget::item:hover {
                background-color: #2d2d38;
            }
            QHeaderView::section {
                background-color: #2d2d38;
                color: #D1D5DB;
                padding: 10px 8px;
                border: none;
                border-bottom: 2px solid #4B5563;
                font-weight: 600;
                font-size: 13px;
            }
        """)
        
        # 设置列宽
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 文件名列自动拉伸
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 大小列适应内容
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 时间列适应内容
        
        # 设置表格属性
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 启用多选模式，支持Ctrl/Shift和拖动选择
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setAlternatingRowColors(True)  # 启用交替行颜色，提高可读性
        self.file_table.setShowGrid(False)  # 隐藏网格线，更美观
        self.file_table.verticalHeader().setDefaultSectionSize(35)  # 设置默认行高
        self.file_table.setDragEnabled(True)  # 启用拖动选择
        
        layout.addWidget(self.file_table)
        
        return container
    
    def create_bottom_bar(self):
        """创建底部操作栏"""
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(60)
        bottom_bar.setStyleSheet("background-color: #13131a; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")
        
        layout = QHBoxLayout(bottom_bar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # 左侧操作按钮
        left_layout = QHBoxLayout()
        left_layout.setSpacing(12)
        
        # 刷新按钮
        refresh_button = QPushButton('刷新')
        refresh_button.setFixedSize(80, 36)
        refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #2d2d38;
                color: #FFFFFF;
                border: 1px solid #4B5563;
                border-radius: 6px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #374151;
                border: 1px solid #ff3a3a;
            }
        """)
        refresh_button.clicked.connect(self.load_file_list)
        
        # 打开文件夹按钮
        open_folder_button = QPushButton('打开文件夹')
        open_folder_button.setFixedSize(100, 36)
        open_folder_button.setStyleSheet("""
            QPushButton {
                background-color: #2d2d38;
                color: #FFFFFF;
                border: 1px solid #4B5563;
                border-radius: 6px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #374151;
                border: 1px solid #ff3a3a;
            }
        """)
        open_folder_button.clicked.connect(self.open_recordings_folder)
        
        # 清空按钮
        clear_all_button = QPushButton('清空')
        clear_all_button.setFixedSize(80, 36)
        clear_all_button.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: #FFFFFF;
                border: 1px solid #B91C1C;
                border-radius: 6px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #EF4444;
                border: 1px solid #DC2626;
            }
        """)
        clear_all_button.clicked.connect(self.clear_all_files)
        
        left_layout.addWidget(refresh_button)
        left_layout.addWidget(open_folder_button)
        left_layout.addWidget(clear_all_button)
        
        # 右侧操作按钮
        right_layout = QHBoxLayout()
        right_layout.setSpacing(12)
        
        # 删除按钮
        self.delete_button = QPushButton('删除')
        self.delete_button.setFixedSize(90, 36)
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #EF4444;
            }
            QPushButton:disabled {
                background-color: #374151;
                color: #9CA3AF;
            }
        """)
        self.delete_button.clicked.connect(self.delete_selected_files)
        self.delete_button.setEnabled(False)
        
        # 打开按钮
        self.open_button = QPushButton('打开')
        self.open_button.setFixedSize(80, 36)
        self.open_button.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
            QPushButton:disabled {
                background-color: #374151;
                color: #9CA3AF;
            }
        """)
        self.open_button.clicked.connect(self.open_selected_file)
        self.open_button.setEnabled(False)
        
        right_layout.addWidget(self.delete_button)
        right_layout.addWidget(self.open_button)
        
        layout.addLayout(left_layout)
        layout.addStretch()
        layout.addLayout(right_layout)
        
        # 连接表格选择事件
        self.file_table.itemSelectionChanged.connect(self.on_selection_changed)
        
        return bottom_bar
    
    def _get_default_recordings_dir(self):
        """智能获取默认录制目录，优先D盘，不存在时使用C盘"""
        # 优先使用D盘
        d_drive_path = r'D:\灵感录屏储存\recordings'
        c_drive_path = r'C:\灵感录屏储存\recordings'
        
        # 检测D盘是否真实存在且可访问
        d_drive_available = False
        try:
            # 尝试访问D盘根目录，如果成功说明D盘存在
            if os.path.isdir('D:\\'):
                # 尝试列举目录来确认可访问性
                os.listdir('D:\\')
                d_drive_available = True
        except (OSError, PermissionError):
            # D盘不存在或不可访问
            d_drive_available = False
        
        if d_drive_available:
            default_dir = d_drive_path
        else:
            print("DEBUG: 未检测到D盘或D盘不可访问，将使用C盘作为默认保存路径")
            default_dir = c_drive_path
        
        return default_dir
    
    def load_file_list(self):
        """加载文件列表"""
        self.file_table.setRowCount(0)
        
        # 如果目录不存在，自动创建
        if not os.path.exists(self.recordings_dir):
            try:
                os.makedirs(self.recordings_dir)
                print(f"DEBUG: 文件列表窗口自动创建目录: {self.recordings_dir}")
            except Exception as e:
                print(f"DEBUG: 创建录制目录失败: {e}")
            return
        
        # 获取所有文件
        files = []
        for filename in os.listdir(self.recordings_dir):
            filepath = os.path.join(self.recordings_dir, filename)
            if os.path.isfile(filepath):
                # 只显示视频文件
                if filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')):
                    files.append(filepath)
        
        # 按创建时间排序（最新的在前）
        files.sort(key=lambda x: os.path.getctime(x), reverse=True)
        
        # 填充表格
        for filepath in files:
            filename = os.path.basename(filepath)
            file_size = os.path.getsize(filepath)
            create_time = datetime.fromtimestamp(os.path.getctime(filepath))
            
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)
            
            # 文件名
            name_item = QTableWidgetItem(filename)
            self.file_table.setItem(row, 0, name_item)
            
            # 文件大小
            size_str = self.format_file_size(file_size)
            size_item = QTableWidgetItem(size_str)
            self.file_table.setItem(row, 1, size_item)
            
            # 创建时间
            time_str = create_time.strftime('%Y-%m-%d %H:%M:%S')
            time_item = QTableWidgetItem(time_str)
            self.file_table.setItem(row, 2, time_item)
            
            # 保存文件路径到item的data中
            name_item.setData(Qt.UserRole, filepath)
    
    def format_file_size(self, size_bytes):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    
    def on_selection_changed(self):
        """选择变化时的处理 - 支持多选"""
        selected_rows = set()
        for item in self.file_table.selectedItems():
            selected_rows.add(item.row())
        
        has_selection = len(selected_rows) > 0
        self.open_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        
        # 更新按钮文本，显示选中数量
        if has_selection:
            count = len(selected_rows)
            if count > 1:
                self.delete_button.setText(f'批量删除({count})')
            else:
                self.delete_button.setText('批量删除')
        else:
            self.delete_button.setText('批量删除')
    
    def open_selected_file(self):
        """打开选中的文件 - 支持多选"""
        selected_rows = set()
        for item in self.file_table.selectedItems():
            selected_rows.add(item.row())
        
        if selected_rows:
            # 打开所有选中的文件
            for row in selected_rows:
                name_item = self.file_table.item(row, 0)
                if name_item:
                    filepath = name_item.data(Qt.UserRole)
                    if filepath:
                        self.open_file(filepath)
    
    def delete_selected_files(self):
        """批量删除选中的文件"""
        selected_rows = set()
        for item in self.file_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        # 获取所有要删除的文件路径
        filepaths = []
        filenames = []
        for row in selected_rows:
            name_item = self.file_table.item(row, 0)
            if name_item:
                filepath = name_item.data(Qt.UserRole)
                if filepath and os.path.exists(filepath):
                    filepaths.append(filepath)
                    filenames.append(os.path.basename(filepath))
        
        if not filepaths:
            return
        
        # 确认删除
        count = len(filepaths)
        if count == 1:
            message = f'确定要删除文件 "{filenames[0]}" 吗？\n此操作无法撤销。'
        else:
            message = f'确定要删除选中的 {count} 个文件吗？\n此操作无法撤销。\n\n文件列表：\n' + '\n'.join(filenames[:10])
            if count > 10:
                message += f'\n... 还有 {count - 10} 个文件'
        
        reply = CustomMessageBox.question(
            self, '确认删除',
            message
        )
        
        if reply:
            success_count = 0
            fail_count = 0
            failed_files = []
            
            for filepath in filepaths:
                try:
                    os.remove(filepath)
                    success_count += 1
                except Exception as e:
                    fail_count += 1
                    failed_files.append((os.path.basename(filepath), str(e)))
            
            # 显示结果
            if fail_count == 0:
                CustomMessageBox.show_message(self, '成功', f'已成功删除 {success_count} 个文件', 'information')
            else:
                error_msg = f'成功删除 {success_count} 个文件\n失败 {fail_count} 个文件：\n'
                for filename, error in failed_files:
                    error_msg += f'\n{filename}: {error}'
                CustomMessageBox.show_message(self, '部分失败', error_msg, 'warning')
            
            # 刷新列表
            self.load_file_list()
    
    def open_file(self, filepath):
        """打开文件"""
        if os.path.exists(filepath):
            # Windows系统使用os.startfile打开文件
            if sys.platform == 'win32':
                os.startfile(filepath)
            else:
                # 其他系统使用默认程序打开
                import subprocess
                subprocess.call(['xdg-open' if sys.platform == 'linux' else 'open', filepath])
    
    def delete_file(self, filepath):
        """删除单个文件"""
        if os.path.exists(filepath):
            filename = os.path.basename(filepath)
            reply = CustomMessageBox.question(
                self, '确认删除',
                f'确定要删除文件 "{filename}" 吗？\n此操作无法撤销。'
            )
            
            if reply:
                try:
                    os.remove(filepath)
                    CustomMessageBox.show_message(self, '成功', '文件已删除', 'information')
                    self.load_file_list()  # 刷新列表
                except Exception as e:
                    CustomMessageBox.show_message(self, '错误', f'删除文件失败：{str(e)}', 'critical')
    
    def clear_all_files(self):
        """清空所有文件"""
        if not os.path.exists(self.recordings_dir):
            CustomMessageBox.show_message(self, '提示', '录制文件夹不存在', 'information')
            return
        
        # 获取所有文件
        files = []
        for filename in os.listdir(self.recordings_dir):
            filepath = os.path.join(self.recordings_dir, filename)
            if os.path.isfile(filepath):
                # 只统计视频文件
                if filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')):
                    files.append(filepath)
        
        if not files:
            CustomMessageBox.show_message(self, '提示', '文件夹中没有可删除的文件', 'information')
            return
        
        # 确认清空
        count = len(files)
        reply = CustomMessageBox.question(
            self, '确认清空',
            f'确定要删除文件夹中的所有 {count} 个文件吗？\n此操作无法撤销！'
        )
        
        if reply:
            success_count = 0
            fail_count = 0
            failed_files = []
            
            for filepath in files:
                try:
                    os.remove(filepath)
                    success_count += 1
                except Exception as e:
                    fail_count += 1
                    failed_files.append((os.path.basename(filepath), str(e)))
            
            # 显示结果
            if fail_count == 0:
                CustomMessageBox.show_message(self, '成功', f'已成功删除所有 {success_count} 个文件', 'information')
            else:
                error_msg = f'成功删除 {success_count} 个文件\n失败 {fail_count} 个文件：\n'
                for filename, error in failed_files[:5]:  # 只显示前5个错误
                    error_msg += f'\n{filename}: {error}'
                if len(failed_files) > 5:
                    error_msg += f'\n... 还有 {len(failed_files) - 5} 个文件删除失败'
                CustomMessageBox.show_message(self, '部分失败', error_msg, 'warning')
            
            # 刷新列表
            self.load_file_list()
    
    def open_recordings_folder(self):
        """打开录制文件夹"""
        if os.path.exists(self.recordings_dir):
            if sys.platform == 'win32':
                os.startfile(self.recordings_dir)
            else:
                import subprocess
                subprocess.call(['xdg-open' if sys.platform == 'linux' else 'open', self.recordings_dir])
        else:
            CustomMessageBox.show_message(self, '提示', '录制文件夹不存在', 'information')
    
    def mouse_press_event(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouse_move_event(self, event):
        """鼠标移动事件"""
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouse_release_event(self, event):
        """鼠标释放事件"""
        self.dragging = False
    
    def paintEvent(self, event):
        """绘制圆角窗口"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.transparent)
        painter.drawRect(self.rect())


class AboutWindow(QWidget):
    """关于窗口 - 真正的圆角无边框"""
    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowTitle('关于')
        self.setFixedSize(500, 400)
        # 关键：无边框 + 透明背景 + 无阴影
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.dragging = False
        self.drag_position = QPoint()

        self.init_ui()
        # 初始遮罩
        self.set_rounded_mask()

    # -------------------- 圆角遮罩 --------------------
    def set_rounded_mask(self):
        """把窗口裁剪成圆角矩形，并外扩 2 px 砍掉边缘残影"""
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(-2, -2, 2, 2), 12, 12)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event):
        """拖动边缘调整大小时重新裁剪"""
        self.set_rounded_mask()
        super().resizeEvent(event)

    # -------------------- UI 构建 --------------------
    def init_ui(self):
        central = QWidget(self)
        central.setStyleSheet("""
            background: transparent;   /* 不用纯色铺满 */
            border-radius: 0px;
        """)
        central.setContentsMargins(0, 0, 0, 0)   # ← 关键

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(central)

        content = QVBoxLayout(central)
        content.setSpacing(0)
        content.addWidget(self.create_title_bar())
        content.addWidget(self.create_separator())   # ← 把分割线单拎出来
        content.addWidget(self.create_content_area(), 1)

    def create_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setFixedWidth(self.width() - 18)   # ← 关键
        sep.setStyleSheet("background:#374151;")
        return sep

    # -------------------- 标题栏 --------------------
    def create_title_bar(self):
        bar = QWidget()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background-color: #1a1a21; border-top-left-radius: 12px; border-top-right-radius: 12px;")

        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)

        title = QLabel('关于')
        title.setStyleSheet("color: #fff; font: 14px 'Microsoft YaHei';")

        close = QPushButton('×')
        close.setFixedSize(28, 28)
        close.setStyleSheet("""
            QPushButton{color:#9CA3AF;font-size:18px;border:none}
            QPushButton:hover{background:#EF4444;color:#fff;border-radius:4px}
        """)
        close.clicked.connect(self.close)

        h.addWidget(title)
        h.addStretch()
        h.addWidget(close)

        bar.mousePressEvent = self.mouse_press_event
        bar.mouseMoveEvent = self.mouse_move_event
        bar.mouseReleaseEvent = self.mouse_release_event
        return bar

    # -------------------- 内容区 --------------------
    def create_content_area(self):
        w = QWidget()
        w.setStyleSheet("background-color: #13131a; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(15)

        labels = [
            ('灵感录屏工具', "color:#fff;font:24px;font-weight:600", False),
            ('版本 1.0.0', "color:#9CA3AF;font:14px", False),
            ('一款功能强大的屏幕录制工具\n支持全屏录制、自定义区域录制\n支持多种视频格式输出\n简单易用，高效稳定', "color:#D1D5DB;font:13px", False),
            ('GitHub地址：https://github.com/jia070310/lingg-Screensy\n技术支持：718339650@qq.com\n联系QQ：718339650\n微信：example_wechat', "color:#9CA3AF;font:12px", True),
            ('© 2025 灵感录屏工具 版权所有', "color:#6B7280;font:11px", False)
        ]

        for item in labels:
            if len(item) == 3:
                txt, style, selectable = item
            else:
                txt, style = item
                selectable = False
            
            lbl = QLabel(txt)
            lbl.setStyleSheet(style)
            lbl.setAlignment(Qt.AlignCenter)
            
            # 如果需要可选择文本，启用文本选择和右键菜单
            if selectable:
                lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                lbl.setContextMenuPolicy(Qt.DefaultContextMenu)
            
            lay.addWidget(lbl)

        return w

    # -------------------- 拖动 --------------------
    def mouse_press_event(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = e.globalPos() - self.frameGeometry().topLeft()

    def mouse_move_event(self, e):
        if self.dragging and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self.drag_position)

    def mouse_release_event(self, e):
        self.dragging = False


class CustomMessageBox(QDialog):
    """统一样式的提示窗口"""
    def __init__(self, title, message, message_type='information', parent=None):
        super().__init__(None)  # 独立窗口
        self.setWindowTitle(title)
        # 根据消息长度动态调整窗口大小
        message_lines = message.count('\n') + 1
        estimated_height = 180 + (message_lines - 1) * 25  # 基础高度 + 每行额外高度
        # 限制最大高度，避免窗口过大
        max_height = min(estimated_height, 400)
        self.setFixedSize(420, max_height)  # 进一步增加宽度，确保中文文本完全显示
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.message_type = message_type  # 'information', 'warning', 'critical', 'question'
        self.title = title
        self.message = message
        self.result = None  # 用于question类型
        
        self.dragging = False
        self.drag_position = QPoint()
        
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        central_widget.setStyleSheet(
            "background-color: #2d2d35; "
            "border-radius: 12px;"
        )
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(central_widget)
        
        content_layout = QVBoxLayout(central_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 标题栏
        title_bar = self.create_title_bar()
        content_layout.addWidget(title_bar)
        
        # 分割线
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        divider.setStyleSheet("border: none; background-color: #1c2129; margin: 0; padding: 0;")
        content_layout.addWidget(divider)
        
        # 内容区域
        content_area = self.create_content_area()
        content_layout.addWidget(content_area)
    
    def create_title_bar(self):
        """创建标题栏"""
        title_bar = QWidget()
        title_bar.setFixedHeight(32)  # 减小标题栏高度
        title_bar.setStyleSheet("background-color: #2d2d35; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;")
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 0, 12, 0)  # 减小内边距
        title_layout.setSpacing(8)
        
        title_label = QLabel(self.title)
        title_label.setStyleSheet("color: #FFFFFF; font-family: 'Microsoft YaHei'; font-size: 12px; font-weight: 500;")  # 减小字体
        
        right_layout = QHBoxLayout()
        right_layout.setAlignment(Qt.AlignRight)
        
        close_button = QPushButton('×')
        close_button.setFixedSize(24, 24)  # 减小关闭按钮尺寸
        close_button.setStyleSheet(
            "background-color: transparent; "
            "color: #B8BDC7; "
            "font-size: 16px; "  # 减小字体
            "border: none;"
        )
        close_button.setToolTip('关闭')
        close_button.clicked.connect(self.close)
        
        def close_enter(event):
            close_button.setStyleSheet(
                "background-color: #EF4444; "
                "color: #FFFFFF; "
                "font-size: 16px; "  # 减小字体
                "border-radius: 4px; "
                "border: none;"
            )
            event.accept()
        
        def close_leave(event):
            close_button.setStyleSheet(
                "background-color: transparent; "
                "color: #B8BDC7; "
                "font-size: 16px; "  # 减小字体
                "border: none;"
            )
            event.accept()
        
        close_button.enterEvent = close_enter
        close_button.leaveEvent = close_leave
        
        right_layout.addWidget(close_button)
        
        title_layout.addWidget(title_label, 1)
        title_layout.addLayout(right_layout)
        
        title_bar.mousePressEvent = self.mouse_press_event
        title_bar.mouseMoveEvent = self.mouse_move_event
        title_bar.mouseReleaseEvent = self.mouse_release_event
        
        return title_bar
    
    def create_content_area(self):
        """创建内容区域"""
        container = QWidget()
        container.setStyleSheet("background-color: #25252d; border-top-left-radius: 0px; border-top-right-radius: 0px; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 30, 30, 30)  # 增加内边距，确保内容不被遮挡
        layout.setSpacing(20)  # 增加元素间距
        layout.setAlignment(Qt.AlignTop)  # 顶部对齐，避免元素重叠
        
        # 根据类型选择图标和颜色
        icon_map = {
            'information': ('ℹ', '#60A5FA'),
            'warning': ('⚠', '#FCD34D'),
            'critical': ('✕', '#F87171'),
            'question': ('?', '#60A5FA')
        }
        icon_char, icon_color = icon_map.get(self.message_type, ('ℹ', '#3B82F6'))
        
        # 提示图标
        icon_label = QLabel(icon_char)
        icon_label.setStyleSheet(
            f"color: {icon_color}; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 36px;"
        )
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedHeight(50)  # 固定图标高度
        
        # 提示信息
        info_label = QLabel(self.message)
        info_label.setStyleSheet(
            "color: #FFFFFF; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 13px; "
            "font-weight: 500;"
        )
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        info_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 设置自适应尺寸策略
        info_label.setMinimumHeight(60)  # 设置最小高度，确保文本有足够空间显示
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignCenter)
        button_layout.setSpacing(12)
        button_layout.setContentsMargins(0, 10, 0, 0)  # 顶部留出间距
        
        if self.message_type == 'question':
            # 问题类型（确认删除、确认清空等）显示两个按钮：确定和取消
            yes_button = QPushButton('确定')
            yes_button.setFixedSize(80, 36)  # 增大按钮尺寸，使其更明显
            yes_button.setCursor(Qt.PointingHandCursor)  # 设置手型光标
            yes_button.setStyleSheet("""
                QPushButton {
                    background-color: #60A5FA;
                    color: #FFFFFF;
                    border: 1px solid #3B82F6;
                    border-radius: 6px;
                    font-family: 'Microsoft YaHei';
                    font-size: 13px;
                    font-weight: 600;
                    padding: 6px 16px;
                }
                QPushButton:hover {
                    background-color: #3B82F6;
                    border: 1px solid #2563EB;
                }
                QPushButton:pressed {
                    background-color: #2563EB;
                    border: 1px solid #1D4ED8;
                }
            """)
            yes_button.clicked.connect(lambda: self.accept_result(True))
            
            no_button = QPushButton('取消')
            no_button.setFixedSize(80, 36)  # 增大按钮尺寸，使其更明显
            no_button.setCursor(Qt.PointingHandCursor)  # 设置手型光标
            no_button.setStyleSheet("""
                QPushButton {
                    background-color: #6B7280;
                    color: #FFFFFF;
                    border: 1px solid #4B5563;
                    border-radius: 6px;
                    font-family: 'Microsoft YaHei';
                    font-size: 13px;
                    font-weight: 600;
                    padding: 6px 16px;
                }
                QPushButton:hover {
                    background-color: #4B5563;
                    border: 1px solid #374151;
                }
                QPushButton:pressed {
                    background-color: #374151;
                    border: 1px solid #1F2937;
                }
            """)
            no_button.clicked.connect(lambda: self.accept_result(False))
            
            button_layout.addWidget(yes_button)
            button_layout.addWidget(no_button)
        else:
            # 其他类型（information、warning、critical）不显示按钮，自动关闭
            from PyQt5.QtCore import QTimer
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self.close)
            # 根据类型设置不同的自动关闭时间
            if self.message_type == 'information':
                timer.start(2000)  # 信息类型2秒后关闭
            else:
                timer.start(2500)  # 其他类型2.5秒后关闭
        
        layout.addWidget(icon_label, alignment=Qt.AlignCenter)
        layout.addWidget(info_label, stretch=1, alignment=Qt.AlignCenter)  # 允许文本区域拉伸
        # 只有question类型才添加按钮布局
        if self.message_type == 'question':
            layout.addLayout(button_layout)
        
        return container
    
    def accept_result(self, result):
        """接受结果并关闭窗口"""
        self.result = result
        self.close()
    
    def mouse_press_event(self, event):
        if event.button() == Qt.LeftButton:
            # 检查点击位置是否在按钮区域
            # 通过判断点击的y坐标是否在标题栏区域来决定是否允许拖动
            if event.pos().y() <= 32:  # 标题栏高度为32px
                self.dragging = True
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
    
    def mouse_move_event(self, event):
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouse_release_event(self, event):
        self.dragging = False
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.transparent)
        painter.drawRect(self.rect())
    
    @staticmethod
    def show_message(parent, title, message, message_type='information'):
        """显示提示窗口（静态方法）"""
        try:
            msg = CustomMessageBox(title, message, message_type, parent)
            msg.exec_()
            return msg.result
        except Exception as e:
            print(f"DEBUG: 显示消息窗口时出错: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def question(parent, title, message):
        """显示问题提示窗口（返回True/False）"""
        msg = CustomMessageBox(title, message, 'question', parent)
        msg.exec_()
        return msg.result == True
        


class UnderDevelopmentWindow(QWidget):
    """功能开发中提示窗口"""
    def __init__(self, feature_name, parent=None):
        super().__init__(None)  # 独立窗口
        self.setWindowTitle('功能开发中')
        self.setFixedSize(450, 300)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.feature_name = feature_name
        
        self.dragging = False
        self.drag_position = QPoint()
        
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        central_widget.setStyleSheet(
            "background-color: #2d2d35; "
            "border-radius: 12px;"
        )
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(central_widget)
        
        content_layout = QVBoxLayout(central_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 标题栏
        title_bar = self.create_title_bar()
        content_layout.addWidget(title_bar)
        
        # 分割线
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        divider.setStyleSheet("border: none; background-color: #1c2129; margin: 0; padding: 0;")
        content_layout.addWidget(divider)

        # 内容区域
        content_area = self.create_content_area()
        content_layout.addWidget(content_area)
    
    def create_title_bar(self):
        """创建标题栏"""
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("background-color: #2d2d35; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;")
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)
        title_layout.setSpacing(8)
        
        title_label = QLabel('功能开发中')
        title_label.setStyleSheet("color: #FFFFFF; font-family: 'Microsoft YaHei'; font-size: 14px; font-weight: 500;")
        
        right_layout = QHBoxLayout()
        right_layout.setAlignment(Qt.AlignRight)
        
        close_button = QPushButton('×')
        close_button.setFixedSize(28, 28)
        close_button.setStyleSheet(
            "background-color: transparent; "
            "color: #B8BDC7; "
            "font-size: 18px; "
            "border: none;"
        )
        close_button.setToolTip('关闭')
        close_button.clicked.connect(self.close)
        
        def close_enter(event):
            close_button.setStyleSheet(
                "background-color: #EF4444; "
                "color: #FFFFFF; "
                "font-size: 18px; "
                "border-radius: 4px; "
                "border: none;"
            )
            event.accept()
        
        def close_leave(event):
            close_button.setStyleSheet(
                "background-color: transparent; "
                "color: #B8BDC7; "
                "font-size: 18px; "
                "border: none;"
            )
            event.accept()
        
        close_button.enterEvent = close_enter
        close_button.leaveEvent = close_leave
        
        right_layout.addWidget(close_button)
        
        title_layout.addWidget(title_label, 1)
        title_layout.addLayout(right_layout)
        
        title_bar.mousePressEvent = self.mouse_press_event
        title_bar.mouseMoveEvent = self.mouse_move_event
        title_bar.mouseReleaseEvent = self.mouse_release_event
        
        return title_bar
    
    def create_content_area(self):
        """创建内容区域"""
        container = QWidget()
        container.setStyleSheet("background-color: #25252d; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; border-top-left-radius: 0px; border-top-right-radius: 0px;")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)
        
        # 提示图标或文字 - 使用Unicode符号
        icon_label = QLabel('⚙')
        icon_label.setStyleSheet(
            "color: #FCD34D; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 48px;"
        )
        icon_label.setAlignment(Qt.AlignCenter)
        
        # 功能名称
        feature_label = QLabel(f'{self.feature_name}')
        feature_label.setStyleSheet(
            "color: #FFFFFF; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 20px; "
            "font-weight: 600;"
        )
        feature_label.setAlignment(Qt.AlignCenter)
        
        # 提示信息
        info_label = QLabel('正在开发中，敬请期待！')
        info_label.setStyleSheet(
            "color: #E5E7EB; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 14px;"
        )
        info_label.setAlignment(Qt.AlignCenter)
        
        # 确认按钮
        ok_button = QPushButton('知道了')
        ok_button.setFixedSize(120, 40)
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #60A5FA;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-family: 'Microsoft YaHei';
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3B82F6;
            }
        """)
        ok_button.clicked.connect(self.close)
        
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignCenter)
        button_layout.addWidget(ok_button)
        
        layout.addStretch()
        layout.addWidget(icon_label)
        layout.addWidget(feature_label)
        layout.addWidget(info_label)
        layout.addStretch()
        layout.addLayout(button_layout)
        
        return container
    
    def mouse_press_event(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouse_move_event(self, event):
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouse_release_event(self, event):
        self.dragging = False
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.transparent)
        painter.drawRect(self.rect())


class SplashScreen(QWidget):
    """启动窗口 - 显示启动画面和动态信息"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(1000, 353)  # 图片尺寸
        
        # 居中显示
        screen = QDesktopWidget().screenGeometry()
        size = self.geometry()
        self.move(
            (screen.width() - size.width()) // 2,
            (screen.height() - size.height()) // 2
        )
        
        self.init_ui()
        # self.setup_animation()  # 已取消点动画
        
        # 设置窗口圆角遮罩
        self.set_rounded_mask()
    
    def init_ui(self):
        """初始化UI"""
        # 使用无布局，直接定位
        self.setStyleSheet("background-color: transparent;")
        
        # 背景图片标签（填充整个窗口）
        self.bg_label = QLabel(self)
        self.bg_label.setGeometry(0, 0, 1000, 353)
        # 设置圆角样式
        radius = 16  # 圆角半径
        if os.path.exists('iconic/a.png'):
            pixmap = QPixmap('iconic/a.png')
            # 缩放图片到窗口尺寸（忽略宽高比，填充整个窗口）
            scaled_pixmap = pixmap.scaled(1000, 353, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            # 创建圆角图片
            rounded_pixmap = QPixmap(1000, 353)
            rounded_pixmap.fill(Qt.transparent)
            painter = QPainter(rounded_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, 1000, 353, radius, radius)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled_pixmap)
            painter.end()
            self.bg_label.setPixmap(rounded_pixmap)
        else:
            # 如果图片不存在，使用纯色背景
            self.bg_label.setStyleSheet(
                f"background-color: #1a1a21; "
                f"border-radius: {radius}px;"
            )
        self.bg_label.setAlignment(Qt.AlignCenter)
        
        # 启动信息标签（叠加在图片上，右下角）
        self.info_label = QLabel('正在初始化...', self)
        self.info_label.setStyleSheet(
            "color: #FFFFFF; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 16px; "
            "font-weight: 600; "
            "background-color: rgba(0, 0, 0, 0.5); "
            "border-radius: 8px; "
            "padding: 8px 16px;"
        )
        self.info_label.setAlignment(Qt.AlignCenter)
        # 定位在右下角
        info_width = 300
        info_height = 40
        self.info_label.setGeometry(
            1000 - info_width - 30,  # 距离右边30px
            353 - info_height - 15,  # 距离底部15px（往下调整）
            info_width,
            info_height
        )
        
        # 加载动画（点动画）- 已取消
        # self.dots_label = QLabel('', self)
        # self.dots_label.setStyleSheet(
        #     "color: #60A5FA; "
        #     "font-family: 'Microsoft YaHei'; "
        #     "font-size: 20px; "
        #     "font-weight: 700; "
        #     "background-color: transparent;"
        # )
        # self.dots_label.setAlignment(Qt.AlignCenter)
        # # 定位在信息标签左侧
        # dots_width = 50
        # dots_height = 40
        # self.dots_label.setGeometry(
        #     1000 - info_width - dots_width - 30,  # 在信息标签左侧
        #     353 - dots_height - 15,  # 距离底部15px（往下调整）
        #     dots_width,
        #     dots_height
        # )
    
    # def setup_animation(self):
    #     """设置动画"""
    #     # 点动画定时器
    #     self.dots_timer = QTimer()
    #     self.dots_timer.timeout.connect(self.update_dots)
    #     self.dots_count = 0
    #     self.dots_timer.start(300)  # 每300ms更新一次
    
    # def update_dots(self):
    #     """更新点动画"""
    #     self.dots_count = (self.dots_count + 1) % 4
    #     dots = '.' * self.dots_count
    #     self.dots_label.setText(dots)
    
    def update_info(self, message):
        """更新启动信息"""
        self.info_label.setText(message)
        QApplication.processEvents()  # 立即更新UI
    
    def set_rounded_mask(self):
        """设置窗口圆角遮罩"""
        radius = 16  # 圆角半径
        mask = QPixmap(self.size())
        mask.fill(Qt.transparent)
        painter = QPainter(mask)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(Qt.black))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        painter.drawPath(path)
        painter.end()
        self.setMask(mask.mask())
    
    def paintEvent(self, event):
        """绘制圆角窗口"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.transparent)
        # 绘制圆角矩形路径
        from PyQt5.QtCore import QRectF
        path = QPainterPath()
        radius = 16  # 圆角半径
        rect = self.rect()
        path.addRoundedRect(QRectF(rect), radius, radius)
        painter.setClipPath(path)
        painter.drawRect(self.rect())
    
    def closeEvent(self, event):
        """关闭事件"""
        # self.dots_timer.stop()  # 已取消点动画
        event.accept()


class SettingsWindow(QWidget):
    """设置窗口"""
    def __init__(self, parent=None):
        super().__init__(None)  # 独立窗口
        self.setWindowTitle('设置')
        self.setFixedSize(700, 700)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 保存父窗口引用
        self.parent = parent
        
        # 配置文件路径 - 保存到用户目录而不是程序安装目录
        config_dir = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', '灵感录屏工具')
        if not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir)
            except:
                pass
        self.config_file = os.path.join(config_dir, 'config.json')
        
        self.dragging = False
        self.drag_position = QPoint()
        
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        central_widget.setStyleSheet(
            "background-color: #1a1a21; "
            "border-radius: 12px;"
        )
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(central_widget)
        
        content_layout = QVBoxLayout(central_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 标题栏
        title_bar = self.create_title_bar()
        content_layout.addWidget(title_bar)
        
        # 标题栏和滚动区域之间的分割线
        divider1 = QLabel()
        divider1.setFixedHeight(1)
        divider1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        divider1.setStyleSheet("border: none; background-color: #1c2129; margin: 0; padding: 0;")
        content_layout.addWidget(divider1)
        
        # 滚动内容区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background-color: #13131a; border-top-left-radius: 0px; border-top-right-radius: 0px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px")
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = self.create_content_area()
        scroll_area.setWidget(content_widget)
        content_layout.addWidget(scroll_area)
        
        # 滚动区域和底部栏之间的分割线
        divider2 = QLabel()
        divider2.setFixedHeight(1)
        divider2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        divider2.setStyleSheet("border: none; background-color: #1c2129; margin: 0; padding: 0;")
        content_layout.addWidget(divider2)
        
        # 底部按钮栏
        bottom_bar = self.create_bottom_bar()
        content_layout.addWidget(bottom_bar)
    
    def create_title_bar(self):
        """创建标题栏"""
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("background-color: #1a1a21; border-top-left-radius: 12px; border-top-right-radius: 12px;")
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)
        
        title_label = QLabel('设置')
        title_label.setStyleSheet("color: #FFFFFF; font-family: 'Microsoft YaHei'; font-size: 14px; font-weight: 500;")
        
        right_layout = QHBoxLayout()
        right_layout.setAlignment(Qt.AlignRight)
        
        close_button = QPushButton('×')
        close_button.setFixedSize(28, 28)
        close_button.setStyleSheet(
            "background-color: transparent; "
            "color: #9CA3AF; "
            "font-size: 18px; "
            "border: none;"
        )
        close_button.clicked.connect(self.close)
        
        def close_enter(event):
            close_button.setStyleSheet(
                "background-color: #EF4444; "
                "color: #FFFFFF; "
                "font-size: 18px; "
                "border-radius: 4px; "
                "border: none;"
            )
            event.accept()
        
        def close_leave(event):
            close_button.setStyleSheet(
                "background-color: transparent; "
                "color: #9CA3AF; "
                "font-size: 18px; "
                "border: none;"
            )
            event.accept()
        
        close_button.enterEvent = close_enter
        close_button.leaveEvent = close_leave
        
        right_layout.addWidget(close_button)
        
        title_layout.addWidget(title_label, 1)
        title_layout.addLayout(right_layout)
        
        title_bar.mousePressEvent = self.mouse_press_event
        title_bar.mouseMoveEvent = self.mouse_move_event
        title_bar.mouseReleaseEvent = self.mouse_release_event
        
        return title_bar
    
    def create_content_area(self):
        """创建内容区域"""
        container = QWidget()
        container.setStyleSheet("background-color: #13131a;")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # 1. 输出路径设置
        path_group = self.create_path_group()
        layout.addWidget(path_group)
        
        # 2. 视频设置
        video_group = self.create_video_group()
        layout.addWidget(video_group)
        
        # 3. 鼠标设置
        mouse_group = self.create_mouse_group()
        layout.addWidget(mouse_group)
        
        # 4. 录制行为设置
        recording_group = self.create_recording_group()
        layout.addWidget(recording_group)
        
        # 5. 快捷键设置
        hotkey_group = self.create_hotkey_group()
        layout.addWidget(hotkey_group)
        
        layout.addStretch()
        
        return container
    
    def create_path_group(self):
        """创建输出路径设置组"""
        group = QGroupBox('1. 输出路径设置')
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-family: 'Microsoft YaHei';
                font-size: 14px;
                font-weight: 500;
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        path_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d38;
                border: 1px solid #4B5563;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
        """)
        
        browse_button = QPushButton('浏览')
        browse_button.setFixedSize(80, 36)
        browse_button.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        browse_button.clicked.connect(self.browse_output_path)
        
        path_layout.addWidget(self.output_path_edit)
        path_layout.addWidget(browse_button)
        
        layout.addLayout(path_layout)
        group.setLayout(layout)
        
        return group
    
    def create_video_group(self):
        """创建视频设置组"""
        group = QGroupBox('2. 音视频输出设置')
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-family: 'Microsoft YaHei';
                font-size: 14px;
                font-weight: 500;
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
        """)
        
        layout = QFormLayout()
        layout.setSpacing(15)
        
        # 视频格式
        self.video_format_combo = QComboBox()
        self.video_format_combo.addItems(['MP4', 'AVI', 'MOV', 'MKV', 'FLV', 'WMV'])
        self.video_format_combo.setStyleSheet("""
            QComboBox {
                background-color: #2d2d38;
                border: 1px solid #4B5563;
                border-radius: 6px;
                color: #FFFFFF;
                padding: 8px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #FFFFFF;
                margin-right: 10px;
            }
        """)
        
        # 录制帧率 - 固定值选择
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(['20 FPS', '25 FPS', '30 FPS', '50 FPS', '60 FPS'])
        self.fps_combo.setCurrentText('30 FPS')
        self.fps_combo.setStyleSheet(self.video_format_combo.styleSheet())
        
        # 清晰度
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['原画质', '高质量', '中等质量', '低质量'])
        self.quality_combo.setStyleSheet(self.video_format_combo.styleSheet())
        
        # 音频质量
        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.addItems(['无损音质', '高音质', '中等音质', '低音质'])
        self.audio_quality_combo.setStyleSheet(self.video_format_combo.styleSheet())
        
        layout.addRow('视频格式：', self.video_format_combo)
        layout.addRow('录制帧率：', self.fps_combo)
        layout.addRow('清晰度：', self.quality_combo)
        layout.addRow('音频质量：', self.audio_quality_combo)
        
        group.setLayout(layout)
        return group
    
    def create_mouse_group(self):
        """创建鼠标设置组"""
        group = QGroupBox('3. 鼠标设置')
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-family: 'Microsoft YaHei';
                font-size: 14px;
                font-weight: 500;
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        self.show_cursor_check = QCheckBox('显示鼠标指针')
        self.record_mouse_region_check = QCheckBox('录制动态鼠标区域')
        
        for checkbox in [self.show_cursor_check, self.record_mouse_region_check]:
            checkbox.setStyleSheet("""
                QCheckBox {
                    color: #FFFFFF;
                    font-family: 'Microsoft YaHei';
                    font-size: 13px;
                }
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                    border: 2px solid #4B5563;
                    border-radius: 4px;
                    background-color: #2d2d38;
                }
                QCheckBox::indicator:checked {
                    background-color: #3B82F6;
                    border-color: #3B82F6;
                }
            """)
        
        layout.addWidget(self.show_cursor_check)
        layout.addWidget(self.record_mouse_region_check)
        group.setLayout(layout)
        
        return group
    
    def create_recording_group(self):
        """创建录制行为设置组"""
        group = QGroupBox('4. 录制行为设置')
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-family: 'Microsoft YaHei';
                font-size: 14px;
                font-weight: 500;
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        self.hide_main_window_check = QCheckBox('录制开始时隐藏主窗口')
        self.show_border_check = QCheckBox('显示录制区域边框')
        self.allow_click_region_check = QCheckBox('允许在录制过程中移动录制区域（自定义录制窗口大小时启用）')
        
        for checkbox in [self.hide_main_window_check, self.show_border_check, self.allow_click_region_check]:
            checkbox.setStyleSheet(self.show_cursor_check.styleSheet())
        
        layout.addWidget(self.hide_main_window_check)
        layout.addWidget(self.show_border_check)
        layout.addWidget(self.allow_click_region_check)
        group.setLayout(layout)
        
        return group
    
    def create_hotkey_group(self):
        """创建快捷键设置组"""
        group = QGroupBox('5. 自定义录制快捷键')
        group.setStyleSheet("""
            QGroupBox {
                color: #FFFFFF;
                font-family: 'Microsoft YaHei';
                font-size: 14px;
                font-weight: 500;
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
        """)
        
        layout = QFormLayout()
        layout.setSpacing(15)
        
        self.hotkey_start = QKeySequenceEdit()
        self.hotkey_stop = QKeySequenceEdit()
        self.hotkey_pause = QKeySequenceEdit()
        self.hotkey_toggle = QKeySequenceEdit()
        
        for edit in [self.hotkey_start, self.hotkey_stop, self.hotkey_pause, self.hotkey_toggle]:
            edit.setStyleSheet("""
                QKeySequenceEdit {
                    background-color: #2d2d38;
                    border: 1px solid #4B5563;
                    border-radius: 6px;
                    color: #FFFFFF;
                    padding: 8px;
                    font-family: 'Microsoft YaHei';
                    font-size: 13px;
                }
            """)
        
        layout.addRow('开始录制：', self.hotkey_start)
        layout.addRow('停止录制：', self.hotkey_stop)
        layout.addRow('暂停录制：', self.hotkey_pause)
        layout.addRow('显示/隐藏窗口：', self.hotkey_toggle)
        
        group.setLayout(layout)
        return group
    
    def create_bottom_bar(self):
        """创建底部按钮栏"""
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(70)
        bottom_bar.setStyleSheet("background-color: #13131a; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")
        
        layout = QHBoxLayout(bottom_bar)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)
        
        reset_button = QPushButton('恢复默认值')
        reset_button.setFixedSize(120, 40)
        reset_button.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #9CA3AF;
            }
        """)
        reset_button.clicked.connect(self.reset_defaults)
        
        save_button = QPushButton('保存设置')
        save_button.setFixedSize(120, 40)
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        save_button.clicked.connect(self.save_settings)
        
        layout.addWidget(reset_button)
        layout.addStretch()
        layout.addWidget(save_button)
        
        return bottom_bar
    
    def browse_output_path(self):
        """浏览输出路径"""
        path = QFileDialog.getExistingDirectory(self, '选择输出文件夹', self.output_path_edit.text())
        if path:
            self.output_path_edit.setText(path)
    
    def reset_defaults(self):
        """恢复默认值"""
        reply = CustomMessageBox.question(
            self, '确认', '确定要恢复所有默认设置吗？'
        )
        if reply:
            self.load_default_settings()
    
    def get_default_save_path(self):
        """智能获取默认保存路径，优先D盘，不存在时使用C盘"""
        # 优先使用D盘
        d_drive_path = r'D:\灵感录屏储存\recordings'
        c_drive_path = r'C:\灵感录屏储存\recordings'
        
        # 检测D盘是否真实存在且可访问
        d_drive_available = False
        try:
            # 尝试访问D盘根目录，如果成功说明D盘存在
            if os.path.isdir('D:\\'):
                # 尝试列举目录来确认可访问性
                os.listdir('D:\\')
                d_drive_available = True
        except (OSError, PermissionError):
            # D盘不存在或不可访问
            d_drive_available = False
        
        if d_drive_available:
            default_dir = d_drive_path
        else:
            print("DEBUG: 未检测到D盘或D盘不可访问，将使用C盘作为默认保存路径")
            default_dir = c_drive_path
        
        # 确保目录存在
        if not os.path.exists(default_dir):
            try:
                os.makedirs(default_dir)
                print(f"DEBUG: 自动创建默认保存目录: {default_dir}")
            except Exception as e:
                print(f"DEBUG: 创建默认目录失败: {e}")
                # 如果创建失败，尝试使用用户文档目录
                fallback_dir = os.path.join(os.path.expanduser('~'), 'Documents', '灵感录屏储存', 'recordings')
                try:
                    os.makedirs(fallback_dir, exist_ok=True)
                    print(f"DEBUG: 使用备用目录: {fallback_dir}")
                    default_dir = fallback_dir
                except Exception as e2:
                    print(f"DEBUG: 创建备用目录也失败: {e2}")
        
        return default_dir
    
    def load_default_settings(self):
        """加载默认设置"""
        default_dir = self.get_default_save_path()
        self.output_path_edit.setText(default_dir)
        self.video_format_combo.setCurrentText('MP4')
        self.fps_combo.setCurrentText('30 FPS')
        self.quality_combo.setCurrentText('高质量')
        self.audio_quality_combo.setCurrentText('高音质')  # 默认高音质
        self.show_cursor_check.setChecked(True)
        self.record_mouse_region_check.setChecked(False)
        self.hide_main_window_check.setChecked(False)
        self.show_border_check.setChecked(True)
        self.allow_click_region_check.setChecked(False)
        self.hotkey_start.setKeySequence(QKeySequence('F9'))
        self.hotkey_stop.setKeySequence(QKeySequence('F10'))
        self.hotkey_pause.setKeySequence(QKeySequence('F11'))
        self.hotkey_toggle.setKeySequence(QKeySequence('Ctrl+F12'))
    
    def load_settings(self):
        """加载设置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # 获取保存的路径，如果没有则使用智能默认路径
                saved_path = settings.get('output_path', '')
                if saved_path:
                    # 检查保存的路径是否在D盘且D盘不存在/不可访问
                    if saved_path.startswith('D:\\'):
                        d_drive_available = False
                        try:
                            if os.path.isdir('D:\\'):
                                os.listdir('D:\\')
                                d_drive_available = True
                        except (OSError, PermissionError):
                            d_drive_available = False
                        
                        if not d_drive_available:
                            print(f"DEBUG: 保存的路径在D盘但D盘不存在或不可访问，切换到C盘")
                            # 将D盘路径转换为C盘路径
                            saved_path = saved_path.replace('D:\\', 'C:\\', 1)
                    output_path = saved_path
                else:
                    output_path = self.get_default_save_path()
                
                self.output_path_edit.setText(output_path)
                
                # 确保设置的路径存在
                if output_path and not os.path.exists(output_path):
                    try:
                        os.makedirs(output_path)
                        print(f"DEBUG: 自动创建设置的保存目录: {output_path}")
                    except Exception as e:
                        print(f"DEBUG: 创建设置目录失败: {e}")
                        # 如果创建失败，使用智能默认路径
                        fallback_path = self.get_default_save_path()
                        self.output_path_edit.setText(fallback_path)
                self.video_format_combo.setCurrentText(settings.get('video_format', 'MP4'))
                
                # 加载帧率设置，从数值转换为选项文本
                fps_value = settings.get('fps', 30)
                fps_text = f'{fps_value} FPS'
                if fps_text in ['20 FPS', '25 FPS', '30 FPS', '50 FPS', '60 FPS']:
                    self.fps_combo.setCurrentText(fps_text)
                else:
                    self.fps_combo.setCurrentText('30 FPS')  # 默认值
                
                self.quality_combo.setCurrentText(settings.get('quality', '高质量'))
                # 加载音频质量设置
                self.audio_quality_combo.setCurrentText(settings.get('audio_quality', '高音质'))
                
                self.show_cursor_check.setChecked(settings.get('show_cursor', True))
                self.record_mouse_region_check.setChecked(settings.get('record_mouse_region', False))
                self.hide_main_window_check.setChecked(settings.get('hide_main_window', False))
                self.show_border_check.setChecked(settings.get('show_border', True))
                self.allow_click_region_check.setChecked(settings.get('allow_click_region', False))
                
                if 'hotkey_start' in settings:
                    self.hotkey_start.setKeySequence(QKeySequence(settings['hotkey_start']))
                if 'hotkey_stop' in settings:
                    self.hotkey_stop.setKeySequence(QKeySequence(settings['hotkey_stop']))
                if 'hotkey_pause' in settings:
                    self.hotkey_pause.setKeySequence(QKeySequence(settings['hotkey_pause']))
                if 'hotkey_toggle' in settings:
                    toggle_key = settings['hotkey_toggle']
                    # 兼容旧配置：如果还是F12，自动升级为Ctrl+F12
                    if toggle_key == 'F12':
                        toggle_key = 'Ctrl+F12'
                    self.hotkey_toggle.setKeySequence(QKeySequence(toggle_key))
            except:
                self.load_default_settings()
        else:
            self.load_default_settings()
    
    def save_settings(self):
        """保存设置"""
        # 从帧率选项文本中提取数值
        fps_text = self.fps_combo.currentText()
        fps_value = int(fps_text.replace(' FPS', ''))
        
        # 获取输出路径并确保存在
        output_path = self.output_path_edit.text()
        if output_path and not os.path.exists(output_path):
            try:
                os.makedirs(output_path)
                print(f"DEBUG: 保存设置时自动创建目录: {output_path}")
            except Exception as e:
                print(f"DEBUG: 创建输出目录失败: {e}")
                CustomMessageBox.show_message(self, '警告', f'无法创建输出目录：{str(e)}\n请选择其他目录或手动创建。', 'warning')
                return
        
        settings = {
            'output_path': output_path,
            'video_format': self.video_format_combo.currentText(),
            'fps': fps_value,
            'quality': self.quality_combo.currentText(),
            'audio_quality': self.audio_quality_combo.currentText(),  # 保存音频质量设置
            'show_cursor': self.show_cursor_check.isChecked(),
            'record_mouse_region': self.record_mouse_region_check.isChecked(),
            'hide_main_window': self.hide_main_window_check.isChecked(),
            'show_border': self.show_border_check.isChecked(),
            'allow_click_region': self.allow_click_region_check.isChecked(),
            'hotkey_start': self.hotkey_start.keySequence().toString(),
            'hotkey_stop': self.hotkey_stop.keySequence().toString(),
            'hotkey_pause': self.hotkey_pause.keySequence().toString(),
            'hotkey_toggle': self.hotkey_toggle.keySequence().toString(),
        }
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            
            # 通知主窗口重新注册快捷键
            if hasattr(self, 'parent') and self.parent:
                if hasattr(self.parent, 'register_global_hotkeys'):
                    self.parent.register_global_hotkeys()
            
            CustomMessageBox.show_message(self, '成功', '设置已保存！', 'information')
            self.close()
        except Exception as e:
            CustomMessageBox.show_message(self, '错误', f'保存设置失败：{str(e)}', 'critical')
    
    def mouse_press_event(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouse_move_event(self, event):
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouse_release_event(self, event):
        self.dragging = False
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.transparent)
        painter.drawRect(self.rect())


class TruePixelPerfectUI(QMainWindow):
    def __init__(self, splash=None):
        super().__init__()
        
        # 保存启动窗口引用
        self.splash = splash
        
        # 更新启动信息
        if self.splash:
            self.splash.update_info('正在初始化界面...')
            QApplication.processEvents()
        
        # 精确设置窗口标题和固定尺寸 - 严格按照HTML中的1000x298px
        self.setWindowTitle('灵感录屏工具')
        self.setFixedSize(1000, 298)
        
        # 设置窗口图标
        if os.path.exists('iconic/logo.ico'):
            self.setWindowIcon(QIcon('iconic/logo.ico'))
        
        # 设置无边框窗口
        self.setWindowFlags(Qt.FramelessWindowHint)
        # 设置窗口背景透明，以便显示圆角
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 更新启动信息
        if self.splash:
            self.splash.update_info('正在创建界面组件...')
            QApplication.processEvents()
        
        # 创建中央部件
        central_widget = QWidget()
        central_widget.setStyleSheet(
            "background-color: transparent; "
            "border-top-left-radius: 12px; "
            "border-top-right-radius: 12px; "
            "border-bottom-left-radius: 12px; "
            "border-bottom-right-radius: 12px; "
            "padding: 0px;"
        )
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 设备下拉菜单引用（在创建UI之前初始化，避免覆盖UI创建时保存的引用）
        self.camera_combo = None
        self.microphone_combo = None
        self.audio_combo = None
        
        # 更新启动信息
        if self.splash:
            self.splash.update_info('正在加载标题栏...')
            QApplication.processEvents()
        
        # 1. 创建顶部标题栏 (精确40px高度)
        title_bar = self.create_title_bar()
        main_layout.addWidget(title_bar)
        
        # 标题栏和功能区之间的分割线
        divider1 = QLabel()
        divider1.setFixedHeight(1)
        divider1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        divider1.setStyleSheet("border: none; background-color: #1c2129; margin: 0; padding: 0;")
        main_layout.addWidget(divider1)
        
        # 更新启动信息
        if self.splash:
            self.splash.update_info('正在加载功能区...')
            QApplication.processEvents()
        
        # 2. 创建中间功能区 (精确218px高度)
        main_content = self.create_main_content()
        main_layout.addWidget(main_content)
        
        # 功能区和底部选项栏之间的分割线
        divider2 = QLabel()
        divider2.setFixedHeight(1)
        divider2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        divider2.setStyleSheet("border: none; background-color: #1c2129; margin: 0; padding: 0;")
        main_layout.addWidget(divider2)
        
        # 更新启动信息
        if self.splash:
            self.splash.update_info('正在加载选项栏...')
            QApplication.processEvents()
        
        # 3. 创建底部选项栏 (精确40px高度)
        bottom_bar = self.create_bottom_bar()
        main_layout.addWidget(bottom_bar)
        
        # 窗口拖动功能
        self.dragging = False
        self.drag_position = QPoint()
        
        # 录制相关变量
        self.recording = False
        self.paused = False
        self.start_time = 0
        self.elapsed_time = 0
        self.timer = None
        # status_label 在 create_bottom_bar() 中创建，不要在这里设置为 None
        
        # 区域更新防抖定时器（避免频繁更新录制区域）
        self.region_update_timer = QTimer()
        self.region_update_timer.setSingleShot(True)
        self.region_update_timer.timeout.connect(self._apply_pending_region_update)
        self.pending_region_update = None  # 待更新的区域
        self.last_recording_region = None  # 上次的录制区域，用于判断是否只是位置改变
        
        # 文件列表窗口
        self.file_list_window = None
        
        # 设置窗口和关于窗口
        self.settings_window = None
        self.about_window = None
        
        # 摄像头预览窗口
        self.camera_preview_window = None
        self._camera_icon_widget = None  # 保存摄像头图标的引用（使用私有变量）
        self.under_development_window = None
        self.camera_device_index_map = {}  # 摄像头设备名称到索引的映射
        
        # 麦克风状态
        self.microphone_icon_widget = None  # 保存麦克风图标的引用
        self.microphone_enabled = False  # 麦克风启用状态（默认禁用）
        
        # 音频（扬声器）状态
        self.audio_icon_widget = None  # 保存音频图标的引用
        self.audio_enabled = True  # 音频启用状态（默认启用）
        
        # 录屏相关变量
        self.recording_thread = None  # 录屏线程
        self.recording_mode = 'fullscreen'  # 录制模式：'fullscreen'、'custom' 或 'window'
        self.custom_region = None  # 自定义录制区域 (x, y, width, height)
        
        # 窗口录制相关变量
        self.selected_window_handle = None  # 选中的窗口句柄
        self.window_follow_timer = None  # 窗口跟随定时器
        self.window_list_menu = None  # 窗口列表菜单
        
        # 更新启动信息
        if self.splash:
            self.splash.update_info('正在初始化录制设置...')
            QApplication.processEvents()
        
        self.recordings_dir = self._get_default_recordings_dir()  # 录制文件保存目录（智能检测D盘或C盘）
        if not os.path.exists(self.recordings_dir):
            try:
                os.makedirs(self.recordings_dir)
                print(f"DEBUG: 主窗口初始化时自动创建目录: {self.recordings_dir}")
            except Exception as e:
                print(f"DEBUG: 创建录制目录失败: {e}")
        self.current_recording_filepath = None  # 当前录制文件路径
        self.recording_fps = 30  # 默认帧率
        
        # 全局快捷键相关变量
        self.hotkey_listener = None  # 快捷键监听器
        self.hotkey_handlers = {}  # 快捷键处理函数字典
        
        # 更新启动信息
        if self.splash:
            self.splash.update_info('正在完成初始化...')
            QApplication.processEvents()
            time.sleep(0.2)  # 短暂延迟，让用户看到完成状态
        
        # 注册全局快捷键
        self.register_global_hotkeys()
    
    def paintEvent(self, event):
        # 确保圆角正确绘制
        from PyQt5.QtGui import QPainter, QColor
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 设置窗口区域为透明，让中央部件的圆角显示出来
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawRect(self.rect())
    
    def detect_cameras(self):
        """检测摄像头设备 - 获取真实的设备名称并建立索引映射"""
        cameras = []
        device_names_list = []
        self.camera_device_index_map = {}  # 清空旧映射
        
        # 在Windows上首先使用系统命令获取摄像头设备名称
        if sys.platform == 'win32':
            try:
                import subprocess
                # 使用PowerShell获取摄像头设备列表
                # 使用不同的方法来避免语法问题
                ps_script = '''
$devices = Get-PnpDevice -Class Camera | Where-Object {$_.Status -eq 'OK'}
foreach ($device in $devices) {
    $device.FriendlyName
}
'''
                result = subprocess.run(
                    ['powershell', '-Command', ps_script],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    encoding='utf-8',
                    errors='ignore',
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                
                if result.returncode == 0 and result.stdout:
                    device_names_list = [name.strip() for name in result.stdout.strip().split('\n') if name.strip()]
            except Exception as e:
                # 如果PowerShell方法失败，继续尝试其他方法
                pass
        
        # 如果PowerShell获取到了设备名称，需要建立名称到索引的映射
        if device_names_list and HAS_CV2:
            # 设置OpenCV日志级别，抑制警告信息
            try:
                cv2.setLogLevel(cv2.LOG_LEVEL_SILENT)
            except:
                pass
            
            import contextlib
            import os
            
            @contextlib.contextmanager
            def suppress_stderr():
                with open(os.devnull, 'w') as devnull:
                    original_stderr = sys.stderr
                    original_stdout = sys.stdout
                    try:
                        sys.stderr = devnull
                        sys.stdout = devnull
                        yield
                    finally:
                        sys.stderr = original_stderr
                        sys.stdout = original_stdout
            
            # 检测每个设备的索引
            try:
                with suppress_stderr():
                    valid_index = 0
                    for i in range(10):  # 检测更多索引
                        cap = None
                        try:
                            cap = cv2.VideoCapture(i)
                            if cap is not None and cap.isOpened():
                                width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                                height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                                if width > 0 and height > 0:
                                    # 这是一个有效的摄像头索引
                                    if valid_index < len(device_names_list):
                                        device_name = device_names_list[valid_index]
                                        cameras.append(device_name)
                                        self.camera_device_index_map[device_name] = i
                                        print(f"DEBUG: 映射摄像头 '{device_name}' -> 索引 {i}")
                                        valid_index += 1
                        except:
                            pass
                        finally:
                            if cap is not None:
                                try:
                                    cap.release()
                                except:
                                    pass
            except:
                pass
            
            # 恢复OpenCV日志级别
            try:
                cv2.setLogLevel(cv2.LOG_LEVEL_WARNING)
            except:
                pass
            
            # 如果没有成功映射任何设备，使用默认索引
            if not cameras and device_names_list:
                for idx, name in enumerate(device_names_list):
                    cameras.append(name)
                    self.camera_device_index_map[name] = idx
                    print(f"DEBUG: 使用默认映射 '{name}' -> 索引 {idx}")
        elif HAS_CV2:
            # 如果PowerShell方法失败，使用OpenCV作为备选方案
            # 设置OpenCV日志级别，抑制警告信息
            try:
                cv2.setLogLevel(cv2.LOG_LEVEL_SILENT)
            except:
                pass
            
            import contextlib
            import os
            
            @contextlib.contextmanager
            def suppress_stderr():
                with open(os.devnull, 'w') as devnull:
                    original_stderr = sys.stderr
                    original_stdout = sys.stdout
                    try:
                        sys.stderr = devnull
                        sys.stdout = devnull
                        yield
                    finally:
                        sys.stderr = original_stderr
                        sys.stdout = original_stdout
            
            # 使用OpenCV检测摄像头索引（备选方案）
            try:
                with suppress_stderr():
                    for i in range(5):  # 检测最夔5个摄像头索引
                        cap = None
                        try:
                            cap = cv2.VideoCapture(i)
                            if cap is not None and cap.isOpened():
                                # 检查摄像头是否真正可用（不读取帧，只检查属性）
                                width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                                height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                                # 如果能够获取分辨率，说明摄像头可用
                                if width > 0 and height > 0:
                                    device_name = f'摄像头 {i}'
                                    cameras.append(device_name)
                                    self.camera_device_index_map[device_name] = i
                        except:
                            pass
                        finally:
                            if cap is not None:
                                try:
                                    cap.release()
                                except:
                                    pass
            except:
                pass
            
            # 恢复OpenCV日志级别
            try:
                cv2.setLogLevel(cv2.LOG_LEVEL_WARNING)
            except:
                pass
        
        return cameras
    
    def detect_microphones(self):
        """检测麦克风设备（音频输入设备）"""
        microphones = []
        if sys.platform == 'win32':
            # 首先尝试使用pycaw库（如果已安装）
            try:
                from pycaw.pycaw import AudioUtilities
                devices = AudioUtilities.GetAllDevices()
                for device in devices:
                    if device.DataFlow == 1:  # 1 = eCapture (输入设备)
                        device_name = device.FriendlyName
                        if device_name and device_name not in microphones:
                            microphones.append(device_name)
            except:
                pass
            
            # 如果pycaw不可用或没有检测到设备，使用Windows系统命令检测
            if not microphones:
                try:
                    import subprocess
                    # 使用Get-PnpDevice检测音频输入设备
                    # 通过实例ID来准确区分输入和输出设备
                    # 输入设备的实例ID包含 {0.0.1.}，输出设备包含 {0.0.0.}
                    ps_command = '''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$devices = Get-PnpDevice -Class AudioEndpoint | Where-Object {$_.Status -eq 'OK'}
foreach ($device in $devices) {
    $friendlyName = $device.FriendlyName
    $instanceId = $device.InstanceId
    if ($friendlyName -and $instanceId) {
        # 通过实例ID判断：输入设备的实例ID包含 {0.0.1.
        if ($instanceId -match '\\\\{0\\.0\\.1\\.') {
            [Console]::WriteLine($friendlyName)
        }
    }
}
'''
                    # 尝试不同的PowerShell路径
                    powershell_paths = [
                        'powershell.exe',
                        r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
                    ]
                    
                    result = None
                    for ps_path in powershell_paths:
                        try:
                            result = subprocess.run(
                                [ps_path, '-NoProfile', '-Command', ps_command],
                                capture_output=True,
                                text=True,
                                timeout=10,
                                encoding='utf-8',
                                errors='ignore',
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                            )
                            if result and result.returncode == 0 and result.stdout:
                                break
                        except (FileNotFoundError, Exception):
                            continue
                    
                    if result and result.returncode == 0 and result.stdout:
                        devices = [d.strip() for d in result.stdout.strip().split('\n') if d.strip()]
                        # 去重
                        seen = set()
                        for device in devices:
                            if device and device not in seen:
                                microphones.append(device)
                                seen.add(device)
                except Exception as e:
                    print(f"DEBUG: Error detecting microphones: {e}")
                    pass
        return microphones
    
    def _get_ffmpeg_dshow_audio_device(self, system_device_name):
        """获取FFmpeg可用的dshow音频设备名称（通过匹配系统设备名称）"""
        if not system_device_name:
            return None
        
        try:
            import subprocess
            # 使用FFmpeg列出所有dshow音频设备
            test_cmd = ['ffmpeg', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy']
            test_result = subprocess.run(
                test_cmd,
                capture_output=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            test_output = test_result.stderr.decode('utf-8', errors='ignore')
            
            # 查找音频设备列表
            # FFmpeg输出格式示例：
            # [dshow @ 0x...] "Microphone (Realtek Audio)" (audio)
            audio_devices = []
            capturing_audio = False
            for line in test_output.split('\n'):
                line_lower = line.lower()
                if 'audio' in line_lower and 'dshow' in line_lower:
                    capturing_audio = True
                if capturing_audio and '"' in line:
                    # 提取设备名称（在引号中）
                    start = line.find('"')
                    end = line.rfind('"')
                    if start >= 0 and end > start:
                        device_name = line[start+1:end]
                        # 移除可能的 "(audio)" 后缀
                        if ' (audio)' in device_name:
                            device_name = device_name.replace(' (audio)', '')
                        if device_name and device_name not in audio_devices:
                            audio_devices.append(device_name)
            
            print(f"DEBUG: FFmpeg检测到的dshow音频设备: {audio_devices}")
            print(f"DEBUG: 系统设备名称: {system_device_name}")
            
            # 尝试精确匹配
            for device in audio_devices:
                if device == system_device_name:
                    print(f"DEBUG: 精确匹配到设备: {device}")
                    return device
            
            # 尝试部分匹配（移除括号内容后匹配）
            system_name_clean = system_device_name.split(' (')[0].strip()
            for device in audio_devices:
                device_clean = device.split(' (')[0].strip()
                if device_clean == system_name_clean:
                    print(f"DEBUG: 部分匹配到设备: {device} (系统名称: {system_device_name})")
                    return device
            
            # 尝试包含匹配
            for device in audio_devices:
                if system_device_name.lower() in device.lower() or device.lower() in system_device_name.lower():
                    print(f"DEBUG: 包含匹配到设备: {device} (系统名称: {system_device_name})")
                    return device
            
            # 如果都匹配不上，返回第一个可用的设备（作为备选）
            if audio_devices:
                print(f"DEBUG: 无法匹配设备，使用第一个可用设备: {audio_devices[0]}")
                return audio_devices[0]
            
            print(f"DEBUG: 未找到FFmpeg可用的音频设备")
            return None
        except Exception as e:
            print(f"DEBUG: 获取FFmpeg dshow音频设备失败: {e}")
            return None
    
    def detect_audio_outputs(self):
        """检测音频输出设备（扬声器）"""
        outputs = []
        if sys.platform == 'win32':
            # 首先尝试使用pycaw库（如果已安装）
            try:
                from pycaw.pycaw import AudioUtilities
                devices = AudioUtilities.GetAllDevices()
                for device in devices:
                    if device.DataFlow == 0:  # 0 = eRender (输出设备)
                        device_name = device.FriendlyName
                        if device_name and device_name not in outputs:
                            outputs.append(device_name)
            except:
                pass
            
            # 如果pycaw不可用或没有检测到设备，使用Windows系统命令检测
            if not outputs:
                try:
                    import subprocess
                    # 使用Get-PnpDevice检测音频输出设备
                    # 通过实例ID来准确区分输入和输出设备
                    # 输出设备的实例ID包含 {0.0.0.}，输入设备包含 {0.0.1.}
                    ps_command = '''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$devices = Get-PnpDevice -Class AudioEndpoint | Where-Object {$_.Status -eq 'OK'}
foreach ($device in $devices) {
    $friendlyName = $device.FriendlyName
    $instanceId = $device.InstanceId
    if ($friendlyName -and $instanceId) {
        # 通过实例ID判断：输出设备的实例ID包含 {0.0.0.
        if ($instanceId -match '\\\\{0\\.0\\.0\\.') {
            [Console]::WriteLine($friendlyName)
        }
    }
}
'''
                    # 尝试不同的PowerShell路径
                    powershell_paths = [
                        'powershell.exe',
                        r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
                    ]
                    
                    result = None
                    for ps_path in powershell_paths:
                        try:
                            result = subprocess.run(
                                [ps_path, '-NoProfile', '-Command', ps_command],
                                capture_output=True,
                                text=True,
                                timeout=10,
                                encoding='utf-8',
                                errors='ignore',
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                            )
                            if result and result.returncode == 0 and result.stdout:
                                break
                        except (FileNotFoundError, Exception):
                            continue
                    
                    if result and result.returncode == 0 and result.stdout:
                        devices = [d.strip() for d in result.stdout.strip().split('\n') if d.strip()]
                        # 去重
                        seen = set()
                        for device in devices:
                            if device and device not in seen:
                                outputs.append(device)
                                seen.add(device)
                except Exception as e:
                    print(f"DEBUG: Error detecting audio outputs: {e}")
                    pass
        return outputs
    
    def _get_default_recordings_dir(self):
        """智能获取默认录制目录，优先D盘，不存在时使用C盘"""
        # 优先使用D盘
        d_drive_path = r'D:\灵感录屏储存\recordings'
        c_drive_path = r'C:\灵感录屏储存\recordings'
        
        # 检测D盘是否真实存在且可访问
        d_drive_available = False
        try:
            # 尝试访问D盘根目录，如果成功说明D盘存在
            if os.path.isdir('D:\\'):
                # 尝试列举目录来确认可访问性
                os.listdir('D:\\')
                d_drive_available = True
        except (OSError, PermissionError):
            # D盘不存在或不可访问
            d_drive_available = False
        
        if d_drive_available:
            default_dir = d_drive_path
        else:
            print("DEBUG: 未检测到D盘或D盘不可访问，将使用C盘作为默认保存路径")
            default_dir = c_drive_path
        
        return default_dir
    
    def create_title_bar(self):
        # 创建顶部标题栏，精确高度40px (h-10 = 40px)
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        # 上段区域：保留左上角和右上角圆角，左下角和右下角改为方角
        title_bar.setStyleSheet(
            "background-color: #1a1a21; "
            "border-top-left-radius: 12px; "
            "border-top-right-radius: 12px; "
            "border-bottom-left-radius: 0px; "
            "border-bottom-right-radius: 0px;"
        )
        
        # 创建标题栏布局
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)  # px-4 = 16px
        title_layout.setSpacing(8)  # space-x-2 = 8px
        
        # 左侧标题区域
        left_layout = QHBoxLayout()
        left_layout.setAlignment(Qt.AlignLeft)
        left_layout.setSpacing(8)  # space-x-2 = 8px
        
        # 应用图标 (20x20)
        icon_widget = QLabel()
        icon_widget.setFixedSize(20, 20)
        if os.path.exists('iconic/logo.ico'):
            icon_pixmap = QPixmap('iconic/logo.ico')
            scaled_icon = icon_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_widget.setPixmap(scaled_icon)
        else:
            icon_widget.setStyleSheet("background-color: #3B82F6; border-radius: 4px;")
        
        # 应用标题
        title_label = QLabel('灵感录屏工具')
        title_label.setStyleSheet("color: #FFFFFF; font-family: 'Microsoft YaHei'; font-size: 14px; font-weight: 500;")
        
        left_layout.addWidget(icon_widget)
        left_layout.addWidget(title_label)
        
        # 右侧控制按钮区域
        right_layout = QHBoxLayout()
        right_layout.setAlignment(Qt.AlignRight)
        right_layout.setSpacing(12)  # space-x-3 = 12px
        
        # 菜单按钮 - 使用三横线表示
        menu_button = QPushButton('≡')
        menu_button.setFixedSize(28, 28)
        menu_button.setStyleSheet(
            "background-color: transparent; "
            "color: #9CA3AF; "
            "font-size: 16px; "
            "border: none;"
        )
        
        # 最小化按钮 - 使用短横线表示
        minimize_button = QPushButton('-')
        minimize_button.setFixedSize(28, 28)
        minimize_button.setStyleSheet(
            "background-color: transparent; "
            "color: #9CA3AF; "
            "font-size: 18px; "
            "border: none;"
        )
        minimize_button.clicked.connect(self.showMinimized)
        
        # 关闭按钮 - 使用叉号表示
        close_button = QPushButton('×')
        close_button.setFixedSize(28, 28)
        close_button.setStyleSheet(
            "background-color: transparent; "
            "color: #9CA3AF; "
            "font-size: 18px; "
            "border: none;"
        )
        close_button.clicked.connect(self.close)
        
        # 添加悬停效果
        menu_button.enterEvent = lambda e: menu_button.setStyleSheet(
            "background-color: #374151; "
            "color: #FFFFFF; "
            "font-size: 16px; "
            "border-radius: 4px; "
            "border: none;"
        )
        menu_button.leaveEvent = lambda e: menu_button.setStyleSheet(
            "background-color: transparent; "
            "color: #9CA3AF; "
            "font-size: 16px; "
            "border: none;"
        )
        
        minimize_button.enterEvent = lambda e: minimize_button.setStyleSheet(
            "background-color: #374151; "
            "color: #FFFFFF; "
            "font-size: 18px; "
            "border-radius: 4px; "
            "border: none;"
        )
        minimize_button.leaveEvent = lambda e: minimize_button.setStyleSheet(
            "background-color: transparent; "
            "color: #9CA3AF; "
            "font-size: 18px; "
            "border: none;"
        )
        
        close_button.enterEvent = lambda e: close_button.setStyleSheet(
            "background-color: #EF4444; "
            "color: #FFFFFF; "
            "font-size: 18px; "
            "border-radius: 4px; "
            "border: none;"
        )
        close_button.leaveEvent = lambda e: close_button.setStyleSheet(
            "background-color: transparent; "
            "color: #9CA3AF; "
            "font-size: 18px; "
            "border: none;"
        )
        
        # 为菜单按钮添加点击事件
        menu_button.clicked.connect(self.show_menu)
        right_layout.addWidget(menu_button)
        
        # 添加分割符 - 菜单按钮和最小化按钮之间
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setFixedSize(1, 20)  # 1px宽度，20px高度
        separator.setStyleSheet("background-color: #374151;")  # 使用灰色，与主题一致
        right_layout.addWidget(separator)
        
        right_layout.addWidget(minimize_button)
        right_layout.addWidget(close_button)
        
        # 添加到主标题栏布局
        title_layout.addLayout(left_layout, 1)
        title_layout.addLayout(right_layout)
        
        # 添加鼠标拖动事件
        title_bar.mousePressEvent = self.mouse_press_event
        title_bar.mouseMoveEvent = self.mouse_move_event
        title_bar.mouseReleaseEvent = self.mouse_release_event
        
        return title_bar
    
    def create_main_content(self):
        # 创建中间功能区，精确布局
        main_content = QWidget()
        main_content.setFixedHeight(218)  # 298 - 40 - 40 = 218
        # 中段区域：全部改为方角
        main_content.setStyleSheet(
            "background-color: #13131a; "
            "border-top-left-radius: 0px; "
            "border-top-right-radius: 0px; "
            "border-bottom-left-radius: 0px; "
            "border-bottom-right-radius: 0px;"
        )
        
        # 创建主内容布局
        main_layout = QHBoxLayout(main_content)
        main_layout.setContentsMargins(24, 16, 24, 16)  # px-6 py-4 = 24px 16px
        main_layout.setSpacing(24)  # 增加水平间距以改善布局
        
        # 1. 左侧区域选择 - 使用QWidget包装以确保水平对齐
        left_section_widget = QWidget()
        left_section = QHBoxLayout(left_section_widget)
        left_section.setAlignment(Qt.AlignVCenter)  # 垂直居中对齐
        left_section.setSpacing(16)  # space-x-4 = 16px
        
        # 全屏区域选择卡片
        full_screen_group = QWidget()
        full_screen_vlayout = QVBoxLayout(full_screen_group)
        full_screen_vlayout.setAlignment(Qt.AlignCenter)
        full_screen_vlayout.setSpacing(8)  # mt-2 = 8px
        
        # 修改为按钮并添加图片
        full_screen_card = QPushButton()
        self.fullscreen_button = full_screen_card  # 保存为实例变量以便检查状态
        full_screen_card.setFixedSize(112, 112)  # w-28 h-28 = 112x112px
        
        # 尝试加载图片并添加圆角效果
        try:
            from PyQt5.QtGui import QIcon
            from PyQt5.QtCore import QSize
            # 加载图片并添加圆角
            rounded_pixmap = self.make_rounded_pixmap('iconic/1.png', 8)  # 8px圆角
            full_screen_icon = QIcon(rounded_pixmap)
            full_screen_card.setIcon(full_screen_icon)
            full_screen_card.setIconSize(QSize(104, 104))  # 增大图标尺寸，只留2px边框空间
        except Exception as e:
            # 加载失败时保持原样
            pass
        
        # 设置全屏按钮的默认样式（移除固定橘色描边）
        full_screen_card.setStyleSheet(
            "background-color: #2d2d38; "
            "border: 2px solid #4B5563; "  # 设置为灰色边框，与其他按钮保持一致
            "border-radius: 8px; "
            "text-align: center;"
        )
        full_screen_card.is_selected = False  # 初始化选中状态
        
        # 添加全屏按钮悬停效果，与自定义按钮保持一致
        full_screen_card.enterEvent = lambda e: full_screen_card.setStyleSheet(
            "background-color: #2d2d38; "
            "border: 2px solid #ff3a3a; "  # 悬停时变为红色边框
            "border-radius: 8px; "
            "text-align: center;"
        )
        full_screen_card.leaveEvent = lambda e: (
            # 如果按钮未选中，则恢复默认样式；如果已选中，保持选中样式
            full_screen_card.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 2px solid #4B5563; "
                "border-radius: 8px; "
                "text-align: center;"
            ) if not hasattr(full_screen_card, 'is_selected') or not full_screen_card.is_selected else None
        )
        
        # 全屏按钮选择动态效果
        def on_fullscreen_clicked():
            # 设置录制模式为全屏
            self.recording_mode = 'fullscreen'
            # 设置当前按钮为选中状态
            self.apply_button_selected_style(full_screen_card)
            full_screen_card.is_selected = True
            # 取消自定义按钮的选中状态
            custom_card.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 2px solid #4B5563; "
                "border-radius: 8px; "
                "text-align: center;"
            )
            custom_card.is_selected = False
            # 更新状态栏 - 显示全屏模式
            if hasattr(self, 'status_label') and self.status_label:
                if not (hasattr(self, 'recording') and self.recording):
                    self.status_label.setText('当前为全屏录制模式 | 就绪')
                    self.status_label.setStyleSheet(
                        "color: #D1D5DB; "
                        "font-family: 'Microsoft YaHei'; "
                        "font-size: 13px; "
                        "background-color: transparent;"
                    )
                    print(f"DEBUG: 状态栏已更新为全屏模式")
            else:
                print(f"DEBUG: 状态栏不存在，hasattr: {hasattr(self, 'status_label')}, status_label: {getattr(self, 'status_label', 'N/A')}")
            # 取消更多按钮的选中状态
            more_button.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 2px solid #4B5563; "
                "border-radius: 8px; "
                "text-align: center;"
            )
            more_button.is_selected = False
        
        full_screen_card.clicked.connect(on_fullscreen_clicked)
        
        full_screen_label = QLabel('全屏')
        full_screen_label.setStyleSheet("color: #FFFFFF; font-family: 'Microsoft YaHei'; font-size: 14px;")
        full_screen_label.setAlignment(Qt.AlignCenter)
        
        full_screen_vlayout.addWidget(full_screen_card)
        full_screen_vlayout.addWidget(full_screen_label)
        
        # 自定义区域选择卡片
        custom_group = QWidget()
        custom_vlayout = QVBoxLayout(custom_group)
        custom_vlayout.setAlignment(Qt.AlignCenter)
        custom_vlayout.setSpacing(8)  # mt-2 = 8px
        
        # 修改为按钮并添加图片
        custom_card = QPushButton()
        self.custom_button = custom_card  # 保存为实例变量以便检查状态
        custom_card.setFixedSize(112, 112)  # w-28 h-28 = 112x112px
        
        # 尝试加载图片并添加圆角效果
        try:
            from PyQt5.QtGui import QIcon
            from PyQt5.QtCore import QSize
            # 加载图片并添加圆角
            rounded_pixmap = self.make_rounded_pixmap('iconic/2.png', 8)  # 8px圆角
            custom_icon = QIcon(rounded_pixmap)
            custom_card.setIcon(custom_icon)
            custom_card.setIconSize(QSize(104, 104))  # 增大图标尺寸，只留2px边框空间
        except Exception as e:
            # 加载失败时保持原样
            pass
            
        # 设置自定义按钮的默认样式
        custom_card.setStyleSheet(
            "background-color: #2d2d38; "
            "border: 2px solid #4B5563; "  # 设置2像素描边
            "border-radius: 8px; "
            "text-align: center;"
        )
        custom_card.is_selected = False  # 初始化选中状态
        
        custom_label = QLabel('自定义')
        custom_label.setStyleSheet("color: #FFFFFF; font-family: 'Microsoft YaHei'; font-size: 14px;")
        custom_label.setAlignment(Qt.AlignCenter)
        
        custom_vlayout.addWidget(custom_card)
        custom_vlayout.addWidget(custom_label)
        
        # 添加悬停效果
        custom_card.enterEvent = lambda e: custom_card.setStyleSheet(
            "background-color: #2d2d38; "
            "border: 2px solid #ff3a3a; "  # 悬停时变为红色边框
            "border-radius: 8px; "
            "text-align: center;"
        )
        custom_card.leaveEvent = lambda e: (
            # 如果按钮未选中，则恢复默认样式；如果已选中，保持选中样式
            custom_card.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 2px solid #4B5563; "
                "border-radius: 8px; "
                "text-align: center;"
            ) if not hasattr(custom_card, 'is_selected') or not custom_card.is_selected else None
        )
        
        # 自定义按钮选择动态效果
        def on_custom_clicked():
            # 设置录制模式为自定义
            self.recording_mode = 'custom'
            # 设置当前按钮为选中状态
            self.apply_button_selected_style(custom_card)
            custom_card.is_selected = True
            # 取消全屏按钮的选中状态
            full_screen_card.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 2px solid #4B5563; "
                "border-radius: 8px; "
                "text-align: center;"
            )
            full_screen_card.is_selected = False
            # 取消更多按钮的选中状态
            more_button.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 2px solid #4B5563; "
                "border-radius: 8px; "
                "text-align: center;"
            )
            more_button.is_selected = False
            # 更新状态栏 - 显示窗口模式（等待选择区域）
            if hasattr(self, 'status_label') and self.status_label:
                if not (hasattr(self, 'recording') and self.recording):
                    self.status_label.setText('当前为窗口录制模式 | 请选择录制区域')
                    self.status_label.setStyleSheet(
                        "color: #D1D5DB; "
                        "font-family: 'Microsoft YaHei'; "
                        "font-size: 13px; "
                        "background-color: transparent;"
                    )
                    print(f"DEBUG: 状态栏已更新为窗口模式（等待选择区域）")
            else:
                print(f"DEBUG: 状态栏不存在，hasattr: {hasattr(self, 'status_label')}, status_label: {getattr(self, 'status_label', 'N/A')}")
            # 显示区域选择窗口
            self.show_custom_region_selector()
        
        custom_card.clicked.connect(on_custom_clicked)
        
        # 更多按钮 - 调整为和全屏按钮一样大的图标按钮
        more_button_widget = QWidget()
        more_button_layout = QVBoxLayout(more_button_widget)
        more_button_layout.setAlignment(Qt.AlignCenter)
        more_button_layout.setSpacing(8)  # mt-2 = 8px
        
        more_button = QPushButton()
        more_button.setFixedSize(112, 112)  # w-28 h-28 = 112x112px，与全屏按钮相同
        
        # 使用3.png作为更多按钮的图标，与其他按钮保持一致
        try:
            from PyQt5.QtGui import QIcon
            from PyQt5.QtCore import QSize
            # 加载图片并添加圆角效果，与其他按钮保持一致
            rounded_pixmap = self.make_rounded_pixmap('iconic/3.png', 8)  # 8px圆角
            if not rounded_pixmap.isNull():
                more_icon = QIcon(rounded_pixmap)
                more_button.setIcon(more_icon)
                more_button.setIconSize(QSize(104, 104))  # 增大图标尺寸，只留2px边框空间
        except Exception as e:
            # 加载失败时打印错误信息以便调试
            print(f"加载3.png失败: {e}")
            pass
            
        # 设置更多按钮的默认样式，与全屏按钮保持一致
        more_button.setStyleSheet(
            "background-color: #2d2d38; "
            "border: 2px solid #4B5563; "
            "border-radius: 8px; "
            "text-align: center;"
        )
        # 取消气泡信息显示
        
        # 更多按钮标签
        more_label = QLabel('更多')
        more_label.setStyleSheet("color: #FFFFFF; font-family: 'Microsoft YaHei'; font-size: 14px;")
        more_label.setAlignment(Qt.AlignCenter)
        
        # 更多按钮悬停效果，与全屏按钮保持一致
        def more_enter(event):
            more_button.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 2px solid #ff3a3a; "  # 悬停时变为红色边框
                "border-radius: 8px; "
                "text-align: center;"
            )
            event.accept()
            
        def more_leave(event):
            # 如果按钮未选中，则恢复默认样式；如果已选中，保持选中样式
            if not hasattr(more_button, 'is_selected') or not more_button.is_selected:
                more_button.setStyleSheet(
                    "background-color: #2d2d38; "
                    "border: 2px solid #4B5563; "  # 离开时恢复灰色边框
                    "border-radius: 8px; "
                    "text-align: center;"
                )
            event.accept()
            
        more_button.enterEvent = more_enter
        more_button.leaveEvent = more_leave
        
        # 更多按钮点击事件 - 显示窗口列表菜单
        more_button.clicked.connect(self.show_window_list_menu)
        
        more_button_layout.addWidget(more_button)
        more_button_layout.addWidget(more_label)
        
        left_section.addWidget(full_screen_group)
        left_section.addWidget(custom_group)
        left_section.addWidget(more_button_widget)
        
        # 2. 中间设备区域 - 使用QWidget包装并调整对齐
        middle_section_widget = QWidget()
        middle_section = QVBoxLayout(middle_section_widget)
        middle_section.setAlignment(Qt.AlignVCenter)  # 垂直居中对齐
        middle_section.setSpacing(16)  # 增加间距以改善视觉效果
        middle_section.setContentsMargins(0, 0, 0, 0)  # 移除左侧边距，使用主布局的间距
        
        # 摄像头选择
        camera_layout = self.create_device_layout('摄像头', '无')
        
        # 麦克风选择
        mic_layout = self.create_device_layout('麦克风', '无')
        
        # 音频选择
        audio_layout = self.create_device_layout('音频', '无')
        
        middle_section.addLayout(camera_layout)
        middle_section.addLayout(mic_layout)
        middle_section.addLayout(audio_layout)
        
        # 3. 右侧录制按钮区域 - 实现开始、暂停、停止功能
        right_section_widget = QWidget()
        right_section = QVBoxLayout(right_section_widget)
        right_section.setAlignment(Qt.AlignCenter)
        right_section.setSpacing(16)
        
        # 创建开始按钮 - 默认显示，设置为新的颜色
        start_button = QPushButton('开始录制')
        start_button.setFixedSize(128, 128)  # w-32 h-32 = 128x128px
        start_button.setStyleSheet(
            "background-color: #fc3b54; "  # 新的颜色
            "color: #FFFFFF; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 18px; "
            "font-weight: 600; "
            "border-radius: 12px; "
            "border: none; "
            "border-style: outset; "
            "border-width: 1px;"
        )
        
        # 开始按钮悬停效果
        start_button.enterEvent = lambda e: start_button.setStyleSheet(
            "background-color: #e6344a; "  # 稍深的悬停颜色
            "color: #FFFFFF; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 18px; "
            "font-weight: 600; "
            "border-radius: 12px; "
            "border: 2px solid #ff3a3a; "  # 悬停时添加红色边框
            "border-style: outset; "
            "border-width: 2px;"
        )
        start_button.leaveEvent = lambda e: start_button.setStyleSheet(
            "background-color: #fc3b54; "  # 恢复新颜色
            "color: #FFFFFF; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 18px; "
            "font-weight: 600; "
            "border-radius: 12px; "
            "border: none; "
            "border-style: outset; "
            "border-width: 1px;"
        )
        
        # 创建暂停按钮 - 默认隐藏，圆形，带图标和悬停效果
        pause_button = QPushButton()
        pause_button.setFixedSize(64, 64)  # 圆形按钮尺寸
        pause_button.setStyleSheet(
            "background-color: #FFC107; "
            "border-radius: 32px; "  # 圆形按钮
            "border: none;"
        )
        
        # 暂停按钮悬停效果
        def pause_enter(event):
            pause_button.setStyleSheet(
                "background-color: #e6ad00; "  # 稍深的悬停颜色
                "border-radius: 32px; "
                "border: 2px solid #ff3a3a; "  # 悬停时添加红色边框
                "border-style: outset;"
            )
            event.accept()
        
        def pause_leave(event):
            pause_button.setStyleSheet(
                "background-color: #FFC107; "
                "border-radius: 32px; "
                "border: none;"
            )
            event.accept()
        
        pause_button.enterEvent = pause_enter
        pause_button.leaveEvent = pause_leave
        
        # 加载暂停和播放图标
        pause_pixmap = None
        play_pixmap = None
        try:
            from PyQt5.QtGui import QIcon, QPixmap
            from PyQt5.QtCore import QSize
            
            # 加载暂停图标
            pause_pixmap = QPixmap('iconic/pause.png')
            if not pause_pixmap.isNull():
                pause_icon = QIcon(pause_pixmap)
                pause_button.setIcon(pause_icon)
                pause_button.setIconSize(QSize(40, 40))
            
            # 加载播放图标（用于恢复录制状态）
            play_pixmap = QPixmap('iconic/play.png')
        except Exception as e:
            print(f"DEBUG: 加载图标失败: {e}")
        
        # 如果加载失败，设置默认文字
        if pause_pixmap is None or pause_pixmap.isNull():
            pause_button.setText('暂停')
            # 重置基本样式（在设置文字后）
            pause_button.setStyleSheet(
                "background-color: #FFC107; "
                "color: #FFFFFF; "
                "font-family: 'Microsoft YaHei'; "
                "font-size: 14px; "
                "border-radius: 32px; "
                "border: none;"
            )
            # 重新设置悬停效果
            pause_button.enterEvent = lambda e: pause_button.setStyleSheet(
                "background-color: #e6ad00; "
                "color: #FFFFFF; "
                "font-family: 'Microsoft YaHei'; "
                "font-size: 14px; "
                "border-radius: 32px; "
                "border: 2px solid #ff3a3a; "
                "border-style: outset;"
            )
            pause_button.leaveEvent = lambda e: pause_button.setStyleSheet(
                "background-color: #FFC107; "
                "color: #FFFFFF; "
                "font-family: 'Microsoft YaHei'; "
                "font-size: 14px; "
                "border-radius: 32px; "
                "border: none;"
            )
        
        # 创建停止按钮 - 默认隐藏，圆形，带图标和悬停效果
        stop_button = QPushButton()
        stop_button.setFixedSize(64, 64)  # 圆形按钮尺寸
        stop_button.setStyleSheet(
            "background-color: #DC2626; "
            "border-radius: 32px; "  # 圆形按钮
            "border: none;"
        )
        
        # 停止按钮悬停效果
        def stop_enter(event):
            stop_button.setStyleSheet(
                "background-color: #c81e1e; "  # 稍深的悬停颜色
                "border-radius: 32px; "
                "border: 2px solid #ff3a3a; "  # 悬停时添加红色边框
                "border-style: outset;"
            )
            event.accept()
        
        def stop_leave(event):
            stop_button.setStyleSheet(
                "background-color: #DC2626; "
                "border-radius: 32px; "
                "border: none;"
            )
            event.accept()
        
        stop_button.enterEvent = stop_enter
        stop_button.leaveEvent = stop_leave
        
        # 尝试加载停止图标
        try:
            stop_pixmap = QPixmap('iconic/stop.png')
            if not stop_pixmap.isNull():
                stop_icon = QIcon(stop_pixmap)
                stop_button.setIcon(stop_icon)
                stop_button.setIconSize(QSize(40, 40))
        except Exception as e:
            # 如果加载失败，设置默认文字
            stop_button.setText('停止')
            # 重置基本样式（在设置文字后）
            stop_button.setStyleSheet(
                "background-color: #DC2626; "
                "color: #FFFFFF; "
                "font-family: 'Microsoft YaHei'; "
                "font-size: 14px; "
                "border-radius: 32px; "
                "border: none;"
            )
            # 重新设置悬停效果
            stop_button.enterEvent = lambda e: stop_button.setStyleSheet(
                "background-color: #c81e1e; "
                "color: #FFFFFF; "
                "font-family: 'Microsoft YaHei'; "
                "font-size: 14px; "
                "border-radius: 32px; "
                "border: 2px solid #ff3a3a; "
                "border-style: outset;"
            )
            stop_button.leaveEvent = lambda e: stop_button.setStyleSheet(
                "background-color: #DC2626; "
                "color: #FFFFFF; "
                "font-family: 'Microsoft YaHei'; "
                "font-size: 14px; "
                "border-radius: 32px; "
                "border: none;"
            )
        
        # 创建包含暂停和停止按钮的水平布局
        control_buttons_layout = QHBoxLayout()
        control_buttons_layout.setAlignment(Qt.AlignCenter)
        control_buttons_layout.setSpacing(24)  # 按钮间距
        control_buttons_layout.addWidget(pause_button)
        control_buttons_layout.addWidget(stop_button)
        
        # 暂停和停止按钮默认隐藏
        pause_button.hide()
        stop_button.hide()
        
        # 按钮点击事件处理函数
        def start_recording():
            # 检查是否选择了录制窗口方式
            fullscreen_selected = getattr(self.fullscreen_button, 'is_selected', False) if hasattr(self, 'fullscreen_button') else False
            custom_selected = getattr(self.custom_button, 'is_selected', False) if hasattr(self, 'custom_button') else False
            window_selected = (self.recording_mode == 'window' and self.selected_window_handle is not None)
            
            if not fullscreen_selected and not custom_selected and not window_selected:
                CustomMessageBox.show_message(self, '提示', '请选择录制窗口方式', 'warning')
                return
            
            # 检查录制模式
            if self.recording_mode == 'custom' and self.custom_region is None:
                CustomMessageBox.show_message(self, '提示', '请先选择自定义录制区域！', 'warning')
                return
            
            if self.recording_mode == 'window' and (self.selected_window_handle is None or self.custom_region is None):
                CustomMessageBox.show_message(self, '提示', '请先选择要录制的窗口！', 'warning')
                return
            
            # 获取设置选项
            fps_text = self.settings_window.fps_combo.currentText() if hasattr(self, 'settings_window') and self.settings_window and hasattr(self.settings_window, 'fps_combo') else '30 FPS'
            self.recording_fps = int(fps_text.split()[0])
            
            # 隐藏开始按钮，显示控制按钮
            start_button.hide()
            pause_button.show()
            stop_button.show()
            
            # 开始录制状态
            self.recording = True
            self.paused = False
            # 全新开始录制，重置时间
            self.start_time = time.time()
            self.elapsed_time = 0
            
            # 更新状态栏 - 显示录制模式和初始时间
            if hasattr(self, 'status_label') and self.status_label:
                mode_text = "当前为全屏录制模式" if self.recording_mode == 'fullscreen' else "当前为窗口录制模式"
                self.status_label.setText(f'{mode_text} | 录制中: 00:00:00')
                self.status_label.setStyleSheet(
                    "color: #ff0021; "
                    "font-family: 'Microsoft YaHei'; "
                    "font-size: 11px; "
                    "font-weight: 500; "
                    "background-color: transparent;"
                )
                print(f"DEBUG: 状态栏已更新: {mode_text} | 录制中: 00:00:00")
            else:
                print("DEBUG: 警告：status_label不存在或未初始化")
            
            # 启动计时器
            if self.timer is None:
                self.timer = QTimer()
                self.timer.timeout.connect(self.update_recording_time)
            self.timer.start(1000)  # 每秒更新一次
            
            # 如果设置了录制开始时隐藏主窗口
            if hasattr(self, 'settings_window') and self.settings_window and hasattr(self.settings_window, 'hide_main_window_check') and self.settings_window.hide_main_window_check.isChecked():
                self.hide()
            
            # 如果是窗口模式，启动窗口跟随
            if self.recording_mode == 'window' and self.selected_window_handle:
                self.start_window_follow()
            
            # 开始实际录屏
            self.start_screen_recording()
        
        def pause_recording():
            if self.recording:
                if not self.paused:
                    # 暂停录制
                    self.paused = True
                    self.elapsed_time = time.time() - self.start_time
                    self.timer.stop()
                    
                    # 暂停录屏线程
                    if self.recording_thread:
                        self.recording_thread.pause()
                    
                    # 切换按钮图标为播放图标（表示可以继续录制）
                    try:
                        from PyQt5.QtGui import QIcon, QPixmap
                        from PyQt5.QtCore import QSize
                        if play_pixmap and not play_pixmap.isNull():
                            play_icon = QIcon(play_pixmap)
                            pause_button.setIcon(play_icon)
                            pause_button.setIconSize(QSize(40, 40))
                            pause_button.setText('')  # 清除文字，只显示图标
                        else:
                            pause_button.setText('播放')
                    except Exception as e:
                        pause_button.setText('播放')
                    
                    # 更新状态栏 - 暂停时也显示录制模式
                    if self.status_label:
                        mode_text = "当前为全屏录制模式" if self.recording_mode == 'fullscreen' else "当前为窗口录制模式"
                        self.status_label.setText(f'{mode_text} | 已暂停: {self.format_time(self.elapsed_time)}')
                        self.status_label.setStyleSheet(
                            "color: #FFC107; "
                            "font-family: 'Microsoft YaHei'; "
                            "font-size: 11px; "
                            "font-weight: 500; "
                            "background-color: transparent;"
                        )
                else:
                    # 恢复录制（继续录制）
                    self.paused = False
                    self.start_time = time.time() - self.elapsed_time
                    self.timer.start(1000)
                    
                    # 恢复录屏线程
                    if self.recording_thread:
                        self.recording_thread.resume()
                    
                    # 切换按钮图标为暂停图标（表示可以暂停录制）
                    try:
                        from PyQt5.QtGui import QIcon, QPixmap
                        from PyQt5.QtCore import QSize
                        if pause_pixmap and not pause_pixmap.isNull():
                            pause_icon = QIcon(pause_pixmap)
                            pause_button.setIcon(pause_icon)
                            pause_button.setIconSize(QSize(40, 40))
                            pause_button.setText('')  # 清除文字，只显示图标
                        else:
                            pause_button.setText('暂停')
                    except Exception as e:
                        pause_button.setText('暂停')
                    
                    # 更新状态栏 - 恢复录制时显示录制模式
                    if self.status_label:
                        mode_text = "当前为全屏录制模式" if self.recording_mode == 'fullscreen' else "当前为窗口录制模式"
                        self.status_label.setText(f'{mode_text} | 录制中: {self.format_time(self.elapsed_time)}')
                        self.status_label.setStyleSheet(
                            "color: #ff0021; "
                            "font-family: 'Microsoft YaHei'; "
                            "font-size: 11px; "
                            "font-weight: 500; "
                            "background-color: transparent;"
                        )
        
        def stop_recording():
            try:
                # 停止实际录屏
                self.stop_screen_recording()
            except Exception as stop_error:
                print(f"DEBUG: 停止录屏时出错: {stop_error}")
                import traceback
                traceback.print_exc()
            
            try:
                # 隐藏控制按钮，显示开始按钮
                pause_button.hide()
                stop_button.hide()
                start_button.show()
                
                # 如果主窗口被隐藏，显示回来
                if self.isHidden():
                    self.show()
                
                # 停止录制
                self.recording = False
                self.paused = False
                if self.timer:
                    self.timer.stop()
                
                # 重置计时器
                self.elapsed_time = 0
                
                # 更新状态栏 - 停止录制后恢复为窗口模式和就绪状态
                # 注意：这里不立即更新状态栏，因为视频处理完成后会更新
                # 如果视频处理失败，状态栏会在on_video_processing_complete中更新
            except Exception as ui_error:
                print(f"DEBUG: 更新UI时出错: {ui_error}")
                import traceback
                traceback.print_exc()
        
        # 连接点击事件
        start_button.clicked.connect(start_recording)
        pause_button.clicked.connect(pause_recording)
        stop_button.clicked.connect(stop_recording)
        
        # 保存按钮引用为实例变量，供快捷键使用
        self.start_button = start_button
        self.pause_button = pause_button
        self.stop_button = stop_button
        
        # 添加到右侧布局
        right_section.addWidget(start_button)
        right_section.addLayout(control_buttons_layout)
        
        # 创建垂直分隔线 - 调整大小和边距以确保垂直居中
        vertical_line_widget = QWidget()
        vertical_line_layout = QVBoxLayout(vertical_line_widget)
        vertical_line_layout.setAlignment(Qt.AlignVCenter)
        
        vertical_line = QFrame()
        vertical_line.setFixedSize(1, 180)  # 增加高度以匹配整体布局
        vertical_line.setStyleSheet("background-color: #374151;")
        
        vertical_line_layout.addWidget(vertical_line)
        
        # 调整主布局结构，将垂直分割线放到设备区域左边
        main_layout.addWidget(left_section_widget, 0, Qt.AlignLeft)
        main_layout.addWidget(vertical_line_widget, 0, Qt.AlignVCenter)  # 垂直分割线移到设备区域左边
        main_layout.addWidget(middle_section_widget, 1, Qt.AlignCenter)  # 给中间部分适当空间
        main_layout.addWidget(right_section_widget, 2, Qt.AlignRight)  # 给右侧控制按钮区域更多伸展空间
        
        return main_content
    
    @property
    def camera_icon_widget(self):
        """获取摄像头图标部件"""
        return self._camera_icon_widget
    
    @camera_icon_widget.setter
    def camera_icon_widget(self, value):
        """设置摄像头图标部件"""
        self._camera_icon_widget = value
    
    def create_device_layout(self, icon_name, default_text):
        # 创建设备选择布局 - 精确尺寸和坐标
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        layout.setSpacing(8)  # mr-2 = 8px
        
        # 根据设备类型选择对应的图标
        icon_path = ""
        if icon_name == '摄像头':
            icon_path = "iconic/camx.png"
        elif icon_name == '麦克风':
            icon_path = "iconic/microx.png"
        elif icon_name == '音频':
            icon_path = "iconic/speake.png"
        
        # 创建图标标签
        icon_widget = QLabel()
        icon_widget.setFixedSize(20, 20)
        icon_widget.setAlignment(Qt.AlignCenter)
        
        # 保存原始pixmap和样式用于悬停效果
        original_pixmap = None
        has_icon = False
        default_bg_style = ""
        
        # 加载并显示图标
        if icon_path:
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                # 调整图标大小以适应
                scaled_pixmap = pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                original_pixmap = scaled_pixmap
                icon_widget.setPixmap(scaled_pixmap)
                has_icon = True
            else:
                # 如果图标加载失败，显示默认背景色
                default_bg_style = "background-color: #6B7280; border-radius: 4px;"
                icon_widget.setStyleSheet(default_bg_style)
        else:
            default_bg_style = "background-color: #6B7280; border-radius: 4px;"
            icon_widget.setStyleSheet(default_bg_style)
        
        # 添加悬停效果
        def icon_enter_event(event):
            """鼠标进入图标时的效果"""
            if has_icon:
                # 有图标时：添加红色半透明背景
                icon_widget.setStyleSheet("""
                    background-color: rgba(255, 58, 58, 0.2);
                    border-radius: 4px;
                """)
            else:
                # 无图标时：改变背景色为红色半透明
                icon_widget.setStyleSheet("""
                    background-color: rgba(255, 58, 58, 0.3);
                    border-radius: 4px;
                """)
            event.accept()
        
        def icon_leave_event(event):
            """鼠标离开图标时的效果"""
            if has_icon:
                # 恢复透明背景
                icon_widget.setStyleSheet("background-color: transparent;")
            else:
                # 恢复默认背景色
                if default_bg_style:
                    icon_widget.setStyleSheet(default_bg_style)
                else:
                    icon_widget.setStyleSheet("background-color: transparent;")
            event.accept()
        
        icon_widget.enterEvent = icon_enter_event
        icon_widget.leaveEvent = icon_leave_event
        
        # 设备选择器 - 使用ComboBox（先创建，以便在点击事件中使用）
        device_combo = QComboBox()
        device_combo.setFixedWidth(200)
        device_combo.setStyleSheet("""
            QComboBox {
                background-color: #2d2d38;
                border: 1px solid #4B5563;
                border-radius: 8px;
                color: #D1D5DB;
                padding: 8px 16px;
                font-family: 'Microsoft YaHei';
                font-size: 14px;
            }
            QComboBox:hover {
                background-color: #374151;
                border: 1px solid #ff3a3a;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #D1D5DB;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d38;
                border: 1px solid #4B5563;
                border-radius: 6px;
                color: #D1D5DB;
                selection-background-color: #374151;
                selection-color: #FFFFFF;
            }
        """)
        
        # 根据设备类型填充选项
        if icon_name == '摄像头':
            cameras = self.detect_cameras()
            if cameras:
                # 如果检测到摄像头，只显示检测到的设备，默认选择第一个
                device_combo.addItems(cameras)
                device_combo.setCurrentIndex(0)  # 默认选择第一个检测到的摄像头
            else:
                # 如果检测不到摄像头，才显示"无"选项
                device_combo.addItem('无')
                device_combo.setCurrentText('无')
        elif icon_name == '麦克风':
            microphones = self.detect_microphones()
            if microphones:
                # 如果检测到麦克风，只显示检测到的设备，默认选择第一个
                device_combo.addItems(microphones)
                device_combo.setCurrentIndex(0)  # 默认选择第一个检测到的麦克风
            else:
                # 如果检测不到麦克风，才显示"无"选项
                device_combo.addItem('无')
                device_combo.setCurrentText('无')
        elif icon_name == '音频':
            outputs = self.detect_audio_outputs()
            if outputs:
                # 如果检测到音频输出设备，只显示检测到的设备，默认选择第一个
                device_combo.addItems(outputs)
                device_combo.setCurrentIndex(0)  # 默认选择第一个检测到的音频输出设备
            else:
                # 如果检测不到音频输出设备，才显示"无"选项
                device_combo.addItem('无')
                device_combo.setCurrentText('无')
        
        # 立即保存图标引用和设备下拉菜单引用
        if icon_name == '摄像头':
            # 保存摄像头图标引用到实例变量
            self.camera_icon_widget = icon_widget
            self.camera_combo = device_combo  # 保存摄像头下拉菜单引用
        elif icon_name == '麦克风':
            self.microphone_icon_widget = icon_widget
            self.microphone_combo = device_combo  # 保存麦克风下拉菜单引用
            print(f"DEBUG: 保存麦克风图标引用: {icon_widget}, id={id(icon_widget)}")
            print(f"DEBUG: 保存麦克风下拉菜单引用: {device_combo}, id={id(device_combo)}, 当前文本: {device_combo.currentText()}")
        elif icon_name == '音频':
            self.audio_icon_widget = icon_widget
            self.audio_combo = device_combo  # 保存音频下拉菜单引用
            print(f"DEBUG: 保存音频图标引用: {icon_widget}, id={id(icon_widget)}")
        
        # 如果是摄像头图标，添加点击事件（在device_combo创建之后）
        if icon_name == '摄像头':
            # 使图标可点击
            icon_widget.setCursor(Qt.PointingHandCursor)
            
            # 保存两个图标的pixmap为实例变量，以便在其他方法中使用
            # 使用 camx.png（禁用状态）和 cam.png（启用状态）
            camx_path = "iconic/camx.png"
            cam_path = "iconic/cam.png"
            
            self.camx_pixmap = QPixmap(camx_path)
            self.cam_pixmap = QPixmap(cam_path)
            
            if not self.camx_pixmap.isNull():
                self.camx_pixmap = self.camx_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                # 设置初始图标为禁用状态
                icon_widget.setPixmap(self.camx_pixmap)
            
            if not self.cam_pixmap.isNull():
                self.cam_pixmap = self.cam_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # 使用lambda函数绑定当前的icon_widget和device_combo
            icon_widget.mousePressEvent = lambda event, icon=icon_widget, combo=device_combo: self.on_camera_icon_clicked(event, icon, combo)
        
        # 如果是麦克风图标，添加点击事件（在device_combo创建之后）
        if icon_name == '麦克风':
            # 使图标可点击
            icon_widget.setCursor(Qt.PointingHandCursor)
            
            # 保存两个图标的pixmap为实例变量，以便在其他方法中使用
            microx_path = "iconic/microx.png"
            micro_path = "iconic/micro.png"
            
            self.microx_pixmap = QPixmap(microx_path)
            self.micro_pixmap = QPixmap(micro_path)
            
            if not self.microx_pixmap.isNull():
                self.microx_pixmap = self.microx_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not self.micro_pixmap.isNull():
                self.micro_pixmap = self.micro_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # 初始化图标状态（默认禁用状态，显示microx.png）
            if not self.microx_pixmap.isNull():
                icon_widget.setPixmap(self.microx_pixmap)
            self.microphone_enabled = False
            
            def mic_icon_mouse_press_event(event):
                """麦克风图标点击事件"""
                if event.button() == Qt.LeftButton:
                    print(f"DEBUG: 麦克风图标被点击，当前状态: {self.microphone_enabled}")
                    print(f"DEBUG: microphone_icon_widget = {self.microphone_icon_widget}")
                    print(f"DEBUG: icon_widget = {icon_widget}, id={id(icon_widget)}")
                    # 如果microphone_icon_widget为None，尝试重新赋值
                    if self.microphone_icon_widget is None:
                        print("DEBUG: microphone_icon_widget 为 None，尝试重新赋值")
                        self.microphone_icon_widget = icon_widget
                    self.toggle_microphone()
                event.accept()
            
            icon_widget.mousePressEvent = mic_icon_mouse_press_event
        
        # 如果是音频图标，添加点击事件（在device_combo创建之后）
        if icon_name == '音频':
            # 使图标可点击
            icon_widget.setCursor(Qt.PointingHandCursor)
            
            # 保存两个图标的pixmap为实例变量，以便在其他方法中使用
            speake_path = "iconic/speake.png"
            speakex_path = "iconic/speakex.png"
            
            self.speake_pixmap = QPixmap(speake_path)
            self.speakex_pixmap = QPixmap(speakex_path)
            
            if not self.speake_pixmap.isNull():
                self.speake_pixmap = self.speake_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not self.speakex_pixmap.isNull():
                self.speakex_pixmap = self.speakex_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # 初始化图标状态（默认启用状态，显示speake.png）
            if not self.speake_pixmap.isNull():
                icon_widget.setPixmap(self.speake_pixmap)
            self.audio_enabled = True
            
            def audio_icon_mouse_press_event(event):
                """音频图标点击事件"""
                if event.button() == Qt.LeftButton:
                    print(f"DEBUG: 音频图标被点击，当前状态: {self.audio_enabled}")
                    print(f"DEBUG: audio_icon_widget = {self.audio_icon_widget}")
                    print(f"DEBUG: icon_widget = {icon_widget}, id={id(icon_widget)}")
                    # 如果audio_icon_widget为None，尝试重新赋值
                    if self.audio_icon_widget is None:
                        print("DEBUG: audio_icon_widget 为 None，尝试重新赋值")
                        self.audio_icon_widget = icon_widget
                    self.toggle_audio()
                event.accept()
            
            icon_widget.mousePressEvent = audio_icon_mouse_press_event
        
        layout.addWidget(icon_widget)
        layout.addWidget(device_combo)
        
        return layout
    
    def create_bottom_bar(self):
        # 创建底部选项栏，精确高度40px
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(40)
        # 下段区域：保留左下角和右下角圆角，左上角和右上角改为方角
        bottom_bar.setStyleSheet(
            "background-color: #13131a; "
            "border-top-left-radius: 0px; "
            "border-top-right-radius: 0px; "
            "border-bottom-left-radius: 12px; "
            "border-bottom-right-radius: 12px;"
        )
        
        # 创建底部布局
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(24, 0, 24, 0)  # 左右边距
        bottom_layout.setSpacing(0)  # 重置默认间距
        
        # 左侧按钮容器
        left_container = QWidget()
        left_layout = QHBoxLayout(left_container)
        left_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        left_layout.setSpacing(24)  # 按钮间距
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建文件列表按钮 - 使用更简单直接的实现方式
        file_list_button = QPushButton()
        file_list_button.setFixedHeight(36)  # 按钮高度稍小于底部栏，有内边距
        file_list_button.setFixedWidth(110)  # 固定宽度确保文字和图标完整显示
        file_list_button.setStyleSheet("background-color: transparent; border: none; margin: 2px 0;")
        
        # 创建文件列表按钮内部布局
        file_list_inner_layout = QHBoxLayout(file_list_button)
        file_list_inner_layout.setContentsMargins(10, 0, 10, 0)  # 按钮内部左右边距
        file_list_inner_layout.setSpacing(8)  # 图标和文字之间的间距
        file_list_inner_layout.setAlignment(Qt.AlignCenter)
        
        # 文件列表图标
        list_icon_label = QLabel()
        list_icon_label.setFixedSize(20, 20)  # 固定图标大小确保完整显示
        list_icon_label.setAlignment(Qt.AlignCenter)
        
        # 加载并设置文件列表图标
        list_pixmap = QPixmap("iconic/list.png")
        if not list_pixmap.isNull():
            # 确保图标适应标签大小并完整显示
            scaled_pixmap = list_pixmap.scaled(
                20, 20, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            list_icon_label.setPixmap(scaled_pixmap)
        
        # 文件列表文字
        list_text_label = QLabel("文件列表")
        list_text_label.setStyleSheet(
            "color: #D1D5DB;"
            "font-family: 'Microsoft YaHei';"
            "font-size: 13px;"
            "background-color: transparent;"
        )
        
        # 添加图标和文字到按钮内部布局
        file_list_inner_layout.addWidget(list_icon_label)
        file_list_inner_layout.addWidget(list_text_label)
        
        # 设置文件列表按钮悬停效果
        def file_list_enter(event):
            file_list_button.setStyleSheet(
                "background-color: #2d2d38;"
                "border: none;"
                "margin: 2px 0;"
                "border-radius: 4px;"
            )
            list_text_label.setStyleSheet(
                "color: #FFFFFF;"
                "font-family: 'Microsoft YaHei';"
                "font-size: 13px;"
                "background-color: transparent;"
            )
        
        def file_list_leave(event):
            file_list_button.setStyleSheet(
                "background-color: transparent;"
                "border: none;"
                "margin: 2px 0;"
            )
            list_text_label.setStyleSheet(
                "color: #D1D5DB;"
                "font-family: 'Microsoft YaHei';"
                "font-size: 13px;"
                "background-color: transparent;"
            )
        
        file_list_button.enterEvent = file_list_enter
        file_list_button.leaveEvent = file_list_leave
        file_list_button.clicked.connect(self.show_file_list_window)
        
        # 创建工具按钮
        tools_button = QPushButton()
        tools_button.setFixedHeight(36)  # 按钮高度稍小于底部栏，有内边距
        tools_button.setFixedWidth(80)  # 固定宽度确保文字和图标完整显示
        tools_button.setStyleSheet("background-color: transparent; border: none; margin: 2px 0;")
        
        # 创建工具按钮内部布局
        tools_inner_layout = QHBoxLayout(tools_button)
        tools_inner_layout.setContentsMargins(10, 0, 10, 0)  # 按钮内部左右边距
        tools_inner_layout.setSpacing(8)  # 图标和文字之间的间距
        tools_inner_layout.setAlignment(Qt.AlignCenter)
        
        # 工具图标
        tools_icon_label = QLabel()
        tools_icon_label.setFixedSize(20, 20)  # 固定图标大小确保完整显示
        tools_icon_label.setAlignment(Qt.AlignCenter)
        
        # 加载并设置工具图标
        tools_pixmap = QPixmap("iconic/tools.png")
        if not tools_pixmap.isNull():
            # 确保图标适应标签大小并完整显示
            scaled_pixmap = tools_pixmap.scaled(
                15, 15, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            tools_icon_label.setPixmap(scaled_pixmap)
        
        # 工具文字
        tools_text_label = QLabel("工具")
        tools_text_label.setStyleSheet(
            "color: #D1D5DB;"
            "font-family: 'Microsoft YaHei';"
            "font-size: 13px;"
            "background-color: transparent;"
        )
        
        # 添加图标和文字到按钮内部布局
        tools_inner_layout.addWidget(tools_icon_label)
        tools_inner_layout.addWidget(tools_text_label)
        
        # 设置工具按钮悬停效果
        def tools_enter(event):
            tools_button.setStyleSheet(
                "background-color: #2d2d38;"
                "border: none;"
                "margin: 2px 0;"
                "border-radius: 4px;"
            )
            tools_text_label.setStyleSheet(
                "color: #FFFFFF;"
                "font-family: 'Microsoft YaHei';"
                "font-size: 13px;"
                "background-color: transparent;"
            )
            event.accept()
            
        def tools_leave(event):
            tools_button.setStyleSheet(
                "background-color: transparent;"
                "border: none;"
                "margin: 2px 0;"
            )
            tools_text_label.setStyleSheet(
                "color: #D1D5DB;"
                "font-family: 'Microsoft YaHei';"
                "font-size: 13px;"
                "background-color: transparent;"
            )
            event.accept()
            
        tools_button.enterEvent = tools_enter
        tools_button.leaveEvent = tools_leave
        # 确保工具按钮处于启用状态
        tools_button.setEnabled(True)
        # 工具按钮点击事件 - 功能正在开发中
        tools_button.clicked.connect(lambda: self.show_under_development("工具功能"))
        
        # 将按钮添加到左侧容器布局
        left_layout.addWidget(file_list_button)
        left_layout.addWidget(tools_button)
        
        # 创建状态栏显示组件 - 用于显示录制状态和时间
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_layout.setContentsMargins(0, 0, 0, 0)
        
        # 状态栏标签 - 初始显示窗口模式和就绪状态
        self.status_label = QLabel("当前窗口模式 | 就绪")
        self.status_label.setStyleSheet(
            "color: #D1D5DB; "
            "font-family: 'Microsoft YaHei'; "
            "font-size: 13px; "
            "background-color: transparent;"
        )
        
        status_layout.addWidget(self.status_label)
        
        # 添加到主底部布局
        bottom_layout.addWidget(left_container)
        bottom_layout.addStretch(1)  # 中间拉伸空间
        bottom_layout.addWidget(status_container)
        
        return bottom_bar
        
    def show_file_list_window(self):
        """显示文件列表窗口 - 作为独立窗口"""
        # 如果窗口不存在或已被关闭，则创建新窗口
        if self.file_list_window is None or not self.file_list_window.isVisible():
            self.file_list_window = FileListWindow()  # 不传递parent，使其独立
            
            # 将窗口居中显示在屏幕中央，作为独立窗口
            screen = QDesktopWidget().screenGeometry()
            window_geometry = self.file_list_window.frameGeometry()
            x = (screen.width() - window_geometry.width()) // 2
            y = (screen.height() - window_geometry.height()) // 2
            self.file_list_window.move(x, y)
            
            # 刷新文件列表
            self.file_list_window.load_file_list()
            
            # 显示窗口
            self.file_list_window.show()
            self.file_list_window.raise_()
            self.file_list_window.activateWindow()
        else:
            # 如果窗口已经显示，则激活它并刷新列表
            self.file_list_window.load_file_list()
            self.file_list_window.raise_()
            self.file_list_window.activateWindow()
    
    def show_menu(self):
        """显示菜单"""
        menu = RoundedMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: transparent;
                border: none;
                color: #FFFFFF;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px 8px 12px;
                border-radius: 4px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
            }
            QMenu::item:selected {
                background-color: #374151;
                color: #FFFFFF;
            }
        """)
        
        # 设置选项
        settings_action = QAction('设置', self)
        settings_action.triggered.connect(self.show_settings_window)
        menu.addAction(settings_action)
        
        # 关于选项
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about_window)
        menu.addAction(about_action)
        
        # 在菜单按钮下方显示菜单
        menu_button = self.sender()
        if menu_button:
            pos = menu_button.mapToGlobal(menu_button.rect().bottomLeft())
            menu.exec_(pos)
    
    def show_settings_window(self):
        """显示设置窗口"""
        if self.settings_window is None or not self.settings_window.isVisible():
            self.settings_window = SettingsWindow()
            screen = QDesktopWidget().screenGeometry()
            window_geometry = self.settings_window.frameGeometry()
            x = (screen.width() - window_geometry.width()) // 2
            y = (screen.height() - window_geometry.height()) // 2
            self.settings_window.move(x, y)
            self.settings_window.show()
            self.settings_window.raise_()
            self.settings_window.activateWindow()
        else:
            self.settings_window.raise_()
            self.settings_window.activateWindow()
    
    def show_about_window(self):
        """显示关于窗口"""
        if self.about_window is None or not self.about_window.isVisible():
            self.about_window = AboutWindow()
            screen = QDesktopWidget().screenGeometry()
            window_geometry = self.about_window.frameGeometry()
            x = (screen.width() - window_geometry.width()) // 2
            y = (screen.height() - window_geometry.height()) // 2
            self.about_window.move(x, y)
            self.about_window.show()
            self.about_window.raise_()
            self.about_window.activateWindow()
        else:
            self.about_window.raise_()
            self.about_window.activateWindow()
    
    def on_camera_icon_clicked(self, event, icon_widget, device_combo):
        """摄像头图标点击事件处理"""
        if event.button() == Qt.LeftButton:
            # 确保摄像头图标引用被正确设置
            if self.camera_icon_widget is None:
                self.camera_icon_widget = icon_widget
            self.toggle_camera_preview(device_combo)
        event.accept()
    
    def toggle_camera_preview(self, device_combo):
        """切换摄像头预览窗口"""
        # 获取当前选择的摄像头索引
        current_text = device_combo.currentText()
        if current_text == '无' or not current_text:
            # 没有可用设备，显示提示
            CustomMessageBox.show_message(self, '提示', '没有可用的摄像头设备，请先连接摄像头设备', 'warning')
            print("DEBUG: 没有可用的摄像头设备")
            return
        
        # 获取摄像头列表
        cameras = self.detect_cameras()
        if not cameras:
            CustomMessageBox.show_message(self, '提示', '没有可用的摄像头设备，请先连接摄像头设备', 'warning')
            print("DEBUG: 未检测到摄像头设备")
            return
        
        # 根据选择的设备名称确定摄像头索引
        camera_index = self.camera_device_index_map.get(current_text, 0)
        print(f"DEBUG: 选择的设备: {current_text}, 映射索引: {camera_index}")
        
        # 如果预览窗口不存在或已关闭，创建并显示
        if self.camera_preview_window is None or not self.camera_preview_window.isVisible():
            # 关闭旧窗口（如果存在）
            if self.camera_preview_window:
                self.camera_preview_window.close()
            
            # 创建新窗口
            self.camera_preview_window = CameraPreviewWindow(camera_index=camera_index)
            
            # 连接窗口关闭事件，当窗口关闭时切换回camx.png
            main_window_ref = self
            original_close_event = self.camera_preview_window.closeEvent
            def custom_close_event(event):
                original_close_event(event)
                main_window_ref.restore_camera_icon()
                main_window_ref.camera_preview_window = None
            self.camera_preview_window.closeEvent = custom_close_event
            
            # 直接设置图标为 cam.png（启用状态），不依赖之前保存的 pixmap
            if self.camera_icon_widget is not None:
                cam_pixmap = QPixmap("iconic/cam.png")
                if not cam_pixmap.isNull():
                    cam_pixmap = cam_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.camera_icon_widget.setPixmap(cam_pixmap)
                    self.camera_icon_widget.setStyleSheet("background-color: transparent;")
                    self.camera_icon_widget.update()
                    QApplication.processEvents()
            
            # 显示窗口
            self.camera_preview_window.show()
            self.camera_preview_window.raise_()
            self.camera_preview_window.activateWindow()
            
            # 窗口显示后再次尝试切换图标（使用定时器延迟，确保界面已更新）
            QTimer.singleShot(100, lambda: self.force_camera_icon_update(True))
        else:
            # 如果预览窗口已打开，先切换图标，再关闭窗口
            self.force_camera_icon_update(False)
            self.camera_preview_window.close()
    
    def force_camera_icon_update(self, is_active):
        """强制更新摄像头图标"""
        if self.camera_icon_widget is None:
            return
        
        # 直接加载并设置图标，不依赖之前保存的 pixmap
        icon_path = "iconic/cam.png" if is_active else "iconic/camx.png"
        
        pixmap = QPixmap(icon_path)
        if pixmap.isNull():
            return
        
        scaled_pixmap = pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.camera_icon_widget.setPixmap(scaled_pixmap)
        self.camera_icon_widget.setStyleSheet("background-color: transparent;")
        self.camera_icon_widget.update()
        QApplication.processEvents()
    
    def switch_to_active_camera_icon(self):
        """切换到激活状态的摄像头图标（cam.png）"""
        if self.camera_icon_widget is None:
            return
        
        # 确保 cam_pixmap 已加载
        if not hasattr(self, 'cam_pixmap') or self.cam_pixmap.isNull():
            self.cam_pixmap = QPixmap("iconic/cam.png")
            if self.cam_pixmap.isNull():
                return
            self.cam_pixmap = self.cam_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.camera_icon_widget.setPixmap(self.cam_pixmap)
        self.camera_icon_widget.setStyleSheet("background-color: transparent;")
        self.camera_icon_widget.update()
        QApplication.processEvents()
    
    def restore_camera_icon(self):
        """恢复摄像头图标为默认状态（camx.png）"""
        self.force_camera_icon_update(False)
    
    def toggle_microphone(self):
        """切换麦克风启用/禁用状态"""
        print(f"DEBUG: toggle_microphone 被调用")
        print(f"DEBUG: microphone_icon_widget = {self.microphone_icon_widget}")
        
        if self.microphone_icon_widget is None:
            print("DEBUG: microphone_icon_widget 为 None，无法切换")
            return
        
        # 检查当前麦克风设备
        current_device = None
        if hasattr(self, 'microphone_combo') and self.microphone_combo:
            current_device = self.microphone_combo.currentText()
            print(f"DEBUG: 当前麦克风设备: {current_device}")
        
        # 如果当前是禁用状态，尝试启用时检查是否有设备
        if not self.microphone_enabled:
            if not current_device or current_device == '无':
                # 没有可用设备，显示提示
                CustomMessageBox.show_message(self, '提示', '没有可用的麦克风设备，请先连接麦克风设备', 'warning')
                print("DEBUG: 没有可用的麦克风设备")
                return
        
        # 切换状态
        self.microphone_enabled = not self.microphone_enabled
        print(f"DEBUG: 切换后状态: microphone_enabled = {self.microphone_enabled}")
        
        # 如果正在录制，动态控制录制线程的麦克风状态
        if hasattr(self, 'recording') and self.recording and hasattr(self, 'recording_thread') and self.recording_thread:
            print(f"DEBUG: 正在录制，动态控制麦克风状态")
            if self.recording_thread.set_microphone_enabled(self.microphone_enabled):
                print(f"DEBUG: 录制线程麦克风状态已更新: {self.microphone_enabled}")
            else:
                print(f"DEBUG: 无法更新录制线程麦克风状态")
        
        if self.microphone_enabled:
            # 启用状态：显示 micro.png（启用麦克风录制）
            print("DEBUG: 切换到启用状态，显示 micro.png")
            if not hasattr(self, 'micro_pixmap') or self.micro_pixmap.isNull():
                # 如果pixmap不存在或为空，重新加载
                print("DEBUG: 重新加载 micro.png")
                self.micro_pixmap = QPixmap("iconic/micro.png")
                if not self.micro_pixmap.isNull():
                    self.micro_pixmap = self.micro_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    print(f"DEBUG: micro.png 加载成功，大小: {self.micro_pixmap.width()}x{self.micro_pixmap.height()}")
                else:
                    print("DEBUG: micro.png 加载失败")
            
            if not self.micro_pixmap.isNull():
                self.microphone_icon_widget.setPixmap(self.micro_pixmap)
                # 设置透明背景，确保图标能正确显示
                self.microphone_icon_widget.setStyleSheet("background-color: transparent;")
                self.microphone_icon_widget.update()
                self.microphone_icon_widget.repaint()
                # 触发重绘事件
                QApplication.processEvents()
                print("DEBUG: 图标已更新为 micro.png")
            else:
                print("DEBUG: micro_pixmap 为空，无法更新图标")
        else:
            # 禁用状态：显示 microx.png（禁用麦克风录制）
            print("DEBUG: 切换到禁用状态，显示 microx.png")
            if not hasattr(self, 'microx_pixmap') or self.microx_pixmap.isNull():
                # 如果pixmap不存在或为空，重新加载
                print("DEBUG: 重新加载 microx.png")
                self.microx_pixmap = QPixmap("iconic/microx.png")
                if not self.microx_pixmap.isNull():
                    self.microx_pixmap = self.microx_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    print(f"DEBUG: microx.png 加载成功，大小: {self.microx_pixmap.width()}x{self.microx_pixmap.height()}")
                else:
                    print("DEBUG: microx.png 加载失败")
            
            if not self.microx_pixmap.isNull():
                self.microphone_icon_widget.setPixmap(self.microx_pixmap)
                # 设置透明背景，确保图标能正确显示
                self.microphone_icon_widget.setStyleSheet("background-color: transparent;")
                self.microphone_icon_widget.update()
                self.microphone_icon_widget.repaint()
                # 触发重绘事件
                QApplication.processEvents()
                print("DEBUG: 图标已更新为 microx.png")
            else:
                print("DEBUG: microx_pixmap 为空，无法更新图标")
    
    def toggle_audio(self):
        """切换音频（扬声器）启用/禁用状态"""
        print(f"DEBUG: toggle_audio 被调用")
        print(f"DEBUG: audio_icon_widget = {self.audio_icon_widget}")
        
        if self.audio_icon_widget is None:
            print("DEBUG: audio_icon_widget 为 None，无法切换")
            return
        
        # 切换状态
        self.audio_enabled = not self.audio_enabled
        print(f"DEBUG: 切换后状态: audio_enabled = {self.audio_enabled}")
        
        # 如果正在录制，动态控制录制线程的音频状态
        if hasattr(self, 'recording') and self.recording and hasattr(self, 'recording_thread') and self.recording_thread:
            print(f"DEBUG: 正在录制，动态控制音频状态")
            if self.recording_thread.set_audio_enabled(self.audio_enabled):
                print(f"DEBUG: 录制线程音频状态已更新: {self.audio_enabled}")
            else:
                print(f"DEBUG: 无法更新录制线程音频状态")
        
        if self.audio_enabled:
            # 启用状态：显示 speake.png（允许录制系统声音）
            print("DEBUG: 切换到启用状态，显示 speake.png")
            if not hasattr(self, 'speake_pixmap') or self.speake_pixmap.isNull():
                # 如果pixmap不存在或为空，重新加载
                print("DEBUG: 重新加载 speake.png")
                self.speake_pixmap = QPixmap("iconic/speake.png")
                if not self.speake_pixmap.isNull():
                    self.speake_pixmap = self.speake_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    print(f"DEBUG: speake.png 加载成功，大小: {self.speake_pixmap.width()}x{self.speake_pixmap.height()}")
                else:
                    print("DEBUG: speake.png 加载失败")
            
            if not self.speake_pixmap.isNull():
                self.audio_icon_widget.setPixmap(self.speake_pixmap)
                # 设置透明背景，确保图标能正确显示
                self.audio_icon_widget.setStyleSheet("background-color: transparent;")
                self.audio_icon_widget.update()
                self.audio_icon_widget.repaint()
                # 触发重绘事件
                QApplication.processEvents()
                print("DEBUG: 图标已更新为 speake.png")
            else:
                print("DEBUG: speake_pixmap 为空，无法更新图标")
        else:
            # 禁用状态：显示 speakex.png（禁止录制系统声音）
            print("DEBUG: 切换到禁用状态，显示 speakex.png")
            if not hasattr(self, 'speakex_pixmap') or self.speakex_pixmap.isNull():
                # 如果pixmap不存在或为空，重新加载
                print("DEBUG: 重新加载 speakex.png")
                self.speakex_pixmap = QPixmap("iconic/speakex.png")
                if not self.speakex_pixmap.isNull():
                    self.speakex_pixmap = self.speakex_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    print(f"DEBUG: speakex.png 加载成功，大小: {self.speakex_pixmap.width()}x{self.speakex_pixmap.height()}")
                else:
                    print("DEBUG: speakex.png 加载失败")
            
            if not self.speakex_pixmap.isNull():
                self.audio_icon_widget.setPixmap(self.speakex_pixmap)
                # 设置透明背景，确保图标能正确显示
                self.audio_icon_widget.setStyleSheet("background-color: transparent;")
                self.audio_icon_widget.update()
                self.audio_icon_widget.repaint()
                # 触发重绘事件
                QApplication.processEvents()
                print("DEBUG: 图标已更新为 speakex.png")
            else:
                print("DEBUG: speakex_pixmap 为空，无法更新图标")
    
    def show_under_development(self, feature_name):
        """显示功能正在开发中的提示窗口"""
        if self.under_development_window is None or not self.under_development_window.isVisible():
            self.under_development_window = UnderDevelopmentWindow(feature_name)
            screen = QDesktopWidget().screenGeometry()
            window_geometry = self.under_development_window.frameGeometry()
            x = (screen.width() - window_geometry.width()) // 2
            y = (screen.height() - window_geometry.height()) // 2
            self.under_development_window.move(x, y)
            self.under_development_window.show()
            self.under_development_window.raise_()
            self.under_development_window.activateWindow()
        else:
            # 如果窗口已存在，更新功能名称并显示
            self.under_development_window.feature_name = feature_name
            self.under_development_window.close()
            self.under_development_window = UnderDevelopmentWindow(feature_name)
            screen = QDesktopWidget().screenGeometry()
            window_geometry = self.under_development_window.frameGeometry()
            x = (screen.width() - window_geometry.width()) // 2
            y = (screen.height() - window_geometry.height()) // 2
            self.under_development_window.move(x, y)
            self.under_development_window.show()
            self.under_development_window.raise_()
            self.under_development_window.activateWindow()
    
    def enumerate_windows(self):
        """枚举所有可见窗口"""
        if sys.platform != 'win32':
            return []
        
        windows = []
        
        # 系统窗口标题黑名单（只排除真正的系统窗口，不排除用户应用）
        system_window_titles = [
            'Program Manager',  # Windows资源管理器
            'Desktop Window Manager',  # DWM
            'Windows Input Experience',  # 输入体验
            'Microsoft Text Input Application',  # 文本输入应用
        ]
        
        # 定义回调函数
        def enum_windows_proc(hwnd, lParam):
            # 检查窗口句柄是否有效
            if not user32.IsWindow(hwnd):
                return True
            
            # 检查窗口是否可见
            if not user32.IsWindowVisible(hwnd):
                return True
            
            # 检查窗口是否有父窗口（排除子窗口，只保留顶级窗口）
            parent = user32.GetParent(hwnd)
            if parent != 0:
                return True
            
            # 检查窗口样式，排除最小化窗口
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            if style & WS_MINIMIZE:
                return True
            
            # 检查窗口扩展样式，排除工具窗口
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # 排除工具窗口
            if ex_style & WS_EX_TOOLWINDOW:
                return True
            
            # 检查窗口是否有标题
            title_length = user32.GetWindowTextLengthW(hwnd)
            if title_length == 0:
                return True
            
            # 获取窗口标题
            title_buffer = ctypes.create_unicode_buffer(title_length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
            title = title_buffer.value
            
            # 过滤掉空标题
            if not title or title.strip() == '':
                return True
            
            # 排除系统窗口
            if title in system_window_titles:
                return True
            
            # 获取窗口矩形
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            
            # 过滤掉太小的窗口（可能是系统托盘等）
            if width < 100 or height < 100:
                return True
            
            # 检查窗口是否在屏幕范围内（排除屏幕外的窗口）
            screen = QDesktopWidget().screenGeometry()
            if (rect.right < 0 or rect.bottom < 0 or 
                rect.left > screen.width() or rect.top > screen.height()):
                return True
            
            # 检查窗口是否被其他窗口完全遮挡（简单检查：窗口是否在屏幕可见区域）
            # 这里只做基本检查，更复杂的遮挡检测需要更多API调用
            
            # 检查窗口是否属于当前进程（排除自己的窗口）
            current_pid = os.getpid()
            window_pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            # 不排除自己的窗口，因为用户可能想录制自己的窗口
            
            # 验证窗口是否真正可用（尝试获取窗口类名）
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            class_name_str = class_name.value
            
            # 排除一些系统窗口类
            system_classes = ['Shell_TrayWnd', 'Button', 'Static', 'Edit', 'ComboBox', 'ListBox']
            if class_name_str in system_classes:
                return True
            
            # 检查窗口是否挂起（使用SendMessageTimeout测试窗口响应）
            # 如果窗口在5秒内不响应，则认为窗口已挂起
            result = ctypes.c_ulong()
            try:
                # 发送WM_NULL消息测试窗口是否响应
                response = user32.SendMessageTimeoutW(
                    hwnd,
                    WM_NULL,
                    0,
                    0,
                    SMTO_ABORTIFHUNG,
                    5000,  # 5秒超时
                    ctypes.byref(result)
                )
                # 如果SendMessageTimeout返回0，说明窗口挂起或无响应
                if response == 0:
                    return True
            except:
                # 如果API调用失败，跳过该窗口
                return True
            
            # 检查窗口是否在任务栏中（通过检查窗口所有者）
            # 如果窗口有所有者且所有者不是桌面，可能是子窗口或弹出窗口
            owner = user32.GetWindow(hwnd, 4)  # GW_OWNER = 4
            if owner != 0:
                # 有所有者的窗口通常是弹出窗口或对话框，检查所有者是否可见
                if not user32.IsWindowVisible(owner):
                    return True
            
            # 使用IsIconic检查窗口是否最小化（更准确的方法）
            try:
                is_minimized = user32.IsIconic(hwnd)
                if is_minimized:
                    return True
            except:
                pass
            
            # 检查窗口是否真正在屏幕上可见
            screen = QDesktopWidget().screenGeometry()
            
            # 如果窗口完全在屏幕外，排除它
            if (rect.right <= 0 or rect.bottom <= 0 or 
                rect.left >= screen.width() or rect.top >= screen.height()):
                return True
            
            # 检查窗口是否至少有一部分在屏幕可见区域内
            visible_left = max(0, rect.left)
            visible_top = max(0, rect.top)
            visible_right = min(screen.width(), rect.right)
            visible_bottom = min(screen.height(), rect.bottom)
            
            # 如果可见区域太小（小于窗口的20%），认为窗口不可见
            visible_width = visible_right - visible_left
            visible_height = visible_bottom - visible_top
            if visible_width < width * 0.2 or visible_height < height * 0.2:
                return True
            
            # 检查窗口是否在任务栏中显示（通过检查窗口是否在任务栏区域）
            # 任务栏通常在屏幕底部，高度约40-50px
            taskbar_height = 50
            if rect.top >= screen.height() - taskbar_height and rect.height() <= taskbar_height:
                return True
            
            # 额外检查：验证窗口是否真正可用
            # 尝试获取窗口的客户端区域，如果失败说明窗口可能不可用
            try:
                client_rect = wintypes.RECT()
                if user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
                    # 如果客户端区域为0，说明窗口可能不可用
                    if client_rect.right == 0 or client_rect.bottom == 0:
                        return True
            except:
                pass
            
            windows.append({
                'handle': hwnd,
                'title': title,
                'rect': (rect.left, rect.top, width, height)
            })
            
            return True
        
        # 定义回调函数类型
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
        enum_windows_proc_ptr = EnumWindowsProc(enum_windows_proc)
        
        # 枚举所有窗口
        user32.EnumWindows(enum_windows_proc_ptr, 0)
        
        # 去重（按标题去重，保留第一个）
        seen_titles = set()
        unique_windows = []
        for window in windows:
            if window['title'] not in seen_titles:
                seen_titles.add(window['title'])
                unique_windows.append(window)
        
        return unique_windows
    
    def show_window_list_menu(self):
        """显示窗口列表菜单"""
        if sys.platform != 'win32':
            CustomMessageBox.show_message(self, '提示', '此功能仅在Windows系统上可用', 'information')
            return
        
        # 枚举所有窗口
        windows = self.enumerate_windows()
        
        if not windows:
            CustomMessageBox.show_message(self, '提示', '未找到可用的窗口', 'information')
            return
        
        # 创建菜单
        menu = RoundedMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: transparent;
                border: none;
                color: #FFFFFF;
                padding: 4px;
                max-height: 400px;
            }
            QMenu::item {
                padding: 8px 24px 8px 12px;
                border-radius: 4px;
                font-family: 'Microsoft YaHei';
                font-size: 13px;
                max-width: 300px;
            }
            QMenu::item:selected {
                background-color: #374151;
                color: #FFFFFF;
            }
        """)
        
        # 添加窗口列表项
        for window in windows:
            title = window['title']
            # 如果标题太长，截断并添加省略号
            if len(title) > 30:
                title = title[:27] + '...'
            action = QAction(title, self)
            action.setData(window)  # 保存窗口信息
            action.triggered.connect(lambda checked, w=window: self.select_window(w))
            menu.addAction(action)
        
        # 获取更多按钮的位置
        more_button = None
        for widget in self.findChildren(QPushButton):
            # 通过查找包含"更多"标签的按钮来确定
            parent = widget.parent()
            if parent:
                for child in parent.findChildren(QLabel):
                    if child.text() == '更多':
                        more_button = widget
                        break
                if more_button:
                    break
        
        if more_button:
            # 在按钮下方显示菜单
            pos = more_button.mapToGlobal(more_button.rect().bottomLeft())
            menu.exec_(pos)
        else:
            # 如果找不到按钮，在鼠标位置显示
            menu.exec_(QCursor.pos())
    
    def select_window(self, window_info):
        """选择窗口并设置录制区域"""
        self.selected_window_handle = window_info['handle']
        x, y, width, height = window_info['rect']
        
        # 设置录制模式为窗口模式
        self.recording_mode = 'window'
        self.custom_region = (x, y, width, height)
        
        # 切换到窗口录制模式（取消全屏和自定义按钮的选中状态）
        if hasattr(self, 'fullscreen_button'):
            if hasattr(self.fullscreen_button, 'is_selected'):
                self.fullscreen_button.is_selected = False
            self.fullscreen_button.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 2px solid #4B5563; "
                "border-radius: 8px; "
                "text-align: center;"
            )
        
        if hasattr(self, 'custom_button'):
            if hasattr(self.custom_button, 'is_selected'):
                self.custom_button.is_selected = False
            self.custom_button.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 2px solid #4B5563; "
                "border-radius: 8px; "
                "text-align: center;"
            )
        
        # 设置更多按钮为选中状态
        more_button = None
        for widget in self.findChildren(QPushButton):
            parent = widget.parent()
            if parent:
                for child in parent.findChildren(QLabel):
                    if child.text() == '更多':
                        more_button = widget
                        break
                if more_button:
                    break
        
        if more_button:
            more_button.is_selected = True
            more_button.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 3px solid #ff3a3a; "
                "border-radius: 8px; "
                "text-align: center;"
            )
        
        # 启动窗口跟随定时器
        self.start_window_follow()
        
        # 显示提示
        CustomMessageBox.show_message(
            self, 
            '成功', 
            f'已选择窗口：{window_info["title"]}\n录制区域已设置为该窗口', 
            'information'
        )
    
    def start_window_follow(self):
        """启动窗口跟随功能"""
        if self.selected_window_handle is None:
            return
        
        # 停止旧的定时器
        if self.window_follow_timer:
            self.window_follow_timer.stop()
        
        # 创建新的定时器，每100ms检查一次窗口位置
        self.window_follow_timer = QTimer()
        self.window_follow_timer.timeout.connect(self.update_window_region)
        self.window_follow_timer.start(100)  # 100ms更新一次
    
    def stop_window_follow(self):
        """停止窗口跟随功能"""
        if self.window_follow_timer:
            self.window_follow_timer.stop()
            self.window_follow_timer = None
    
    def update_window_region(self):
        """更新窗口区域"""
        if sys.platform != 'win32' or self.selected_window_handle is None:
            return
        
        # 检查窗口是否仍然存在
        if not user32.IsWindow(self.selected_window_handle):
            self.stop_window_follow()
            self.selected_window_handle = None
            if self.recording:
                CustomMessageBox.show_message(self, '提示', '选中的窗口已关闭，录制将继续使用最后的位置', 'warning')
            return
        
        # 检查窗口是否可见
        if not user32.IsWindowVisible(self.selected_window_handle):
            return
        
        # 获取窗口矩形
        rect = wintypes.RECT()
        if user32.GetWindowRect(self.selected_window_handle, ctypes.byref(rect)):
            x = rect.left
            y = rect.top
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            
            # 更新录制区域
            new_region = (x, y, width, height)
            if self.custom_region != new_region:
                self.custom_region = new_region
                
                # 如果正在录制，更新录制区域
                if self.recording and self.recording_thread:
                    self.recording_thread.update_region({
                        'left': x,
                        'top': y,
                        'width': width,
                        'height': height
                    })
    
    def format_time(self, seconds):
        """格式化时间为 HH:MM:SS 格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
    def update_recording_time(self):
        """更新录制时间显示 - 显示录制模式和动态时间"""
        if self.recording and not self.paused:
            self.elapsed_time = time.time() - self.start_time
            if hasattr(self, 'status_label') and self.status_label:
                mode_text = "当前为全屏录制模式" if self.recording_mode == 'fullscreen' else "当前为窗口录制模式"
                self.status_label.setText(f'{mode_text} | 录制中: {self.format_time(self.elapsed_time)}')
    
    def mouse_press_event(self, event):
        # 窗口拖动功能
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouse_move_event(self, event):
        # 窗口拖动功能
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouse_release_event(self, event):
        # 窗口拖动功能
        self.dragging = False
        
    def make_rounded_pixmap(self, image_path, radius):
        # 创建带圆角的图片
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return pixmap
        
        return self.make_rounded_pixmap_from_pixmap(pixmap, radius)
    
    def make_rounded_pixmap_from_pixmap(self, pixmap, radius):
        # 创建带圆角的图片（从已有的QPixmap对象）
        if pixmap.isNull():
            return pixmap
        
        # 创建一个新的透明图片作为目标
        rounded = QPixmap(pixmap.size())
        rounded.fill(Qt.transparent)
        
        # 创建画家并设置抗锯齿
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 创建圆角矩形路径
        path = QPainterPath()
        path.addRoundedRect(0, 0, pixmap.width(), pixmap.height(), radius, radius)
        
        # 设置裁剪路径
        painter.setClipPath(path)
        
        # 绘制图片
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        
        return rounded
    
    def show_custom_region_selector(self):
        """显示自定义区域选择器"""
        print("DEBUG: 显示自定义区域选择器")  # 添加调试信息
        
        # 确保在主线程中创建和显示窗口
        if QThread.currentThread() != QApplication.instance().thread():
            print("DEBUG: 在非主线程，切换到主线程显示")
            QTimer.singleShot(0, self.show_custom_region_selector)
            return
            
        # 清理之前可能存在的选择器实例
        if hasattr(self, 'region_selector') and self.region_selector:
            print("DEBUG: 清理旧的区域选择器实例")
            try:
                # 先断开所有信号连接，避免触发按钮状态取消
                try:
                    self.region_selector.window_closing.disconnect()
                    self.region_selector.region_selected.disconnect()
                    self.region_selector.destroyed.disconnect()
                except:
                    pass  # 如果信号未连接，忽略错误
                # 隐藏窗口并删除
                self.region_selector.hide()
                self.region_selector.setParent(None)  # 移除父窗口关系
                self.region_selector.deleteLater()
            except Exception as e:
                print(f"DEBUG: 清理实例时出错: {e}")
            self.region_selector = None
            
        # 创建新的区域选择器 - 不设置父窗口以确保全屏正常工作
        print("DEBUG: 创建新的区域选择器实例")
        self.region_selector = RegionSelectorWindow()
        
        # 重新设置窗口标志以确保正确显示
        self.region_selector.setWindowFlags(Qt.FramelessWindowHint | 
                                          Qt.WindowStaysOnTopHint | 
                                          Qt.SplashScreen)
        
        # 连接信号槽
        self.region_selector.region_selected.connect(self.on_region_selected)
        
        # 连接窗口关闭信号，关闭时取消按钮选中状态并清空区域
        def on_window_closing():
            print("DEBUG: 区域选择器窗口正在关闭")
            # 取消自定义按钮的选中状态
            if hasattr(self, 'custom_button') and self.custom_button:
                # 恢复按钮默认样式
                self.custom_button.setStyleSheet(
                    "background-color: #2d2d38; "
                    "border: 2px solid #4B5563; "
                    "border-radius: 8px; "
                    "text-align: center;"
                )
                self.custom_button.is_selected = False
                print("DEBUG: 窗口关闭时，取消自定义按钮选中状态")
            # 清空已选择的区域
            self.custom_region = None
            print("DEBUG: 窗口关闭时，清空已选择的区域")
            # 如果区域被清空，恢复状态栏为窗口模式
            if hasattr(self, 'status_label') and self.status_label:
                if not (hasattr(self, 'recording') and self.recording):
                    self.status_label.setText('当前窗口模式 | 就绪')
                    self.status_label.setStyleSheet(
                        "color: #D1D5DB; "
                        "font-family: 'Microsoft YaHei'; "
                        "font-size: 13px; "
                        "background-color: transparent;"
                    )
        
        self.region_selector.window_closing.connect(on_window_closing)
        
        # 添加调试信号连接
        def on_window_closed():
            print("DEBUG: 区域选择器窗口已关闭")
            
        self.region_selector.destroyed.connect(on_window_closed)
        
        # 设置录制状态和设置选项
        is_recording = getattr(self, 'recording', False)
        allow_move = False
        if hasattr(self, 'settings_window') and self.settings_window:
            if hasattr(self.settings_window, 'allow_click_region_check'):
                allow_move = self.settings_window.allow_click_region_check.isChecked()
        self.region_selector.set_recording_state(is_recording, allow_move)
        
        # 显示区域选择器 - 使用showFullScreen确保全屏覆盖所有显示器
        print("DEBUG: 使用showFullScreen()显示区域选择器")
        self.region_selector.showFullScreen()
        self.region_selector.raise_()
        self.region_selector.activateWindow()
        print("DEBUG: 区域选择器窗口显示请求已发送")
    
    def _apply_pending_region_update(self):
        """应用待更新的区域（防抖机制）"""
        if self.pending_region_update and hasattr(self, 'recording_thread') and self.recording_thread:
            recording_region = self.pending_region_update
            self.pending_region_update = None
            
            # 更新录制线程的区域
            if hasattr(self.recording_thread, 'update_region'):
                print(f"DEBUG: 应用区域更新: {recording_region}")
                self.recording_thread.update_region(recording_region)
                # 保存当前区域，用于下次判断是否只是位置改变
                self.last_recording_region = recording_region.copy()
            else:
                print(f"DEBUG: 警告：录制线程没有update_region方法")
    
    def on_region_selected(self, region):
        """区域选择完成回调"""
        self.custom_region = region
        print(f"DEBUG: 选择的录制区域: {region}")
        
        # 更新状态栏 - 区域选择完成后显示窗口模式和就绪状态
        if hasattr(self, 'status_label') and self.status_label:
            if not (hasattr(self, 'recording') and self.recording):
                self.status_label.setText('当前为窗口录制模式 | 就绪')
                self.status_label.setStyleSheet(
                    "color: #D1D5DB; "
                    "font-family: 'Microsoft YaHei'; "
                    "font-size: 13px; "
                    "background-color: transparent;"
                )
                print(f"DEBUG: 状态栏已更新为窗口模式（区域已选择）")
            else:
                print(f"DEBUG: 正在录制中，不更新状态栏")
        else:
            print(f"DEBUG: 状态栏不存在，hasattr: {hasattr(self, 'status_label')}, status_label: {getattr(self, 'status_label', 'N/A')}")
        
        # 如果在录制过程中移动了窗口或改变了大小时，需要更新录制区域
        if hasattr(self, 'recording') and self.recording and hasattr(self, 'recording_thread') and self.recording_thread:
            # 将区域转换为字典格式（与录制线程使用的格式一致）
            x, y, width, height = region
            # 将录制区域向内收缩2像素（虚线边框宽度），避免录制到虚线框
            border_width = 2
            if width > border_width * 2 and height > border_width * 2:
                recording_region = {
                    'top': y + border_width,
                    'left': x + border_width,
                    'width': width - border_width * 2,
                    'height': height - border_width * 2
                }
                # 使用防抖机制：保存待更新的区域，延迟200毫秒后更新（减少延迟以更快响应）
                # 检查是否只是位置改变（移动）还是大小也改变了（调整大小）
                old_region = getattr(self, 'last_recording_region', None)
                is_only_position_change = False
                if old_region:
                    is_only_position_change = (
                        old_region.get('width') == recording_region['width'] and
                        old_region.get('height') == recording_region['height'] and
                        (old_region.get('left') != recording_region['left'] or
                         old_region.get('top') != recording_region['top'])
                    )
                
                # 如果只是位置改变（移动），使用更短的延迟（100ms）以更快响应
                # 如果是大小改变，使用稍长的延迟（200ms）以避免频繁调整
                delay = 100 if is_only_position_change else 200
                
                self.pending_region_update = recording_region
                self.region_update_timer.stop()  # 停止之前的定时器
                self.region_update_timer.start(delay)  # 延迟后更新
                print(f"DEBUG: 区域改变（{'移动' if is_only_position_change else '调整大小'}），将在{delay}ms后更新录制区域: {recording_region}")
        
        # 确认录制模式和按钮状态
        print(f"DEBUG: 当前录制模式: {self.recording_mode}")
        if hasattr(self, 'custom_button'):
            selected = getattr(self.custom_button, 'is_selected', False)
            print(f"DEBUG: 自定义按钮选中状态: {selected}")
        # 显示消息确认选择完成（仅在非录制状态时显示）
        if not (hasattr(self, 'recording') and self.recording):
            if hasattr(self, 'show_message'):
                try:
                    self.show_message(f"已选择录制区域: {region[2]}x{region[3]}px")
                except:
                    pass
    
    def start_screen_recording(self):
        """开始屏幕录制"""
        try:
            # 获取输出路径（优先使用设置中的路径）
            if hasattr(self, 'settings_window') and self.settings_window:
                if hasattr(self.settings_window, 'output_path_edit'):
                    output_dir = self.settings_window.output_path_edit.text()
                    if output_dir and os.path.exists(output_dir):
                        recordings_dir = output_dir
                    else:
                        recordings_dir = self.recordings_dir
                else:
                    recordings_dir = self.recordings_dir
            else:
                recordings_dir = self.recordings_dir
            
            # 确保目录存在
            if not os.path.exists(recordings_dir):
                try:
                    os.makedirs(recordings_dir)
                    print(f"DEBUG: 开始录制时自动创建目录: {recordings_dir}")
                except Exception as e:
                    error_msg = f'无法创建保存目录：{recordings_dir}\n\n错误：{str(e)}\n\n请检查目录权限或选择其他目录。'
                    print(f"DEBUG: 创建录制目录失败: {e}")
                    CustomMessageBox.show_message(self, '错误', error_msg, 'critical')
                    return
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            video_format = 'mp4'
            if hasattr(self, 'settings_window') and self.settings_window:
                if hasattr(self.settings_window, 'video_format_combo'):
                    format_text = self.settings_window.video_format_combo.currentText()
                    video_format = format_text.lower().split()[0] if format_text else 'mp4'
            
            filename = f'recording_{timestamp}.{video_format}'
            filepath = os.path.join(recordings_dir, filename)
            
            print(f"DEBUG: 文件保存路径: {filepath}")
            
            # 确定录制区域
            if self.recording_mode == 'fullscreen':
                # 全屏录制
                screen = QDesktopWidget().screenGeometry()
                region = {'top': 0, 'left': 0, 'width': screen.width(), 'height': screen.height()}
            else:
                # 自定义区域
                if self.custom_region:
                    x, y, width, height = self.custom_region
                    # 将录制区域向内收缩2像素（虚线边框宽度），避免录制到虚线框
                    border_width = 2  # 虚线框的宽度
                    # 确保收缩后区域仍然有效（至少保留最小尺寸）
                    if width > border_width * 2 and height > border_width * 2:
                        region = {
                            'top': y + border_width,
                            'left': x + border_width,
                            'width': width - border_width * 2,
                            'height': height - border_width * 2
                        }
                    else:
                        # 如果区域太小，使用原始区域（不收缩）
                        region = {'top': y, 'left': x, 'width': width, 'height': height}
                        print(f"DEBUG: 警告：录制区域太小 ({width}x{height})，无法收缩虚线框")
                else:
                    CustomMessageBox.show_message(self, '错误', '未选择自定义录制区域！', 'warning')
                    return
            
            # 获取设置选项
            quality = '高质量'
            audio_quality = '高音质'
            show_cursor = True
            camera_device = None
            camera_enabled = False
            
            if hasattr(self, 'settings_window') and self.settings_window:
                if hasattr(self.settings_window, 'quality_combo'):
                    quality = self.settings_window.quality_combo.currentText()
                if hasattr(self.settings_window, 'audio_quality_combo'):
                    audio_quality = self.settings_window.audio_quality_combo.currentText()
                if hasattr(self.settings_window, 'show_cursor_check'):
                    show_cursor = self.settings_window.show_cursor_check.isChecked()
            
            # 获取摄像头设备（只要摄像头预览窗口打开就自动启用录制）
            camera_device = None
            camera_enabled = False
            # 只要摄像头预览窗口打开，就自动启用摄像头录制
            if hasattr(self, 'camera_preview_window') and self.camera_preview_window is not None and self.camera_preview_window.isVisible():
                # 摄像头预览窗口已打开，获取选中的摄像头设备
                if hasattr(self, 'camera_combo') and self.camera_combo:
                    camera_device = self.camera_combo.currentText()
                    print(f"DEBUG: 摄像头预览窗口已打开，自动启用摄像头录制，设备: {camera_device}")
                    if camera_device and camera_device != '无':
                        camera_enabled = True
                    else:
                        # 如果未选择设备，尝试使用第一个可用设备
                        if hasattr(self, 'cameras') and self.cameras:
                            camera_device = self.cameras[0]
                            camera_enabled = True
                            print(f"DEBUG: 未选择设备，使用第一个可用设备: {camera_device}")
                        else:
                            camera_enabled = False
                            print(f"DEBUG: 摄像头预览窗口已打开，但未找到可用设备")
                else:
                    camera_enabled = False
                    print(f"DEBUG: 摄像头预览窗口已打开，但camera_combo不存在")
            else:
                camera_enabled = False
                print(f"DEBUG: 摄像头预览窗口未打开，不录制摄像头")
            
            # 获取麦克风设备
            microphone_device = self.get_selected_microphone()
            print(f"DEBUG: 开始录制 - microphone_enabled={self.microphone_enabled}, microphone_device={microphone_device}")
            print(f"DEBUG: microphone_combo存在: {hasattr(self, 'microphone_combo') and self.microphone_combo is not None}")
            if hasattr(self, 'microphone_combo') and self.microphone_combo:
                print(f"DEBUG: microphone_combo当前文本: {self.microphone_combo.currentText()}")
            
            # 创建录屏线程
            self.recording_thread = RecordingThread(
                region=region,
                filepath=filepath,
                fps=self.recording_fps,
                microphone_enabled=self.microphone_enabled,
                audio_enabled=self.audio_enabled,
                microphone_device=microphone_device,
                audio_device=self.get_selected_audio_output(),
                quality=quality,
                audio_quality=audio_quality,
                show_cursor=show_cursor,
                camera_device=camera_device if camera_enabled else None,
                camera_enabled=camera_enabled
            )
            
            # 连接录制失败信号
            self.recording_thread.recording_failed.connect(self.on_recording_failed)
            
            # 隐藏区域选择器的关闭按钮并更新录制状态（虚线框仍然可见）
            if hasattr(self, 'region_selector') and self.region_selector:
                self.region_selector.set_show_close_button(False)
                # 获取设置选项：直接从config.json读取（配置文件是最终来源）
                allow_move = self.get_allow_move_from_config()
                print(f"DEBUG: 允许在录制过程中移动录制区域: {allow_move}")
                # 设置录制状态（虚线框仍然显示，但录制区域已向内收缩，不会录制到虚线）
                self.region_selector.set_recording_state(True, allow_move)
            
            self.recording_thread.start()
            
            # 保存文件路径供后续使用
            self.current_recording_filepath = filepath
            
            print(f"DEBUG: 开始录制 - 模式: {self.recording_mode}, 区域: {region}, 文件: {filepath}")
            print(f"DEBUG: 文件将保存到: {recordings_dir}")
            
        except Exception as e:
            CustomMessageBox.show_message(self, '错误', f'开始录制失败: {str(e)}', 'critical')
            print(f"DEBUG: 录制失败: {e}")
            import traceback
            traceback.print_exc()
    
    def on_recording_failed(self, error_msg):
        """处理录制失败"""
        print(f"DEBUG: 录制失败，错误信息: {error_msg}")
        
        # 显示错误提示窗口
        CustomMessageBox.show_message(self, '录制失败', error_msg, 'critical')
        
        # 清理录制线程
        if hasattr(self, 'recording_thread') and self.recording_thread:
            try:
                self.recording_thread.stop()
                self.recording_thread.wait(1000)  # 等待1秒
            except:
                pass
            self.recording_thread = None
        
        # 重置录制状态
        if hasattr(self, 'recording') and self.recording:
            self.recording = False
        
        # 恢复区域选择器的关闭按钮显示并更新录制状态
        if hasattr(self, 'region_selector') and self.region_selector:
            self.region_selector.set_show_close_button(True)
            self.region_selector.set_recording_state(False, False)
        
        # 清理文件路径
        if hasattr(self, 'current_recording_filepath'):
            self.current_recording_filepath = None
        
        print("DEBUG: 录制失败处理完成，已重置所有状态")
    
    def stop_screen_recording(self):
        """停止屏幕录制"""
        # 停止窗口跟随
        self.stop_window_follow()
        
        if self.recording_thread:
            # 更新状态栏显示处理中
            if hasattr(self, 'status_label') and self.status_label:
                mode_text = '全屏录制模式' if self.recording_mode == 'fullscreen' else '窗口录制模式'
                self.status_label.setText(f'{mode_text} | 录制结束，视频处理中...')
                self.status_label.setStyleSheet(
                    "color: #60A5FA; "
                    "font-family: 'Microsoft YaHei'; "
                    "font-size: 12px; "
                    "font-weight: 500;"
                )
                QApplication.processEvents()
            
            # 连接视频处理完成信号（如果还没有连接）
            try:
                # 先断开可能存在的旧连接，避免重复连接
                try:
                    self.recording_thread.video_processing_complete.disconnect()
                except:
                    pass
                self.recording_thread.video_processing_complete.connect(self.on_video_processing_complete)
                
                # 连接合并进度信号
                try:
                    self.recording_thread.merge_progress.disconnect()
                except:
                    pass
                self.recording_thread.merge_progress.connect(self.on_merge_progress)
            except Exception as connect_error:
                print(f"DEBUG: 连接信号时出错: {connect_error}")
                import traceback
                traceback.print_exc()
            
            # 停止录制线程
            try:
                self.recording_thread.stop()
            except Exception as stop_error:
                print(f"DEBUG: 停止录制线程时出错: {stop_error}")
                import traceback
                traceback.print_exc()
            
            # 等待录制线程完全结束（包括音频合并）
            # 使用较长的超时时间，确保音频合并完成
            try:
                if not self.recording_thread.wait(300000):  # 最多等待5分钟
                    print("DEBUG: 警告：等待录制线程结束超时")
            except Exception as wait_error:
                print(f"DEBUG: 等待线程结束时出错: {wait_error}")
                import traceback
                traceback.print_exc()
            
            # 恢复区域选择器的关闭按钮显示并更新录制状态
            if hasattr(self, 'region_selector') and self.region_selector:
                self.region_selector.set_show_close_button(True)
                self.region_selector.set_recording_state(False, False)
            
            print("DEBUG: 录制已停止，视频处理中...")
    
    def on_merge_progress(self, message, current, total):
        """合并进度回调（在主线程中执行）"""
        try:
            if hasattr(self, 'status_label') and self.status_label:
                mode_text = '全屏录制模式' if self.recording_mode == 'fullscreen' else '窗口录制模式'
                # 显示进度百分比
                progress_percent = int((current / total * 100)) if total > 0 else 0
                self.status_label.setText(f'{mode_text} | {message} ({progress_percent}%)')
                self.status_label.setStyleSheet(
                    "color: #60A5FA; "
                    "font-family: 'Microsoft YaHei'; "
                    "font-size: 12px; "
                    "font-weight: 500;"
                )
                QApplication.processEvents()  # 立即更新UI
        except Exception as e:
            print(f"DEBUG: 更新合并进度失败: {e}")
    
    def on_video_processing_complete(self, filepath, file_size):
        """视频处理完成回调（在主线程中执行）"""
        try:
            print(f"DEBUG: 视频处理完成，文件已保存: {filepath}")
            print(f"DEBUG: 文件大小: {file_size} 字节 ({file_size / 1024 / 1024:.2f} MB)")
            
            # 更新状态栏
            if hasattr(self, 'status_label') and self.status_label:
                try:
                    mode_text = '全屏录制模式' if self.recording_mode == 'fullscreen' else '窗口录制模式'
                    self.status_label.setText(f'{mode_text} | 就绪')
                    self.status_label.setStyleSheet(
                        "color: #9CA3AF; "
                        "font-family: 'Microsoft YaHei'; "
                        "font-size: 12px; "
                        "font-weight: 500;"
                    )
                except Exception as status_error:
                    print(f"DEBUG: 更新状态栏失败: {status_error}")
                    import traceback
                    traceback.print_exc()
            
            # 显示完成提示 - 使用QTimer延迟显示，确保在主线程中执行
            def show_completion_message():
                try:
                    # 确保文件路径存在
                    if filepath and os.path.exists(filepath):
                        file_size_mb = file_size / 1024 / 1024
                        CustomMessageBox.show_message(
                            self, 
                            '录制完成', 
                            f'录制已完成！\n\n文件保存位置：\n{filepath}\n\n文件大小：{file_size_mb:.2f} MB',
                            'information'
                        )
                    else:
                        # 如果文件不存在，显示警告
                        CustomMessageBox.show_message(
                            self, 
                            '录制完成', 
                            f'录制已完成！\n\n注意：文件可能未正确保存。\n预期位置：\n{filepath}',
                            'warning'
                        )
                except Exception as msg_error:
                    print(f"DEBUG: 显示完成提示失败: {msg_error}")
                    import traceback
                    traceback.print_exc()
            
            # 使用QTimer延迟显示，确保UI更新完成
            QTimer.singleShot(100, show_completion_message)
            
        except Exception as e:
            print(f"DEBUG: 视频处理完成回调出错: {e}")
            import traceback
            traceback.print_exc()
        
        # 清理录制线程（确保线程已经完全结束）
        # 注意：不要在这里立即清理线程，因为线程可能还在处理中
        # 线程清理应该在stop_screen_recording中完成
        # 这里只断开信号连接，避免重复调用
        try:
            if self.recording_thread:
                # 断开信号连接，避免重复触发
                try:
                    self.recording_thread.video_processing_complete.disconnect(self.on_video_processing_complete)
                except:
                    pass
        except Exception as cleanup_error:
            print(f"DEBUG: 断开信号连接时出错: {cleanup_error}")
            import traceback
            traceback.print_exc()
    
    def get_selected_microphone(self):
        """获取选中的麦克风设备"""
        print(f"DEBUG: get_selected_microphone - 检查microphone_combo: hasattr={hasattr(self, 'microphone_combo')}, value={getattr(self, 'microphone_combo', 'N/A')}")
        if hasattr(self, 'microphone_combo') and self.microphone_combo:
            device_name = self.microphone_combo.currentText()
            print(f"DEBUG: get_selected_microphone - 下拉菜单文本: {device_name}")
            if device_name and device_name != '无':
                print(f"DEBUG: get_selected_microphone - 返回设备: {device_name}")
                return device_name
            else:
                print(f"DEBUG: get_selected_microphone - 未选择设备或选择了'无'")
        else:
            print(f"DEBUG: get_selected_microphone - microphone_combo不存在或为None")
            # 尝试从所有下拉菜单中查找麦克风下拉菜单
            print(f"DEBUG: 尝试查找麦克风下拉菜单...")
            # 检查是否有其他方式可以获取麦克风设备
        return None
    
    def get_selected_audio_output(self):
        """获取选中的音频输出设备"""
        if self.audio_combo:
            device_name = self.audio_combo.currentText()
            if device_name and device_name != '无':
                return device_name
        return None
    
    def get_allow_move_from_config(self):
        """介config.json读取是否允许在录制过程中移动录制区域"""
        config_dir = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', '灵感录屏工具')
        config_file = os.path.join(config_dir, 'config.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                allow_move = settings.get('allow_click_region', False)
                print(f"DEBUG: 从config.json读取allow_click_region: {allow_move}")
                return allow_move
            except Exception as e:
                print(f"DEBUG: 读取config.json失败: {e}")
        return False
    
    def register_global_hotkeys(self):
        """注册全局快捷键"""
        if not HAS_PYNPUT:
            print("DEBUG: pynput未安装，无法使用全局快捷键")
            return
        
        # 停止旧的监听器（如果存在）
        self.unregister_global_hotkeys()
        
        # 读取配置文件中的快捷键设置
        config_dir = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', '灵感录屏工具')
        config_file = os.path.join(config_dir, 'config.json')
        hotkeys = {
            'hotkey_start': 'F9',
            'hotkey_stop': 'F10',
            'hotkey_pause': 'F11',
            'hotkey_toggle': 'Ctrl+F12'  # 默认改为Ctrl+F12
        }
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                hotkeys.update({
                    'hotkey_start': settings.get('hotkey_start', 'F9'),
                    'hotkey_stop': settings.get('hotkey_stop', 'F10'),
                    'hotkey_pause': settings.get('hotkey_pause', 'F11'),
                    'hotkey_toggle': settings.get('hotkey_toggle', 'Ctrl+F12')
                })
            except Exception as e:
                print(f"DEBUG: 读取快捷键配置失败: {e}")
        
        # 解析快捷键字符串并注册
        try:
            hotkey_dict = {}
            
            # 解析开始录制快捷键
            start_key = self._parse_hotkey(hotkeys['hotkey_start'])
            if start_key:
                hotkey_dict[start_key] = self._on_hotkey_start
                print(f"DEBUG: 解析开始录制快捷键: {hotkeys['hotkey_start']} -> {start_key}")
            else:
                print(f"DEBUG: 警告：无法解析开始录制快捷键: {hotkeys['hotkey_start']}")
            
            # 解析停止录制快捷键
            stop_key = self._parse_hotkey(hotkeys['hotkey_stop'])
            if stop_key:
                hotkey_dict[stop_key] = self._on_hotkey_stop
                print(f"DEBUG: 解析停止录制快捷键: {hotkeys['hotkey_stop']} -> {stop_key}")
            else:
                print(f"DEBUG: 警告：无法解析停止录制快捷键: {hotkeys['hotkey_stop']}")
            
            # 解析暂停录制快捷键
            pause_key = self._parse_hotkey(hotkeys['hotkey_pause'])
            if pause_key:
                hotkey_dict[pause_key] = self._on_hotkey_pause
                print(f"DEBUG: 解析暂停录制快捷键: {hotkeys['hotkey_pause']} -> {pause_key}")
            else:
                print(f"DEBUG: 警告：无法解析暂停录制快捷键: {hotkeys['hotkey_pause']}")
            
            # 解析显示/隐藏窗口快捷键
            toggle_key = self._parse_hotkey(hotkeys['hotkey_toggle'])
            if toggle_key:
                hotkey_dict[toggle_key] = self._on_hotkey_toggle
                print(f"DEBUG: 解析显示/隐藏窗口快捷键: {hotkeys['hotkey_toggle']} -> {toggle_key}")
            else:
                print(f"DEBUG: 警告：无法解析显示/隐藏窗口快捷键: {hotkeys['hotkey_toggle']}")
            
            if hotkey_dict:
                # 创建全局快捷键监听器
                self.hotkey_listener = keyboard.GlobalHotKeys(hotkey_dict)
                self.hotkey_listener.start()
                print(f"DEBUG: 全局快捷键已注册: {list(hotkey_dict.keys())}")
            else:
                print("DEBUG: 没有有效的快捷键可注册")
        except Exception as e:
            print(f"DEBUG: 注册全局快捷键失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _parse_hotkey(self, hotkey_str):
        """解析快捷键字符串，返回pynput GlobalHotKeys格式的字符串"""
        if not hotkey_str:
            return None
        
        try:
            # pynput的GlobalHotKeys需要字符串格式，例如: '<ctrl>+<f12>', '<f9>'
            # 将QKeySequence格式转换为pynput格式
            parts = hotkey_str.upper().split('+')
            key_parts = []
            
            for part in parts:
                part = part.strip()
                if part == 'CTRL':
                    key_parts.append('<ctrl>')
                elif part == 'ALT':
                    key_parts.append('<alt>')
                elif part == 'SHIFT':
                    key_parts.append('<shift>')
                elif part == 'WIN' or part == 'META':
                    key_parts.append('<cmd>')
                elif part.startswith('F'):
                    # 功能键 F1-F12
                    try:
                        f_num = int(part[1:])
                        if 1 <= f_num <= 12:
                            key_parts.append(f'<f{f_num}>')
                    except:
                        pass
                else:
                    # 普通按键，直接使用（小写）
                    key_parts.append(part.lower())
            
            if key_parts:
                return '+'.join(key_parts)
            else:
                return None
        except Exception as e:
            print(f"DEBUG: 解析快捷键失败 {hotkey_str}: {e}")
            return None
    
    def unregister_global_hotkeys(self):
        """取消注册全局快捷键"""
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
                self.hotkey_listener = None
                print("DEBUG: 全局快捷键已取消注册")
            except Exception as e:
                print(f"DEBUG: 取消注册全局快捷键失败: {e}")
    
    def _on_hotkey_start(self):
        """开始录制快捷键处理"""
        # 在主线程中执行，使用QTimer.singleShot确保线程安全
        QTimer.singleShot(0, self._trigger_start_recording)
    
    def _on_hotkey_stop(self):
        """停止录制快捷键处理"""
        QTimer.singleShot(0, self._trigger_stop_recording)
    
    def _on_hotkey_pause(self):
        """暂停录制快捷键处理"""
        QTimer.singleShot(0, self._trigger_pause_recording)
    
    def _on_hotkey_toggle(self):
        """显示/隐藏窗口快捷键处理"""
        QTimer.singleShot(0, self._trigger_toggle_window)
    
    def _trigger_start_recording(self):
        """触发开始录制（在主线程中执行）"""
        print("DEBUG: 快捷键触发开始录制")
        if not self.recording:
            if hasattr(self, 'start_button') and self.start_button:
                print("DEBUG: 通过快捷键触发开始按钮点击")
                self.start_button.click()
            else:
                print("DEBUG: 警告：开始按钮不存在")
        else:
            print("DEBUG: 已经在录制中，忽略开始录制快捷键")
    
    def _trigger_stop_recording(self):
        """触发停止录制（在主线程中执行）"""
        print("DEBUG: 快捷键触发停止录制")
        if self.recording:
            if hasattr(self, 'stop_button') and self.stop_button:
                print("DEBUG: 通过快捷键触发停止按钮点击")
                self.stop_button.click()
            else:
                print("DEBUG: 警告：停止按钮不存在")
        else:
            print("DEBUG: 未在录制中，忽略停止录制快捷键")
    
    def _trigger_pause_recording(self):
        """触发暂停录制（在主线程中执行）"""
        print("DEBUG: 快捷键触发暂停录制")
        if self.recording:
            if hasattr(self, 'pause_button') and self.pause_button:
                print("DEBUG: 通过快捷键触发暂停按钮点击")
                self.pause_button.click()
            else:
                print("DEBUG: 警告：暂停按钮不存在")
        else:
            print("DEBUG: 未在录制中，忽略暂停录制快捷键")
    
    def _trigger_toggle_window(self):
        """触发显示/隐藏窗口（在主线程中执行）"""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
    
    def closeEvent(self, event):
        """窗口关闭事件 - 关闭所有子窗口并清理资源"""
        # 如果正在录制，阻止关闭并提示用户
        if self.recording:
            print("DEBUG: 关闭主窗口时检测到正在录制，阻止关闭")
            CustomMessageBox.show_message(
                self, 
                '提示', 
                '正在录制中，请先停止录制后再退出程序！', 
                'warning'
            )
            event.ignore()  # 阻止关闭
            return
        
        # 停止窗口跟随
        self.stop_window_follow()
        
        # 关闭所有子窗口
        if hasattr(self, 'settings_window') and self.settings_window:
            try:
                self.settings_window.close()
                print("DEBUG: 已关闭设置窗口")
            except Exception as e:
                print(f"DEBUG: 关闭设置窗口时出错: {e}")
        
        if hasattr(self, 'about_window') and self.about_window:
            try:
                self.about_window.close()
                print("DEBUG: 已关闭关于窗口")
            except Exception as e:
                print(f"DEBUG: 关闭关于窗口时出错: {e}")
        
        if hasattr(self, 'file_list_window') and self.file_list_window:
            try:
                self.file_list_window.close()
                print("DEBUG: 已关闭文件列表窗口")
            except Exception as e:
                print(f"DEBUG: 关闭文件列表窗口时出错: {e}")
        
        if hasattr(self, 'camera_preview_window') and self.camera_preview_window:
            try:
                self.camera_preview_window.close()
                print("DEBUG: 已关闭摄像头预览窗口")
            except Exception as e:
                print(f"DEBUG: 关闭摄像头预览窗口时出错: {e}")
        
        if hasattr(self, 'under_development_window') and self.under_development_window:
            try:
                self.under_development_window.close()
                print("DEBUG: 已关闭开发中功能窗口")
            except Exception as e:
                print(f"DEBUG: 关闭开发中功能窗口时出错: {e}")
        
        # 关闭区域选择窗口（如果存在）
        if hasattr(self, 'region_selector') and self.region_selector:
            try:
                self.region_selector.close()
                print("DEBUG: 已关闭区域选择窗口")
            except Exception as e:
                print(f"DEBUG: 关闭区域选择窗口时出错: {e}")
        
        # 清理所有FFmpeg进程（如果存在recording_thread对象）
        if hasattr(self, 'recording_thread') and self.recording_thread:
            try:
                print("DEBUG: 清理所有FFmpeg进程...")
                # RecordingThread 本身就有 _cleanup_all_ffmpeg_processes 方法
                if hasattr(self.recording_thread, '_cleanup_all_ffmpeg_processes'):
                    self.recording_thread._cleanup_all_ffmpeg_processes()
            except Exception as e:
                print(f"DEBUG: 清理FFmpeg进程时出错: {e}")
                import traceback
                traceback.print_exc()
        
        # 取消注册全局快捷键
        self.unregister_global_hotkeys()
        
        # 停止定时器
        if hasattr(self, 'timer') and self.timer:
            try:
                self.timer.stop()
            except:
                pass
        
        if hasattr(self, 'region_update_timer') and self.region_update_timer:
            try:
                self.region_update_timer.stop()
            except:
                pass
        
        event.accept()
    
    def apply_button_selected_style(self, button):
        """为按钮应用选择状态的红色动态效果"""
        # 通用的红色选择效果
        # 全屏按钮选择样式
        if button.width() == 112 and button.height() == 112:
            button.setStyleSheet(
                "background-color: #2d2d38; "
                "border: 3px solid #ff3a3a; "  # 加粗的红色边框作为选中效果
                "border-radius: 8px; "
                "text-align: center;"
            )
        # 更多按钮选择样式 - 现在与全屏按钮尺寸相同，使用相同的选中样式
        # 这里不再需要单独判断，因为已经包含在112x112的条件中
        # 录制按钮选择样式
        elif button.width() == 128 and button.height() == 128:
            # 切换录制按钮的文本和样式（开始/停止）
            if button.text() == '停止录制':
                button.setText('开始录制')
                button.setStyleSheet(
                    "background-color: #EF4444; "  # 停止时为红色
                    "color: #FFFFFF; "
                    "font-family: 'Microsoft YaHei'; "
                    "font-size: 18px; "
                    "font-weight: 600; "
                    "border: 3px solid #ff3a3a; "  # 加粗的红色边框作为选中效果
                    "border-radius: 12px; "
                    "border-style: outset; "
                    "border-width: 3px;"
                )
            else:
                button.setText('停止录制')
                button.setStyleSheet(
                    "background-color: #16A34A; "  # 开始时为绿色
                    "color: #FFFFFF; "
                    "font-family: 'Microsoft YaHei'; "
                    "font-size: 18px; "
                    "font-weight: 600; "
                    "border: 3px solid #ff3a3a; "  # 加粗的红色边框作为选中效果
                    "border-radius: 12px; "
                    "border-style: outset; "
                    "border-width: 3px;"
                )

if __name__ == '__main__':
    # 抑制OpenCV的警告信息
    import os
    os.environ['OPENCV_LOG_LEVEL'] = 'ERROR'  # 只显示错误，不显示警告
    
    # 创建应用程序实例
    app = QApplication(sys.argv)
    
    # 设置融合风格以确保跨平台一致性
    app.setStyle('Fusion')
    
    # 设置全局样式以确保深色主题
    app.setStyleSheet("QWidget { background-color: #1F2937; color: #F9FAFB; }")
    
    # 确保使用正确的字体
    font = app.font()
    font.setFamily('Microsoft YaHei')
    font.setPointSize(9)
    app.setFont(font)
    
    # 创建并显示启动窗口
    splash = SplashScreen()
    splash.show()
    QApplication.processEvents()  # 立即显示启动窗口
    
    # 创建主窗口（传入启动窗口以便更新信息）
    window = TruePixelPerfectUI(splash)
    
    # 关闭启动窗口
    splash.close()
    
    # 显示主窗口
    window.show()
    window.raise_()  # 确保窗口在最前面
    window.activateWindow()  # 激活窗口
    
    # 运行应用程序
    sys.exit(app.exec_())
