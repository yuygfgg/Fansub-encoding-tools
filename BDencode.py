import shlex
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import re
import subprocess
import shutil
import threading
import queue as Queue
from queue import Empty as QueueEmpty
import time
from pathlib import Path
from datetime import datetime
import signal

class EncodingTask:
    def __init__(self, episode_num, task_type, command, prerequisites=None, work_dir=None):
        self.episode_num = episode_num
        self.task_type = task_type
        self.command = command
        self.prerequisites = prerequisites or []
        self.status = "pending"
        self.start_time = None
        self.end_time = None
        self.process = None
        self.output = []
        self.custom_params = {}
        self.paused = False
        self.work_dir = work_dir
    
    def is_completed(self, root_path):
        if self.status == "stopped":
            return False
            
        episode_dir = Path(root_path) / f"E{self.episode_num.zfill(2)}"
        result_dir = Path(root_path) / "result"
        
        try:
            if self.task_type == "video":
                return (episode_dir / "video.mkv").exists()
                
            elif self.task_type == "audio":
                return (episode_dir / f"output{self.episode_num}.flac").exists()
                
            elif self.task_type == "subtitle_process":
                return (episode_dir / "subsetted_fonts").exists()
                
            elif self.task_type == "merge":
                return (episode_dir / "final_output.mkv").exists()
                
            elif self.task_type == "mux":
                return (episode_dir / "final_with_subs.mkv").exists()
                
            elif "hardsub_" in self.task_type:
                if "merge" in self.task_type:
                    lang = self.task_type.split("_")[1]
                    return (episode_dir / f"final_{lang}.mkv").exists()
                else:
                    lang = self.task_type.split("_")[1]
                    return (episode_dir / f"{lang}.mkv").exists()
                    
            elif self.task_type == "organize":
                return all([
                    (result_dir / f"E{self.episode_num.zfill(2)}_complete.mkv").exists(),
                    (result_dir / f"E{self.episode_num.zfill(2)}_chs.mkv").exists(),
                    (result_dir / f"E{self.episode_num.zfill(2)}_cht.mkv").exists()
                ])
                
            return False
            
        except Exception as e:
            print(f"Error checking completion for task {self.task_type}: {str(e)}")
            return False

