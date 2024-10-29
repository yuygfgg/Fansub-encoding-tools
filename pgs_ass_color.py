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
import argparse
import ass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PGSColorAnalyzer:
    def __init__(self):
        self.framerate = 23.976
        self.logger = logging.getLogger(__name__)

    def timecode_to_seconds(self, timecode: str) -> float:
        """将时间码转换为秒数"""
        hours, minutes, seconds, frames = map(int, timecode.split(':'))
        total_seconds = hours * 3600 + minutes * 60 + seconds + frames / self.framerate
        return total_seconds

    def seconds_to_ass_time(self, seconds: float) -> str:
        """将秒数转换为ASS格式时间码"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        return f"{hours:d}:{minutes:02d}:{seconds:02.2f}"

    def extract_outline_color(self, image: np.ndarray) -> Tuple[str, float]:
        """从图像中提取描边颜色"""
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
        """解析XML并分析每个图片的颜色"""
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
                if i % 10 == 0:
                    self.logger.info(f"Processed {i}/{total_events} events")

            return results
        except Exception as e:
            self.logger.error(f"XML parsing failed: {str(e)}")
            return None

    def save_results(self, results: List[Dict], output_path: str):
        """保存结果到JSON文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Results saved to {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to save results: {str(e)}")

class ASSColorUpdater:
    def __init__(self, ass_path: str, colors_json_path: str, images_dir: str):
        self.logger = logging.getLogger(__name__)
        self.ass_doc = self._load_ass(ass_path)
        self.colors = self._load_colors(colors_json_path)
        self.images_dir = images_dir

    def _format_time(self, td: datetime.timedelta) -> str:
        """将timedelta转换为ASS格式的时间字符串"""
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
            self.logger.error(f"Invalid color format: {hex_color}")
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
                        color_info[color]['duration'] += duration
                        color_info[color]['images'].add(graphic['filename'])

        return {
            color: {
                'percentage': info['duration']/total_duration,
                'images': sorted(list(info['images']))
            }
            for color, info in color_info.items()
        }

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

        return None, color_info

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

    def _format_ass_event(self, event: ass.Dialogue) -> str:
        fields = [
            str(event.layer),
            self._format_time(event.start),
            self._format_time(event.end),
            event.style,
            event.name,
            str(event.margin_l),
            str(event.margin_r),
            str(event.margin_v),
            event.effect,
            event.text
        ]
        return 'Dialogue: ' + ','.join(fields)

    def _display_images(self, image_files: List[str], color: str) -> None:
        print(f"\n颜色 {color} 的相关图片:")
        for img_file in image_files:
            img_path = os.path.join(self.images_dir, img_file)
            if os.path.exists(img_path):
                print(f"- {img_file}")
            else:
                print(f"[未找到] {img_file}")

    def update_dialogues_colors(self):
        updated_count = 0
        manual_selection_needed = []

        for event in self.ass_doc.events:
            if not isinstance(event, ass.Dialogue):
                continue

            start_time = event.start.total_seconds()
            end_time = event.end.total_seconds()

            result = self._find_color_at_time(start_time, end_time)
            if not result:
                continue

            dominant_color, color_info = result

            if dominant_color:
                ass_color = self._hex_to_ass_color(dominant_color)
                event.text = self._update_dialogue_text(event.text, ass_color)
                updated_count += 1
                self.logger.info(
                    f"Updated dialogue at {start_time:.2f}-{end_time:.2f} "
                    f"with color {dominant_color} (dominant)"
                )
            else:
                manual_selection_needed.append({
                    'event': event,
                    'colors': color_info,
                    'start_time': start_time,
                    'end_time': end_time
                })

        self.logger.info(f"Automatically updated dialogues: {updated_count}")

        if manual_selection_needed:
            self._handle_manual_selection(manual_selection_needed)

    def _handle_manual_selection(self, selections_needed: List[Dict]):
        print("\n需要手动选择颜色的对话行：")

        for item in selections_needed:
            event = item['event']
            start_time = item['start_time']
            end_time = item['end_time']
            color_info = item['colors']

            print(f"\n时间: {self._format_time(datetime.timedelta(seconds=start_time))} - "
                  f"{self._format_time(datetime.timedelta(seconds=end_time))}")
            print(f"原始ASS行: {self._format_ass_event(event)}")
            print("\n可选颜色:")

            color_list = []
            for i, (color, info) in enumerate(sorted(color_info.items(),
                                                   key=lambda x: x[1]['percentage'],
                                                   reverse=True), 1):
                percentage = info['percentage']
                images = info['images']
                print(f"\n{i}. {color} (持续时间比例: {percentage:.2%})")
                self._display_images(images, color)
                color_list.append(color)

            while True:
                try:
                    choice = input("\n请选择颜色编号（输入q跳过此行）: ")
                    if choice.lower() == 'q':
                        break

                    index = int(choice) - 1
                    if 0 <= index < len(color_list):
                        selected_color = color_list[index]
                        ass_color = self._hex_to_ass_color(selected_color)
                        event.text = self._update_dialogue_text(event.text, ass_color)
                        print(f"已更新颜色为: {selected_color}")
                        break
                    else:
                        print("无效的选择，请重试")
                except ValueError:
                    print("请输入有效的数字或q")
            print("\n" + "="*50)

    def save(self, output_path: str):
        try:
            with codecs.open(output_path, 'w', encoding='utf-8-sig') as f:
                self.ass_doc.dump_file(f)
            self.logger.info(f"Saved updated ASS to {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to save ASS file: {str(e)}")
            raise

def process_files(xml_path: str, ass_path: str, images_dir: str, output_path: str, temp_json_path: str = None):
    """处理文件的主函数"""
    logger = logging.getLogger(__name__)

    logger.info("开始分析XML文件和提取颜色...")
    analyzer = PGSColorAnalyzer()
    results = analyzer.parse_xml_and_analyze(xml_path, images_dir)

    if not results:
        logger.error("颜色分析失败")
        return

    if temp_json_path:
        analyzer.save_results(results, temp_json_path)
        colors_json_path = temp_json_path
    else:
        colors_json_path = "temp_colors.json"
        analyzer.save_results(results, colors_json_path)

    logger.info("开始更新ASS文件...")
    try:
        updater = ASSColorUpdater(ass_path, colors_json_path, images_dir)
        updater.update_dialogues_colors()
        updater.save(output_path)
        logger.info("处理完成！")
    finally:
        if not temp_json_path and os.path.exists(colors_json_path):
            os.remove(colors_json_path)

def main():
    parser = argparse.ArgumentParser(description='PGS字幕颜色提取和ASS更新工具')

    parser.add_argument('xml_path',
                      help='XML文件路径 (从PGS提取的)')
    parser.add_argument('ass_path',
                      help='输入的ASS文件路径')
    parser.add_argument('--images-dir', '-i',
                      default='./',
                      help='包含PNG图片的目录路径 (默认: 当前目录)')
    parser.add_argument('--output', '-o',
                      help='输出的ASS文件路径 (默认: 在原文件名后添加_colored)')
    parser.add_argument('--save-json', '-s',
                      help='保存颜色分析结果的JSON文件路径 (可选)')

    args = parser.parse_args()

    if not args.output:
        output_path = Path(args.ass_path)
        output_path = output_path.with_name(output_path.stem + '_colored' + output_path.suffix)
    else:
        output_path = args.output

    try:
        process_files(
            xml_path=args.xml_path,
            ass_path=args.ass_path,
            images_dir=args.images_dir,
            output_path=output_path,
            temp_json_path=args.save_json
        )
    except Exception as e:
        logging.error(f"处理失败: {str(e)}")
        raise

if __name__ == "__main__":
    main()
