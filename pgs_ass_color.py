import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import xml.etree.ElementTree as ET
import cv2
import numpy as np
from pathlib import Path
import json
import re
from typing import Dict, List, Optional, Tuple, Union
import logging
import codecs
from collections import defaultdict
import os
import datetime
import ass
from PIL import Image, ImageTk
import threading
import queue
from ttkthemes import ThemedTk


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put(("log", msg))

class PGSColorAnalyzer:
    def __init__(self, queue=None):
        self.framerate = 23.976
        self.logger = logging.getLogger(__name__)
        self.queue = queue

    def update_progress(self, progress):
        if self.queue:
            self.queue.put(("progress", progress))

    def timecode_to_seconds(self, timecode: str) -> float:
        hours, minutes, seconds, frames = map(int, timecode.split(':'))
        total_seconds = hours * 3600 + minutes * 60 + seconds + frames / self.framerate
        return total_seconds

    def seconds_to_ass_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        return f"{hours:d}:{minutes:02d}:{seconds:02.2f}"

    def extract_outline_color(self, image: np.ndarray) -> Tuple[str, float]:
        try:
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            lower_white = np.array([0, 0, 180])
            upper_white = np.array([180, 30, 255])
            white_mask = cv2.inRange(hsv, lower_white, upper_white)
            kernel = np.ones((5,5), np.uint8)
            dilated = cv2.dilate(white_mask, kernel, iterations=3)
            outline = cv2.bitwise_xor(dilated, white_mask)
            outline_colors = image[outline > 0]

            if len(outline_colors) > 0:
                outline_colors = outline_colors.reshape(-1, 3)
                outline_colors = np.float32(outline_colors)
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
                k = 3
                _, labels, centers = cv2.kmeans(outline_colors, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
                labels_unique, counts = np.unique(labels, return_counts=True)
                total_pixels = sum(counts)
                dominant_idx = np.argmax(counts)
                dominant_color = centers[dominant_idx]
                confidence = counts[dominant_idx] / total_pixels
                color_hex = '#{:02x}{:02x}{:02x}'.format(
                    int(dominant_color[2]),
                    int(dominant_color[1]),
                    int(dominant_color[0])
                )
                return color_hex, confidence
        except Exception as e:
            self.logger.error(f"Color extraction failed: {str(e)}")
        return None, 0.0

    def parse_xml_and_analyze(self, xml_path: str, images_dir: str) -> List[Dict]:
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            format_elem = root.find(".//Format")
            if format_elem is not None:
                framerate_str = format_elem.get('FrameRate')
                if framerate_str:
                    self.framerate = float(framerate_str)

            results = []
            images_path = Path(images_dir)
            total_events = len(root.findall('.//Event'))

            for i, event in enumerate(root.findall('.//Event'), 1):
                if self.queue:
                    self.update_progress(i * 100 / total_events)

                in_time = event.get('InTC')
                out_time = event.get('OutTC')
                event_data = {
                    'start': self.timecode_to_seconds(in_time),
                    'end': self.timecode_to_seconds(out_time),
                    'start_ass': self.seconds_to_ass_time(self.timecode_to_seconds(in_time)),
                    'end_ass': self.seconds_to_ass_time(self.timecode_to_seconds(out_time)),
                    'graphics': []
                }

                for graphic in event.findall('Graphic'):
                    image_filename = graphic.text
                    image_path = images_path / image_filename
                    if image_path.exists():
                        image = cv2.imread(str(image_path))
                        if image is not None:
                            color, confidence = self.extract_outline_color(image)
                            graphic_data = {
                                'filename': image_filename,
                                'width': int(graphic.get('Width')),
                                'height': int(graphic.get('Height')),
                                'x': int(graphic.get('X')),
                                'y': int(graphic.get('Y')),
                                'color': color,
                                'confidence': confidence
                            }
                            event_data['graphics'].append(graphic_data)

                results.append(event_data)

            return results
        except Exception as e:
            self.logger.error(f"XML parsing failed: {str(e)}")
            return None

    def save_results(self, results: List[Dict], output_path: str):
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Results saved to {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to save results: {str(e)}")

class ASSColorUpdater:
    def __init__(self, ass_path: str, colors_json_path: str, images_dir: str, queue=None, preview_callback=None):
        self.logger = logging.getLogger(__name__)
        self.ass_doc = self._load_ass(ass_path)
        self.colors = self._load_colors(colors_json_path)
        self.images_dir = images_dir
        self.queue = queue
        self.preview_callback = preview_callback
        self.color_selection_event = threading.Event()
        self.selected_color = None

    def _format_time(self, td: datetime.timedelta) -> str:
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        centiseconds = int((td.total_seconds() * 100) % 100)
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    def _load_ass(self, ass_path: str) -> ass.Document:
        try:
            with codecs.open(ass_path, 'r', encoding='utf-8-sig') as f:
                return ass.parse(f)
        except Exception as e:
            self.logger.error(f"Failed to load ASS file: {str(e)}")
            raise

    def _load_colors(self, colors_json_path: str) -> List[Dict]:
        try:
            with codecs.open(colors_json_path, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load colors JSON: {str(e)}")
            raise

    def _hex_to_ass_color(self, hex_color: str) -> str:
        try:
            color = hex_color.lstrip('#')
            rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            return f"&H{rgb[2]:02X}{rgb[1]:02X}{rgb[0]:02X}&"
        except ValueError as e:
            self.logger.error(f"Invalid color format: {hex_color} {e}")
            return "&H000000&"

    def _calculate_color_duration(self, start_time: float, end_time: float,
                                color_events: List[Dict]) -> Dict[str, Dict[str, Union[float, List[str]]]]:
        color_info = defaultdict(lambda: {'duration': 0.0, 'images': set()})
        total_duration = end_time - start_time

        for event in color_events:
            event_start = max(event['start'], start_time)
            event_end = min(event['end'], end_time)
            if event_end > event_start:
                for graphic in event['graphics']:
                    if graphic.get('confidence', 0) > 0.5:
                        duration = event_end - event_start
                        color = graphic['color']
                        if color:  # Check if color is not None
                            color_info[color]['duration'] += duration
                            color_info[color]['images'].add(os.path.join(self.images_dir, graphic['filename']))

        return {
            color: {
                'percentage': info['duration']/total_duration,
                'images': sorted(list(info['images']))
            }
            for color, info in color_info.items()
            if color is not None  # Filter out None colors
        }

    def wait_for_color_selection(self):
        self.color_selection_event.wait()
        self.color_selection_event.clear()
        return self.selected_color

    def set_selected_color(self, color):
        self.selected_color = color
        self.color_selection_event.set()

    def skip_current_line(self):
        """跳过当前行"""
        self.selected_color = "SKIP"
        self.color_selection_event.set()

    def _find_color_at_time(self, start_time: float, end_time: float) -> Optional[Tuple[str, Dict]]:
        relevant_events = [
            event for event in self.colors
            if event['start'] <= end_time and event['end'] >= start_time
        ]

        if not relevant_events:
            return None

        color_info = self._calculate_color_duration(start_time, end_time, relevant_events)

        if not color_info:
            return None

        if len(color_info) == 1:
            color, info = next(iter(color_info.items()))
            if info['percentage'] > 0.5:
                return color, {}

        dominant_color = max(color_info.items(), key=lambda x: x[1]['percentage'])

        if dominant_color[1]['percentage'] >= 0.8:
            return dominant_color[0], {}

        # 如果有预览回调函数，发送预览信息并等待选择
        if self.preview_callback and self.queue:
            event_data = self._get_current_event()
            self.preview_callback((event_data, color_info))
            color = self.wait_for_color_selection()
            if color == "SKIP":
                self.queue.put(("log", f"跳过行: {event_data.text}"))
                return None, {}
            if color:
                return color, {}

        return None, color_info

    def _get_current_event(self):
        """返回当前正在处理的事件数据"""
        if hasattr(self, '_current_event'):
            return self._current_event
        return None

    def update_dialogues_colors(self):
        updated_count = 0
        total_dialogues = len([e for e in self.ass_doc.events if isinstance(e, ass.Dialogue)])
        current_dialogue = 0

        for event in self.ass_doc.events:
            if not isinstance(event, ass.Dialogue):
                continue

            self._current_event = event  # 保存当前正在处理的事件
            current_dialogue += 1
            if self.queue:
                self.queue.put(("progress", current_dialogue * 100 / total_dialogues))

            start_time = event.start.total_seconds()
            end_time = event.end.total_seconds()

            result = self._find_color_at_time(start_time, end_time)
            if not result:
                continue

            color, _ = result
            if color:
                ass_color = self._hex_to_ass_color(color)
                event.text = self._update_dialogue_text(event.text, ass_color)
                updated_count += 1
                if self.queue:
                    self.queue.put(("log", f"Updated dialogue at {start_time:.2f}-{end_time:.2f} "
                                         f"with color {color}"))

        if self.queue:
            self.queue.put(("log", f"Total updated dialogues: {updated_count}"))

    def _update_dialogue_text(self, text: str, new_color: str) -> str:
        color_tag = f"\\3c{new_color}"

        if "\\3c" in text:
            text = re.sub(r'\\3c&H[0-9A-Fa-f]{6}&', color_tag, text)
        else:
            if text.startswith('{'):
                bracket_end = text.find('}')
                if bracket_end != -1:
                    text = text[:bracket_end] + color_tag + text[bracket_end:]
            else:
                text = '{' + color_tag + '}' + text

        return text

    def save(self, output_path: str):
        try:
            with codecs.open(output_path, 'w', encoding='utf-8-sig') as f:
                self.ass_doc.dump_file(f)
            if self.queue:
                self.queue.put(("log", f"Saved updated ASS to {output_path}"))
        except Exception as e:
            if self.queue:
                self.queue.put(("error", f"Failed to save ASS file: {str(e)}"))
            raise
    
class PGSASSColorGUI:
    def __init__(self):
        self.root = ThemedTk(theme="equilux")
        self.root.title("PGS/ASS 字幕颜色处理工具")
        self.root.geometry("1200x800")
        
        # 设置日志
        self.setup_logging()
        
        # 初始化变量
        self.xml_path = tk.StringVar()
        self.ass_path = tk.StringVar()
        self.images_dir = tk.StringVar()
        self.output_path = tk.StringVar()
        self.save_json = tk.StringVar()
        self.current_updater = None
        
        # 创建界面
        self.create_gui()
        
        # 处理队列
        self.queue = queue.Queue()
        
        # 状态变量
        self.processing = False
        self.current_images = []
        self.current_color_info = None

        # 配置窗口大小调整行为
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
    def setup_logging(self):
        """设置日志系统"""
        self.log_queue = queue.Queue()
        self.logger = logging.getLogger(__name__)
        queue_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        queue_handler.setFormatter(formatter)
        self.logger.addHandler(queue_handler)
        self.logger.setLevel(logging.INFO)

    def create_gui(self):
        """创建主界面"""
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # 创建左右分栏
        left_frame = ttk.Frame(main_frame)
        right_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=5)
        
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # 左侧部分
        self.create_left_panel(left_frame)
        
        # 右侧部分
        self.create_right_panel(right_frame)

    def create_left_panel(self, parent):
        """创建左侧面板"""
        # 文件选择区域
        file_frame = ttk.LabelFrame(parent, text="文件选择", padding=5)
        file_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        # XML文件选择
        ttk.Label(file_frame, text="XML文件:").grid(row=0, column=0, sticky="w")
        ttk.Entry(file_frame, textvariable=self.xml_path).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(file_frame, text="浏览", command=lambda: self.browse_file("xml")).grid(row=0, column=2)
        
        # ASS文件选择
        ttk.Label(file_frame, text="ASS文件:").grid(row=1, column=0, sticky="w")
        ttk.Entry(file_frame, textvariable=self.ass_path).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(file_frame, text="浏览", command=lambda: self.browse_file("ass")).grid(row=1, column=2)
        
        # 图片目录选择
        ttk.Label(file_frame, text="图片目录:").grid(row=2, column=0, sticky="w")
        ttk.Entry(file_frame, textvariable=self.images_dir).grid(row=2, column=1, sticky="ew", padx=5)
        ttk.Button(file_frame, text="浏览", command=self.browse_directory).grid(row=2, column=2)
        
        # 输出文件选择
        ttk.Label(file_frame, text="输出文件:").grid(row=3, column=0, sticky="w")
        ttk.Entry(file_frame, textvariable=self.output_path).grid(row=3, column=1, sticky="ew", padx=5)
        ttk.Button(file_frame, text="浏览", command=lambda: self.browse_file("output")).grid(row=3, column=2)
        
        file_frame.grid_columnconfigure(1, weight=1)
        
        # 控制区域
        control_frame = ttk.Frame(parent)
        control_frame.grid(row=1, column=0, sticky="ew", pady=5)
        
        ttk.Button(control_frame, text="开始处理", command=self.start_processing).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="停止处理", command=self.stop_processing).pack(side=tk.LEFT, padx=5)
        
        # 进度条
        self.progress = ttk.Progressbar(control_frame, mode='determinate')
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 日志区域
        log_frame = ttk.LabelFrame(parent, text="处理日志", padding=5)
        log_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        
        self.log_text = tk.Text(log_frame, height=10, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=1)

    def create_right_panel(self, parent):
        """创建右侧面板"""
        # 预览区域
        preview_frame = ttk.LabelFrame(parent, text="颜色选择预览", padding=5)
        preview_frame.grid(row=0, column=0, sticky="nsew")
        
        # ASS行内容显示
        ass_frame = ttk.LabelFrame(preview_frame, text="字幕行内容", padding=5)
        ass_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        self.ass_text = tk.Text(ass_frame, height=3, wrap=tk.WORD)
        ass_scrollbar = ttk.Scrollbar(ass_frame, orient="vertical", command=self.ass_text.yview)
        self.ass_text.configure(yscrollcommand=ass_scrollbar.set)
        self.ass_text.grid(row=0, column=0, sticky="nsew")
        ass_scrollbar.grid(row=0, column=1, sticky="ns")
        
        # 操作按钮区域
        action_frame = ttk.Frame(preview_frame)
        action_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        ttk.Button(action_frame, 
                  text="跳过此行", 
                  command=self.skip_current_line).pack(side=tk.LEFT, padx=5)
        
        # 颜色选择区域
        colors_frame = ttk.LabelFrame(preview_frame, text="可选颜色", padding=5)
        colors_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        
        # 创建颜色选择列表
        self.colors_canvas = tk.Canvas(colors_frame, bg='#2d2d2d')
        colors_scrollbar = ttk.Scrollbar(colors_frame, orient="vertical", 
                                       command=self.colors_canvas.yview)
        self.colors_canvas.configure(yscrollcommand=colors_scrollbar.set)
        
        self.colors_frame_inner = ttk.Frame(self.colors_canvas)
        self.colors_canvas.create_window((0, 0), window=self.colors_frame_inner, anchor='nw')
        
        self.colors_canvas.grid(row=0, column=0, sticky="nsew")
        colors_scrollbar.grid(row=0, column=1, sticky="ns")
        
        # 配置权重
        preview_frame.grid_rowconfigure(2, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        colors_frame.grid_rowconfigure(0, weight=1)
        colors_frame.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # 绑定调整大小事件
        self.colors_frame_inner.bind('<Configure>', 
                                   lambda e: self.colors_canvas.configure(
                                       scrollregion=self.colors_canvas.bbox("all")))

    def update_preview_gui(self, data):
        """更新预览界面"""
        event, color_info = data
        
        # 清除之前的内容
        for widget in self.colors_frame_inner.winfo_children():
            widget.destroy()
        
        # 显示ASS行内容
        self.ass_text.delete(1.0, tk.END)
        self.ass_text.insert(tk.END, f"时间: {event.start} -> {event.end}\n")
        self.ass_text.insert(tk.END, f"样式: {event.style}\n")
        self.ass_text.insert(tk.END, f"文本: {event.text}")
        
        # 为每个颜色创建预览区域
        for i, (color, info) in enumerate(sorted(color_info.items(), 
                                            key=lambda x: x[1]['percentage'],
                                            reverse=True)):
            color_frame = ttk.LabelFrame(self.colors_frame_inner, 
                                    text=f"颜色选项 {i+1}", padding=5)
            color_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # 颜色信息和按钮区域
            info_frame = ttk.Frame(color_frame)
            info_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # 显示颜色样本
            color_sample = tk.Canvas(info_frame, width=50, height=20, bg=color)
            color_sample.pack(side=tk.LEFT, padx=5)
            
            # 显示颜色代码和使用时长百分比
            ttk.Label(info_frame, 
                    text=f"颜色代码: {color} | 使用时长: {info['percentage']:.1%}"
                    ).pack(side=tk.LEFT, padx=5)
            
            # 选择按钮
            ttk.Button(info_frame, 
                    text="使用此颜色", 
                    command=lambda c=color: self.confirm_color_selection(c)
                    ).pack(side=tk.RIGHT, padx=5)
            
            # 创建图片预览区域
            images_frame = ttk.Frame(color_frame)
            images_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # 使用Flowbox布局显示图片
            current_row = ttk.Frame(images_frame)
            current_row.pack(fill=tk.X)
            row_width = 0
            max_width = self.colors_frame_inner.winfo_width() - 20  # 留出一些边距
            
            for img_path in info['images']:
                # 创建预览
                photo = self.create_image_preview(img_path, (200, 150))  # 控制最大尺寸
                if photo:
                    if row_width + photo.width() > max_width and row_width > 0:
                        # 创建新行
                        current_row = ttk.Frame(images_frame)
                        current_row.pack(fill=tk.X)
                        row_width = 0
                    
                    # 创建图片容器
                    img_container = ttk.Frame(current_row)
                    img_container.pack(side=tk.LEFT, padx=2, pady=2)
                    
                    # 显示图片
                    label = ttk.Label(img_container, image=photo)
                    label.image = photo
                    label.pack()
                    
                    # 显示文件名
                    ttk.Label(img_container, 
                            text=os.path.basename(img_path),
                            wraplength=photo.width()  # 文件名宽度匹配图片宽度
                            ).pack()
                    
                    row_width += photo.width() + 4  # 加上padding
        
        # 更新主画布滚动区域
        self.colors_frame_inner.update_idletasks()
        self.colors_canvas.configure(scrollregion=self.colors_canvas.bbox("all"))

    def create_image_preview(self, image_path, max_size=(200, 150)):
        """创建自适应大小的图片预览"""
        try:
            # 使用PIL打开图片
            image = Image.open(image_path)
            
            # 如果是调色板模式，转换为RGB
            if image.mode in ('P', 'PA'):
                image = image.convert('RGBA')
            
            # 获取原始尺寸
            orig_width, orig_height = image.size
            
            # 计算缩放比例，保持原始比例
            scale = min(max_size[0]/orig_width, max_size[1]/orig_height, 1.0)
            
            if scale != 1.0:
                new_width = int(orig_width * scale)
                new_height = int(orig_height * scale)
                
                # 确保图像在缩放前是RGB模式
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # 使用高质量缩放
                image = image.resize((new_width, new_height), Image.LANCZOS)
            
            return ImageTk.PhotoImage(image)
        except Exception as e:
            self.logger.error(f"Failed to create image preview: {str(e)}")
            return None

    def skip_current_line(self):
        """跳过当前行"""
        if self.current_updater:
            self.current_updater.skip_current_line()
            
    def confirm_color_selection(self, color):
        """确认颜色选择"""
        if self.current_updater:
            self.current_updater.set_selected_color(color)
            
    def browse_file(self, file_type):
        """浏览并选择文件"""
        filetypes = {
            "xml": [("XML files", "*.xml")],
            "ass": [("ASS files", "*.ass")],
            "output": [("ASS files", "*.ass")]
        }
        
        filename = filedialog.askopenfilename(filetypes=filetypes.get(file_type, [("All files", "*.*")]))
        if filename:
            if file_type == "xml":
                self.xml_path.set(filename)
            elif file_type == "ass":
                self.ass_path.set(filename)
                # 自动设置输出文件名
                output = Path(filename)
                self.output_path.set(str(output.with_name(output.stem + '_colored' + output.suffix)))
            elif file_type == "output":
                self.output_path.set(filename)

    def browse_directory(self):
        """浏览并选择目录"""
        directory = filedialog.askdirectory()
        if directory:
            self.images_dir.set(directory)

    def update_preview(self, color_info):
        """更新预览区域"""
        self.queue.put(("preview", color_info))

    def show_image(self, image_path):
        """在画布上显示图片"""
        try:
            image = Image.open(image_path)
            # 获取画布尺寸
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            
            # 计算缩放比例
            ratio = min(canvas_width/image.width, canvas_height/image.height)
            new_width = int(image.width * ratio)
            new_height = int(image.height * ratio)
            
            # 调整图片大小
            image = image.resize((new_width, new_height), Image.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            
            # 清除画布并显示新图片
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(
                canvas_width//2, canvas_height//2,
                image=photo, anchor=tk.CENTER
            )
            # 保持图片引用
            self.preview_canvas.image = photo
            
        except Exception as e:
            self.logger.error(f"Failed to show image: {str(e)}")

    def start_processing(self):
        """开始处理文件"""
        if self.processing:
            return
            
        if not all([self.xml_path.get(), self.ass_path.get(), self.images_dir.get(), self.output_path.get()]):
            messagebox.showerror("错误", "请先选择所有必要的文件和目录")
            return
            
        self.processing = True
        self.progress['value'] = 0
        
        # 在新线程中处理文件
        threading.Thread(target=self.process_files, daemon=True).start()
        
        # 开始检查消息队列
        self.root.after(100, self.check_queue)

    def stop_processing(self):
        """停止处理"""
        self.processing = False

    def process_files(self):
        """处理文件的主要逻辑"""
        try:
            self.queue.put(("log", "开始分析XML文件和提取颜色..."))
            analyzer = PGSColorAnalyzer(self.queue)
            results = analyzer.parse_xml_and_analyze(self.xml_path.get(), self.images_dir.get())
            
            if not results:
                self.queue.put(("error", "颜色分析失败"))
                return
                
            temp_json = "temp_colors.json"
            analyzer.save_results(results, temp_json)
            
            self.queue.put(("log", "开始更新ASS文件..."))
            self.current_updater = ASSColorUpdater(
                self.ass_path.get(), 
                temp_json, 
                self.images_dir.get(),
                self.queue,
                self.update_preview
            )
            self.current_updater.update_dialogues_colors()
            self.current_updater.save(self.output_path.get())
            
            os.remove(temp_json)
            self.queue.put(("info", "处理完成！"))
            
        except Exception as e:
            self.queue.put(("error", f"处理失败: {str(e)}"))
            
        finally:
            self.processing = False
            self.current_updater = None

    def check_queue(self):
        """检查消息队列"""
        try:
            while True:
                msg_type, message = self.queue.get_nowait()
                
                if msg_type == "progress":
                    self.progress['value'] = message
                elif msg_type == "log":
                    self.log_text.insert(tk.END, message + "\n")
                    self.log_text.see(tk.END)
                elif msg_type == "error":
                    messagebox.showerror("错误", message)
                elif msg_type == "info":
                    messagebox.showinfo("信息", message)
                elif msg_type == "preview":
                    self.update_preview_gui(message)
                    
        except queue.Empty:
            pass
            
        if self.processing:
            self.root.after(100, self.check_queue)

def main():
    app = PGSASSColorGUI()
    app.root.mainloop()

if __name__ == "__main__":
    main()