class EncodingProject:
    def __init__(self):
        self.root_path = None
        self.tasks = []
        self.default_normal_x265_params = {
            "crf": 16,
            "tune": "lp",
            "preset": "slower"
        }
        self.default_hardsub_x265_params = {
            "crf": 17,
            "tune": "lp",
            "preset": "slower"
        }
        self.current_normal_x265_params = self.default_normal_x265_params.copy()
        self.current_hardsub_x265_params = self.default_hardsub_x265_params.copy()
    def generate_x265_command(self, params):
        base_params = [
            "--no-open-gop",
            "--deblock=-1:-1",
            "--colorprim=bt709",
            "--colormatrix=bt709",
            "--transfer=bt709",
            "--range=limited",
            "--hist-scenecut",
            "--no-sao",
            "-b=9",
            "--qcomp=0.65",
            "--qg-size=8",
            "--subme=5",
            "--tu-intra-depth=4",
            "--tu-inter-depth=4",
            "--no-strong-intra-smoothing",
            "--ctu=32",
            "--cbqpoffs=-2",
            "--crqpoffs=-2",
            "--limit-tu=0",
            "--aq-mode=3",
            "--aq-strength=0.7",
            "--merange=32",
            "-D=10"
        ]

        cmd = ["x265"]
        cmd.extend([f"--crf={params['crf']}"])
        if params['tune'] and params['tune'].strip():
            cmd.extend([f"--tune={params['tune']}"])
        cmd.extend([f"--preset={params['preset']}"])
        cmd.extend(base_params)
        return cmd

    def setup_project(self, root_path):
        self.root_path = Path(root_path)
        self.workspace_path = Path.home() / self.root_path.name
        os.makedirs(self.workspace_path, exist_ok=True)

    def generate_tasks(self, episode_patterns):
        try:
            m2ts_pattern = episode_patterns.get("m2ts", r"[0-9][0-9]\.m2ts")
            ass_pattern = episode_patterns.get("ass", r".*\[[0-9][0-9]\].*\.ass")
            chapter_pattern = episode_patterns.get("chapter", r"\ [0-9][0-9]\ \.txt")

            # Create episode directories and generate tasks
            for m2ts_file in self.root_path.glob("m2ts/*.m2ts"):
                if not re.match(m2ts_pattern, m2ts_file.name):
                    continue

                episode_num = re.search(r"\d+", m2ts_file.name).group()
                episode_dir = self.root_path / f"E{episode_num.zfill(2)}"
                os.makedirs(episode_dir, exist_ok=True)

                try:
                    # Copy and setup files
                    self._setup_episode_files(episode_num, m2ts_file, ass_pattern, chapter_pattern)

                    # Generate tasks for this episode
                    self._generate_episode_tasks(episode_num)
                except Exception as e:
                    print(f"Error processing episode {episode_num}: {str(e)}")
                    raise

        except Exception as e:
            print(f"Error generating tasks: {str(e)}")
            raise

    def _setup_episode_files(self, episode_num, m2ts_file, ass_pattern, chapter_pattern):
        episode_dir = self.root_path / f"E{episode_num.zfill(2)}"
        target_m2ts = episode_dir / "source.m2ts"

        if target_m2ts.exists():
            if target_m2ts.stat().st_size == m2ts_file.stat().st_size:
                print(f"M2TS file already exists : {target_m2ts}, skip copying")
            else:
                print(f"M2TS file exists but size differs, copying: {m2ts_file}")
                shutil.copy2(m2ts_file, target_m2ts)
        else:
            print(f"M2TS file does not exist, copying: {m2ts_file}")
            shutil.copy2(m2ts_file, target_m2ts)

        # Copy subtitles
        for ass_file in self.root_path.glob("subtitles/*.ass"):
            if re.match(ass_pattern, ass_file.name):
                if str(episode_num) in ass_file.name:
                    shutil.copy2(ass_file, episode_dir)

        # Copy chapters
        for chapter_file in self.root_path.glob("chapters/*.txt"):
            if re.match(chapter_pattern, chapter_file.name):
                if str(episode_num) in chapter_file.name:
                    shutil.copy2(chapter_file, episode_dir)

        # Create VPY script
        self._create_vpy_script(episode_num)

    def _create_vpy_script(self, episode_num):
        episode_dir = self.root_path / f"E{episode_num.zfill(2)}"
        template_path = self.root_path / "template.vpy"
        source_path = episode_dir / "source.m2ts"

        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        vpy_content = template_content.replace('file_path = ""', f'file_path = r"{str(source_path)}"')

        output_vpy = episode_dir / f"{episode_num.zfill(2)}.vpy"
        with open(output_vpy, 'w', encoding='utf-8') as f:
            f.write(vpy_content)

    def _generate_mux_task(self, episode_num):
        episode_dir = self.root_path / f"E{episode_num.zfill(2)}"
        temp_dir = episode_dir / "temp"
        fonts_dir = episode_dir / "subsetted_fonts"

        # 使用命令去动态查找字幕文件
        mux_command = (
            f'mkdir -p "{str(temp_dir)}" && '
            f'mkvextract "{str(episode_dir / "final_output.mkv")}" tracks '
            f'0:"{str(temp_dir / "video.hevc")}" '
            f'1:"{str(temp_dir / "audio.flac")}" && '
            f'mkvmerge -o "{str(episode_dir / "final_with_subs.mkv")}" '
            f'--language 0:und "{str(temp_dir / "video.hevc")}" '
            f'--language 0:ja "{str(temp_dir / "audio.flac")}" '
            f'--language 0:zh-cn --track-name 0:简日双语 '
            f'--default-track 0:yes "$(ls "{str(episode_dir)}"/*.chs_jpn.rename.ass)" '
            f'--language 0:zh-tw --track-name 0:繁日双语 '
            f'--default-track 0:no "$(ls "{str(episode_dir)}"/*.cht_jpn.rename.ass)" '
            f'--chapters "{str(list(episode_dir.glob("*.txt"))[0])}" && '
            f'find "{str(fonts_dir)}" -type f -name "*.ttf" '
            f'-exec mkvpropedit "{str(episode_dir / "final_with_subs.mkv")}" '
            f'--attachment-mime-type font/ttf --add-attachment "{{}}" \\; && '
            f'find "{str(fonts_dir)}" -type f -name "*.otf" '
            f'-exec mkvpropedit "{str(episode_dir / "final_with_subs.mkv")}" '
            f'--attachment-mime-type font/otf --add-attachment "{{}}" \\; && '
            f'rm -rf "{str(temp_dir)}"'
        )

        mux_task = EncodingTask(
            episode_num,
            "mux",
            mux_command,
            prerequisites=["merge", "subtitle_process"],  # 确保字幕处理完成后再执行
            work_dir=str(episode_dir)
        )

        return [mux_task]
    
    def _execute_task(self, task):
        try:
            # 输出调试信息
            if hasattr(self, 'output_text'):
                self.output_text.insert(tk.END, f"\n[{task.episode_num}:{task.task_type}] Task Info:\n")
                if task.work_dir:
                    self.output_text.insert(tk.END, f"Working Directory: {task.work_dir}\n")
                self.output_text.insert(tk.END, f"Command: {task.command}\n\n")
                self.output_text.see(tk.END)

            # 如果命令是列表，转换为字符串
            if isinstance(task.command, list):
                command = ' '.join(str(x) for x in task.command)
            else:
                command = task.command

            # 创建进程
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                shell=True,
                cwd=task.work_dir
            )

            task.process = process
            
            # 启动输出监控线程
            threading.Thread(
                target=self._monitor_output,
                args=(task, process),
                daemon=True
            ).start()

        except Exception as e:
            task.status = "failed"
            if hasattr(self, 'output_text'):
                self.output_text.insert(tk.END, f"任务执行失败: {str(e)}\n")
                self.output_text.see(tk.END)

    def _monitor_output(self, task, process):
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    if hasattr(self, 'output_text'):
                        self.output_text.insert(tk.END, f"[{task.episode_num}:{task.task_type}] {line}\n")
                        self.output_text.see(tk.END)
                    task.output.append(line)
        except Exception as e:
            if hasattr(self, 'output_text'):
                self.output_text.insert(tk.END, f"输出监控错误: {str(e)}\n")
                self.output_text.see(tk.END)
        finally:
            try:
                process.wait()
            except Exception:
                pass

    def _generate_episode_tasks(self, episode_num):
        episode_dir = self.root_path / f"E{episode_num.zfill(2)}"

        # 查找字幕文件
        subtitle_paths = []
        for lang in ["chs", "cht"]:
            files = list(episode_dir.glob(f"*{lang}_jpn.ass"))
            if files:
                subtitle_paths.append(str(files[0]))

        if not subtitle_paths:
            raise ValueError(f"No subtitle files found in {episode_dir}")

        # 构建assfonts命令
        subtitle_command = "assfonts"
        for path in subtitle_paths:
            subtitle_command += f' -i "{path}"'
        subtitle_command += f' -f "{str(self.root_path / "fonts")}" -r -c && mv *.chs_jpn.rename.ass {episode_num.zfill(2)}.chs_jpn.rename.ass && mv *.cht_jpn.rename.ass {episode_num.zfill(2)}.cht_jpn.rename.ass'

        # 创建所有任务
        tasks = []

        # 字幕处理任务
        subtitle_process_task = EncodingTask(
            episode_num,
            "subtitle_process",
            subtitle_command,
            work_dir=str(episode_dir)
        )
        tasks.append(subtitle_process_task)

        # 字幕清理任务
        subtitle_cleanup_task = EncodingTask(
            episode_num,
            "subtitle_cleanup",
            f"rm {' '.join(shlex.quote(str(f)) for f in episode_dir.glob('*.ass') if not f.name.endswith('.rename.ass'))}",
            prerequisites=["subtitle_process"],
            work_dir=str(episode_dir)
        )
        tasks.append(subtitle_cleanup_task)

        # 音频任务
        audio_task = EncodingTask(
            episode_num,
            "audio",
            f'ffmpeg -i "{str(episode_dir / "source.m2ts")}" -c:a pcm_s24le "{str(episode_dir / f"audio{episode_num}.wav")}" && '
            f'flaldf "{str(episode_dir / f"audio{episode_num}.wav")}" -o "{str(episode_dir / f"output{episode_num}.flac")}" && '
            f'ffmpeg -i "{str(episode_dir / f"audio{episode_num}.wav")}" -c:a aac_at  -global_quality:a 14 -aac_at_mode 2 -b:a 320k "{str(episode_dir / f"audio{episode_num}.aac")}"',
            work_dir=str(episode_dir)
        )
        tasks.append(audio_task)

        # 视频任务
        video_task = EncodingTask(
            episode_num,
            "video",
            None,  # 命令先设为None，运行时再构造
            work_dir=str(episode_dir)
        )
        video_task.custom_params = {
            "input_vpy": str(episode_dir / f"{episode_num.zfill(2)}.vpy"),
            "output_mkv": str(episode_dir / "video.mkv"),
            "is_hardsub": False
        }
        tasks.append(video_task)

        # 合并任务
        merge_task = EncodingTask(
            episode_num,
            "merge",
            f'mkvmerge -o "{str(episode_dir / "final_output.mkv")}" --language 0:ja "{str(episode_dir / "video.mkv")}" "{str(episode_dir / f"output{episode_num}.flac")}"',
            prerequisites=["audio", "video"],
            work_dir=str(episode_dir)
        )
        tasks.append(merge_task)

        # MUX任务
        mux_tasks = self._generate_mux_task(episode_num)
        tasks.extend(mux_tasks)

        # 硬字幕任务
        hardsub_tasks = self._generate_hardsub_tasks(episode_num)
        tasks.extend(hardsub_tasks)

        # 硬字幕合并任务
        hardsub_merge_tasks = self._generate_hardsub_merge_task(episode_num)
        tasks.extend(hardsub_merge_tasks)

        # 整理任务
        organize_task = EncodingTask(
            episode_num,
            "organize",
            self._generate_organize_command(episode_num),
            prerequisites=["mux"] + [f"hardsub_{lang}_merge" for lang in ["chs", "cht"]],
            work_dir=str(episode_dir)
        )
        tasks.append(organize_task)

        # 检查每个任务的完成状态
        for task in tasks:
            if task.is_completed(self.root_path):
                task.status = "completed"
                task.start_time = datetime.now()
                task.end_time = datetime.now()

        # 将任务添加到项目中
        self.tasks.extend(tasks)

    def _generate_organize_command(self, episode_num):
        episode_dir = self.root_path / f"E{episode_num.zfill(2)}"
        result_dir = self.root_path / "result"

        # 确保结果目录存在并合并所有移动命令
        return (
            f'mkdir -p "{str(result_dir)}" && '
            f'cp "{str(episode_dir / "final_with_subs.mkv")}" '
            f'"{str(result_dir / f"E{episode_num.zfill(2)}_complete.mkv")}" && '
            f'cp "{str(episode_dir / "final_chs.mkv")}" '
            f'"{str(result_dir / f"E{episode_num.zfill(2)}_chs.mkv")}" && '
            f'cp "{str(episode_dir / "final_cht.mkv")}" '
            f'"{str(result_dir / f"E{episode_num.zfill(2)}_cht.mkv")}"'
        )

    def _generate_hardsub_tasks(self, episode_num):
        tasks = []
        episode_dir = self.root_path / f"E{episode_num.zfill(2)}"
        fonts_dir = episode_dir / "subsetted_fonts"

        for lang in ["chs", "cht"]:
            vpy_file = episode_dir / f"{lang}.vpy"
            
            # 创建VPY文件
            with open(vpy_file, 'w', encoding='utf-8') as f:
                f.write(self._generate_hardsub_vpy(episode_num, lang, fonts_dir))

            hardsub_task = EncodingTask(
                episode_num,
                f"hardsub_{lang}",
                None,  # 命令先设为None，运行时再构造
                prerequisites=["merge"],
                work_dir=str(episode_dir)
            )
            hardsub_task.custom_params = {
                "input_vpy": str(vpy_file),
                "output_mkv": str(episode_dir / f"{lang}.mkv"),
                "is_hardsub": True
            }
            tasks.append(hardsub_task)

        return tasks

    def _generate_hardsub_vpy(self, episode_num, lang, fonts_dir):
        episode_dir = self.root_path / f"E{episode_num.zfill(2)}"
        video_path = episode_dir / "video.mkv"
        subtitle_path = episode_dir / f"{episode_num.zfill(2)}.{lang}_jpn.rename.ass"

        return f"""import vapoursynth as vs
from vapoursynth import core

file_path = r"{str(video_path)}"
sub_path = r"{str(subtitle_path)}"
fonts_dir = r"{str(fonts_dir)}"

clip = core.lsmas.LWLibavSource(file_path)

sub = core.assrender.TextSub(
    clip=clip,
    file=sub_path,
    fontdir=fonts_dir
)

sub.set_output(0)
    """


    def _generate_hardsub_merge_task(self, episode_num):
        episode_dir = self.root_path / f"E{episode_num.zfill(2)}"
        tasks = []

        for lang in ["chs", "cht"]:
            merge_task = EncodingTask(
                episode_num,
                f"hardsub_{lang}_merge",
                f'mkvmerge -o "{str(episode_dir / f"final_{lang}.mkv")}" ' +
                f'--language 0:und "{str(episode_dir / f"{lang}.mkv")}" ' +
                f'--language 0:ja "{str(episode_dir / f"audio{episode_num}.aac")}" ' +
                f'--chapters "{str(list(episode_dir.glob("*.txt"))[0])}"',
                prerequisites=[f"hardsub_{lang}"]
            )
            tasks.append(merge_task)

        return tasks

class EncodingGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BD Encoding Manager")
        self.root.geometry("1200x800")

        self.project = EncodingProject()
        self.running_tasks = {}
        self.output_queues = {}

        self._create_gui()
        self._setup_task_monitor()

    def _create_gui(self):
        # Main container
        main_container = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True)

        # Left panel (Tree)
        left_frame = ttk.Frame(main_container)
        main_container.add(left_frame)

        # Task tree
        columns = ("Episode", "Task", "Status", "Duration")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings")

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)

        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Right panel (Controls and Output)
        right_frame = ttk.Frame(main_container)
        main_container.add(right_frame)

        # Control panel
        control_frame = ttk.LabelFrame(right_frame, text="控制面板")
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        # Project setup
        project_frame = ttk.LabelFrame(control_frame, text="项目设置")
        project_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(project_frame, text="选择项目文件夹",
                command=self._select_project_folder).pack(pady=5)

        # Encoding parameters
        params_frame = ttk.LabelFrame(control_frame, text="编码参数")
        params_frame.pack(fill=tk.X, padx=5, pady=5)

        # Normal encode parameters
        normal_frame = ttk.LabelFrame(params_frame, text="普通编码（内封）")
        normal_frame.pack(fill=tk.X, padx=5, pady=5)

        self.normal_param_vars = {}
        param_labels = {
            "crf": "CRF值",
            "tune": "调优模式",
            "preset": "预设速度"
        }

        for param in ["crf", "tune", "preset"]:
            frame = ttk.Frame(normal_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(frame, text=param_labels[param], width=10).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(self.project.current_normal_x265_params[param]))
            entry = ttk.Entry(frame, textvariable=var)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.normal_param_vars[param] = var

        ttk.Button(normal_frame, text="重置为默认值",
                command=lambda: self._reset_params("normal")).pack(pady=5)

        # Hardsub encode parameters
        hardsub_frame = ttk.LabelFrame(params_frame, text="硬字幕编码（内嵌）")
        hardsub_frame.pack(fill=tk.X, padx=5, pady=5)

        self.hardsub_param_vars = {}
        for param in ["crf", "tune", "preset"]:
            frame = ttk.Frame(hardsub_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(frame, text=param_labels[param], width=10).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(self.project.current_hardsub_x265_params[param]))
            entry = ttk.Entry(frame, textvariable=var)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.hardsub_param_vars[param] = var

        ttk.Button(hardsub_frame, text="重置为默认值",
                command=lambda: self._reset_params("hardsub")).pack(pady=5)

        # Add apply button
        ttk.Button(params_frame, text="应用参数设置",
                command=self._apply_params).pack(pady=5)

        # Task control buttons
        button_frame = ttk.LabelFrame(control_frame, text="任务控制")
        button_frame.pack(fill=tk.X, pady=5, padx=5)

        task_btn_frame = ttk.Frame(button_frame)
        task_btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(task_btn_frame, text="执行选中",
                command=self._start_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(task_btn_frame, text="停止选中",
                command=self._stop_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(task_btn_frame, text="暂停选中",
                command=self._pause_selected).pack(side=tk.LEFT, padx=5)

        # Add global control buttons
        global_btn_frame = ttk.Frame(button_frame)
        global_btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(global_btn_frame, text="全部执行",
                command=self._start_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(global_btn_frame, text="全部停止",
                command=self._stop_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(global_btn_frame, text="全部暂停",
                command=self._pause_all).pack(side=tk.LEFT, padx=5)

        # Output console
        console_frame = ttk.LabelFrame(right_frame, text="输出日志")
        console_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add scrollbar for output text
        text_frame = ttk.Frame(console_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.output_text = tk.Text(text_frame, wrap=tk.WORD, height=20)
        scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=scroll.set)

        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Add clear log button
        ttk.Button(console_frame, text="清除日志",
                command=lambda: self.output_text.delete(1.0, tk.END)).pack(pady=5)

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    def _reset_params(self, param_type):
        if param_type == "normal":
            self.project.current_normal_x265_params = self.project.default_normal_x265_params.copy()
            for param, var in self.normal_param_vars.items():
                var.set(str(self.project.current_normal_x265_params[param]))
        else:
            self.project.current_hardsub_x265_params = self.project.default_hardsub_x265_params.copy()
            for param, var in self.hardsub_param_vars.items():
                var.set(str(self.project.current_hardsub_x265_params[param]))

    def _apply_params(self):
        # Update normal encode parameters
        for param, var in self.normal_param_vars.items():
            self.project.current_normal_x265_params[param] = var.get()

        # Update hardsub encode parameters
        for param, var in self.hardsub_param_vars.items():
            self.project.current_hardsub_x265_params[param] = var.get()

        # Update running tasks if needed
        self._update_running_tasks_params()

    def _update_running_tasks_params(self):
        for task_id, (task, queue) in self.running_tasks.items():
            if task.status == "pending":
                if "hardsub" in task.task_type:
                    params = self.project.current_hardsub_x265_params
                else:
                    params = self.project.current_normal_x265_params

                if task.task_type == "video":
                    task.command = self.project.generate_x265_command(params) + [
                        f"--input={task.episode_num.zfill(2)}.vpy",
                        "-o video.mkv"
                    ]
                elif "hardsub" in task.task_type and "encode" in task.task_type:
                    lang = task.task_type.split("_")[1]
                    task.command = self.project.generate_x265_command(params) + [
                        f"--input={lang}.vpy",
                        f"-o {lang}.mkv"
                    ]

    def _setup_task_monitor(self):
        self.monitor_thread = threading.Thread(target=self._monitor_tasks, daemon=True)
        self.monitor_thread.start()

    def _monitor_tasks(self):
        while True:
            for task_id, (task, output_queue) in list(self.running_tasks.items()):
                try:
                    while True:
                        output = output_queue.get_nowait()
                        self._update_task_output(task, output)
                except QueueEmpty:
                    pass

                if task.process and task.process.poll() is not None:
                    self._task_completed(task)
                    del self.running_tasks[task_id]

                time.sleep(0.1)

    def _select_project_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.project.setup_project(folder)
            self._show_pattern_dialog()

    def _show_pattern_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("File Patterns")
        dialog.grab_set()

        patterns = {}
        for name in ["m2ts", "ass", "chapter"]:
            frame = ttk.Frame(dialog)
            frame.pack(fill=tk.X, padx=5, pady=5)
            ttk.Label(frame, text=f"{name} pattern:").pack(side=tk.LEFT)
            var = tk.StringVar()
            ttk.Entry(frame, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)
            patterns[name] = var

        def confirm():
            pattern_dict = {k: v.get() for k, v in patterns.items()}
            self.project.generate_tasks(pattern_dict)
            self._refresh_task_tree()
            dialog.destroy()

        ttk.Button(dialog, text="Confirm", command=confirm).pack(pady=10)

    def _refresh_task_tree(self):
        # 保存当前选中的项目的值
        selected_values = []
        for item in self.tree.selection():
            values = self.tree.item(item)['values']
            if values:
                selected_values.append((values[0], values[1]))  # 保存集数和任务类型
        
        # 清除所有项目
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 定义任务类型的顺序
        task_type_order = {
            "subtitle_process": 1,
            "subtitle_cleanup": 2,
            "audio": 3,
            "video": 4,
            "merge": 5,
            "mux": 6,
            "hardsub_chs": 7,
            "hardsub_cht": 8,
            "hardsub_chs_merge": 9,
            "hardsub_cht_merge": 10,
            "organize": 11
        }

        # 对任务进行排序
        sorted_tasks = sorted(
            self.project.tasks,
            key=lambda x: (
                int(x.episode_num),  # 首先按集数排序
                task_type_order.get(x.task_type, 999)  # 然后按任务类型排序
            )
        )

        # 重新插入所有任务并记录新的item ID
        new_items = {}
        for task in sorted_tasks:
            item_id = self.tree.insert("", tk.END, values=(
                f"E{task.episode_num.zfill(2)}",
                task.task_type,
                task.status,
                self._format_duration(task.start_time, task.end_time)
            ))
            new_items[(f"E{task.episode_num.zfill(2)}", task.task_type)] = item_id

        # 恢复之前的选择状态
        for episode, task_type in selected_values:
            if (episode, task_type) in new_items:
                self.tree.selection_add(new_items[(episode, task_type)])

    def _format_duration(self, start_time, end_time):
        if not start_time:
            return "-"
        if not end_time:
            return "Running"
        duration = end_time - start_time
        return str(duration).split(".")[0]

    def _start_selected(self):
        try:
            selected_items = self.tree.selection()
            if len(selected_items) > 1:
                messagebox.showwarning("Warning", "Please select only one task to start")
                return
            elif not selected_items:
                messagebox.showwarning("Warning", "No task selected")
                return

            item = selected_items[0]
            values = self.tree.item(item)["values"]
            if values:
                episode = values[0][1:]  # Remove 'E' prefix
                task_type = values[1]

                task = self._find_task(episode, task_type)
                if task and task.status != "running":
                    self._start_task(task)
        except Exception as e:
            print(f"Error in _start_selected: {str(e)}")
            messagebox.showerror("Error", f"Failed to start task: {str(e)}")

    def _stop_selected(self):
        selected_items = self.tree.selection()
        for item in selected_items:
            values = self.tree.item(item)["values"]
            episode = values[0][1:]
            task_type = values[1]

            task = self._find_task(episode, task_type)
            if task and task.status == "running":
                self._stop_task(task)

    def _pause_selected(self):
        selected_items = self.tree.selection()
        for item in selected_items:
            values = self.tree.item(item)["values"]
            episode = values[0][1:]
            task_type = values[1]

            task = self._find_task(episode, task_type)
            if task and task.status == "running":
                self._pause_task(task)
    
    def _start_all(self):
        """Start all tasks in sequence"""
        # Sort tasks by episode number and predefined order
        task_type_order = {
            "subtitle_process": 1,
            "subtitle_cleanup": 2,
            "audio": 3,
            "video": 4,
            "merge": 5,
            "mux": 6,
            "hardsub_chs": 7,
            "hardsub_cht": 8,
            "hardsub_chs_merge": 9,
            "hardsub_cht_merge": 10,
            "organize": 11
        }
        
        sorted_tasks = sorted(
            self.project.tasks,
            key=lambda x: (int(x.episode_num), task_type_order.get(x.task_type, 999))
        )
        
        def execute_next_task(tasks):
            if not tasks:
                return
                
            task = tasks[0]
            if task.status not in ["completed", "running"]:
                if self._check_prerequisites(task):
                    self._start_task(task)
                    # Schedule check for next task
                    self.root.after(1000, lambda: self._check_task_completion(task, tasks[1:]))
                else:
                    # Skip this task and move to next
                    execute_next_task(tasks[1:])
            else:
                # Skip this task and move to next
                execute_next_task(tasks[1:])
        
        execute_next_task(sorted_tasks)

    def _check_task_completion(self, current_task, remaining_tasks):
        """Check if current task is completed and start next task if it is"""
        if current_task.status == "completed":
            self._start_all_execute_next(remaining_tasks)
        elif current_task.status == "failed":
            messagebox.showerror("Error", f"Task failed: {current_task.episode_num}:{current_task.task_type}")
        elif current_task.status == "running":
            # Check again after 1 second
            self.root.after(1000, lambda: self._check_task_completion(current_task, remaining_tasks))

    def _start_all_execute_next(self, remaining_tasks):
        """Execute next task in the sequence"""
        if remaining_tasks:
            self._start_all()

    def _stop_all(self):
        """Stop all running tasks"""
        for task in self.project.tasks:
            if task.status == "running":
                self._stop_task(task)

    def _pause_all(self):
        """Pause all running tasks"""
        for task in self.project.tasks:
            if task.status == "running":
                self._pause_task(task)

    def _find_task(self, episode, task_type):
        for task in self.project.tasks:
            if task.episode_num == episode and task.task_type == task_type:
                return task
        return None

    def _start_task(self, task):
        if not self._check_prerequisites(task):
            messagebox.showwarning("Warning", "Prerequisites not met")
            return

        # 如果是编码任务，在运行时构造命令
        if task.task_type == "video" or (("hardsub_" in task.task_type) and ("merge" not in task.task_type)):
            # 只有视频编码任务和硬字幕编码任务（非合并）需要构造编码命令
            params = (self.project.current_hardsub_x265_params 
                    if task.custom_params.get("is_hardsub") 
                    else self.project.current_normal_x265_params)
            
            x265_command = self.project.generate_x265_command(params)
            if isinstance(x265_command, list):
                x265_params = ' '.join(x265_command[1:])  # 去掉 "x265" 命令本身
                task.command = (
                    f'vspipe -c y4m "{task.custom_params["input_vpy"]}" - | '
                    f'x265 --input - --y4m {x265_params} '
                    f'-o "{task.custom_params["output_mkv"]}"'
                )
            else:
                task.command = f'{x265_command} --input="{task.custom_params["input_vpy"]}" -o "{task.custom_params["output_mkv"]}"'

        task.status = "running"
        task.start_time = datetime.now()
        task.output = []

        output_queue = Queue.Queue()
        self.output_queues[task] = output_queue

        if task.command is None:
            task.status = "failed"
            self.output_text.insert(tk.END, f"任务命令未正确设置: {task.task_type}\n")
            self.output_text.see(tk.END)
            return

        try:
            # 创建进程，使用进程组
            process = subprocess.Popen(
                task.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                shell=True,
                cwd=task.work_dir,
                preexec_fn=os.setsid  # 创建新的进程组
            )
            
            task.process = process
            task.status = "running"
            task.start_time = datetime.now()
            
            self.running_tasks[id(task)] = (task, output_queue)
            threading.Thread(
                target=self._read_output,
                args=(task, process, output_queue),
                daemon=True
            ).start()

            self._refresh_task_tree()
            
        except Exception as e:
            task.status = "failed"
            self.output_text.insert(tk.END, f"启动任务失败: {str(e)}\n")
            self.output_text.see(tk.END)

    def _check_prerequisites(self, task):
        if not task.prerequisites:
            return True

        for prereq in task.prerequisites:
            prereq_task = self._find_task(task.episode_num, prereq)
            if not prereq_task or prereq_task.status != "completed":
                return False
        return True

    def _read_output(self, task, process, queue):
        try:
            while True:
                line = process.stdout.readline()
                if not line:  # EOF
                    break
                if task.status == "stopped":
                    break
                queue.put(line)
        except (IOError, ValueError) as e:
            # 进程被终止时可能会抛出这些异常
            if task.status != "stopped":
                print(f"Error reading output: {e}")
        finally:
            # 确保进程被终止
            try:
                if process.poll() is None:  # 如果进程还在运行
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except Exception as e:
                print(f"Error in final process cleanup: {e}")

    def _update_task_output(self, task, output):
        task.output.append(output)
        self.output_text.insert(tk.END, f"[{task.episode_num}:{task.task_type}] {output}")
        self.output_text.see(tk.END)

    def _task_completed(self, task):
        task.end_time = datetime.now()
        task.status = "completed" if task.process.returncode == 0 else "failed"
        self._refresh_task_tree()

    def _stop_task(self, task):
        if task.process:
            try:
                # 向整个进程组发送 SIGTERM 信号
                os.killpg(os.getpgid(task.process.pid), signal.SIGTERM)
                
                # 等待进程结束，但最多等待 5 秒
                try:
                    task.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # 如果进程没有响应 SIGTERM，使用 SIGKILL 强制终止
                    os.killpg(os.getpgid(task.process.pid), signal.SIGKILL)
                
                # 关闭管道
                if task.process.stdout:
                    task.process.stdout.close()
                if task.process.stderr:
                    task.process.stderr.close()
                
                task.status = "stopped"
                task.end_time = datetime.now()
                
                # 从运行任务列表中移除
                task_id = id(task)
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
                
                self._refresh_task_tree()
                
                # 添加停止信息到输出
                self.output_text.insert(tk.END, 
                    f"[{task.episode_num}:{task.task_type}] Task stopped by user\n")
                self.output_text.see(tk.END)
                
            except ProcessLookupError:
                # 进程可能已经结束
                pass
            except Exception as e:
                print(f"Error stopping task: {e}")

    def _pause_task(self, task):
        if task.process:
            try:
                if task.paused:
                    # 恢复进程组
                    os.killpg(os.getpgid(task.process.pid), signal.SIGCONT)
                    task.paused = False
                    self.output_text.insert(tk.END, 
                        f"[{task.episode_num}:{task.task_type}] Task resumed\n")
                else:
                    # 暂停进程组
                    os.killpg(os.getpgid(task.process.pid), signal.SIGSTOP)
                    task.paused = True
                    self.output_text.insert(tk.END, 
                        f"[{task.episode_num}:{task.task_type}] Task paused\n")
                self.output_text.see(tk.END)
            except ProcessLookupError:
                # 进程可能已经结束
                pass
            except Exception as e:
                print(f"Error pausing/resuming task: {e}")

    def run(self):
        self.root.mainloop()

def main():
    gui = EncodingGUI()
    gui.run()

if __name__ == "__main__":
    main()
