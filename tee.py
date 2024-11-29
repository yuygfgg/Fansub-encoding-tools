import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
import shlex
import hashlib
import colorsys
import queue

class LogWindow:
    def __init__(self, command, color):
        self.window = tk.Toplevel()
        self.command = command
        name = command.split()[0]

        self.window.title(f"Encoder: {name}")
        self.window.geometry("800x600")

        self.text = scrolledtext.ScrolledText(
            self.window,
            wrap=tk.WORD,
            background='black',
            foreground=color,
            font=('Consolas', 10)
        )
        self.text.pack(expand=True, fill='both')

        self.autoscroll = True

        self.text.vbar.bind("<Button-1>", self.on_scroll)

        self.text.insert('end', f"Command: {command}\n\n")
        self.text.see('end')

        self.log_queue = queue.Queue()
        self.update_log()

    def on_scroll(self, event):
        self.autoscroll = False
        if self.text.yview()[1] == 1.0:
            self.autoscroll = True

    def append_log(self, text):
        self.log_queue.put(text)

    def update_log(self):
        while not self.log_queue.empty():
            text = self.log_queue.get()
            self.text.insert('end', text + '\n')
            if self.autoscroll:
                self.text.see('end')
        self.window.after(100, self.update_log)

def get_color_mapping(commands):
    hash_values = {
        cmd: int(hashlib.sha1(cmd.encode()).hexdigest(), 16) / (2**160)
        for cmd in commands
    }
    sorted_commands = sorted(commands, key=lambda x: hash_values[x])
    colors = {}
    for i, cmd in enumerate(sorted_commands):
        hue = (i * 360 / len(commands)) % 360
        rgb = colorsys.hls_to_rgb(hue/360, 0.8, 0.8)
        hex_color = "#{:02x}{:02x}{:02x}".format(
            int(rgb[0]*255),
            int(rgb[1]*255),
            int(rgb[2]*255)
        )
        colors[cmd] = hex_color
    return colors

def output_reader(proc, window):
    try:
        while True:
            output = proc.stdout.read(1024)
            if not output:
                break
            window.append_log(output.decode('utf-8', errors='ignore').strip())
    except Exception as e:
        print(f"Error reading output: {e}")

def copy_stdin(processes):
    while True:
        chunk = sys.stdin.buffer.read(10240*1024)
        if not chunk:
            break
        for proc in processes:
            try:
                proc.stdin.write(chunk)
                proc.stdin.flush()
            except:
                pass

    for proc in processes:
        try:
            proc.stdin.close()
        except:
            pass

def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py 'encoder1 args' 'encoder2 args' ...")
        return

    commands = sys.argv[1:]
    processes = []
    windows = {}

    root = tk.Tk()
    root.withdraw()

    colors = get_color_mapping(commands)

    for cmd in commands:
        window = LogWindow(cmd, colors[cmd])
        windows[cmd] = window

        proc = subprocess.Popen(
            shlex.split(cmd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0
        )
        processes.append(proc)

        thread = threading.Thread(
            target=output_reader,
            args=(proc, window),
            daemon=True
        )
        thread.start()

    copy_thread = threading.Thread(
        target=copy_stdin,
        args=(processes,),
        daemon=True
    )
    copy_thread.start()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in processes:
            try:
                proc.terminate()
            except:
                pass

if __name__ == "__main__":
    main()
