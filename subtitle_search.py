# --- START OF FILE subtitle_search_optimized.py ---

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import os
import re
from pathlib import Path
import json
import requests
import threading
import time # 引入 time 模块，用于简单的延迟或状态更新

# --- Constants ---
CONFIG_DIR_NAME = "SubtitleSearcher"
CONFIG_FILE_NAME = "translator_config.json"
SUPPORTED_ENCODINGS = ['utf-8', 'gbk', 'gb2312', 'utf-16']
# 定义API端点和参数结构，方便管理
API_ENDPOINTS = {
    "Azure": {
        "url": "https://api.cognitive.microsofttranslator.com/translate",
        "params": {'api-version': '3.0', 'from': 'en', 'to': 'zh-Hans'},
        "headers": {'Content-type': 'application/json'},
        "body_template": [{'text': '{text}'}]
    },
    "Google_Paid": {
        "url": "https://translation.googleapis.com/language/translate/v2",
        "params": {'source': 'en', 'target': 'zh-CN'}, # 使用 zh-CN 可能更通用
        "method": "POST" # 明确指定 POST
    },
    "Google_Free": {
        "url": "https://translate.googleapis.com/translate_a/single",
        "params": {'client': 'gtx', 'sl': 'en', 'tl': 'zh-CN', 'dt': 't'},
        "method": "GET"
    },
    "DeepL": {
        "url": "https://api-free.deepl.com/v2/translate",
        "params": {'source_lang': 'EN', 'target_lang': 'ZH'},
        "method": "POST"
    }
}

class TranslatorService:
    def __init__(self):
        # 使用常量定义路径
        self.config_dir = Path.home() / "AppData" / "Local" / CONFIG_DIR_NAME
        self.config_file = self.config_dir / CONFIG_FILE_NAME
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 默认配置
        self.current_service = None
        self.azure_key = ""
        self.azure_region = ""
        self.google_key = ""
        self.deepl_key = ""

        self.load_config()

    def load_config(self):
        """加载翻译配置，增加更具体的错误处理"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.current_service = config.get('current_service')
                    self.azure_key = config.get('azure_key', '')
                    self.azure_region = config.get('azure_region', '')
                    self.google_key = config.get('google_key', '')
                    self.deepl_key = config.get('deepl_key', '')
        except json.JSONDecodeError as e:
            print(f"加载翻译配置失败: JSON 格式错误 - {e}")
            # 可以选择删除损坏的配置文件或提示用户
        except Exception as e:
            print(f"加载翻译配置失败: {e}")

    def save_config(self):
        """保存翻译配置"""
        try:
            config = {
                'current_service': self.current_service,
                'azure_key': self.azure_key,
                'azure_region': self.azure_region,
                'google_key': self.google_key,
                'deepl_key': self.deepl_key
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                # indent=4 使 JSON 文件更易读
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存翻译配置失败: {e}")

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """封装 requests 调用，统一处理超时和基本错误"""
        try:
            # 设置超时时间，防止无限等待
            response = requests.request(method, url, timeout=10, **kwargs)
            response.raise_for_status() # 检查 HTTP 错误 (4xx or 5xx)
            return response
        except requests.exceptions.Timeout:
            raise TimeoutError("请求超时")
        except requests.exceptions.RequestException as e:
            # 处理其他网络相关错误
            raise ConnectionError(f"网络请求失败: {e}")

    def test_api(self, service: str, **kwargs) -> tuple[bool, str]:
        """
        测试API是否有效。
        允许传入临时的 key/region 进行测试，方便设置窗口直接测试输入值。
        """
        test_text = "Hello, world!"
        azure_key = kwargs.get('azure_key', self.azure_key)
        azure_region = kwargs.get('azure_region', self.azure_region)
        google_key = kwargs.get('google_key', self.google_key)
        deepl_key = kwargs.get('deepl_key', self.deepl_key)

        try:
            translated_text = ""
            if service == "Azure":
                if not azure_key or not azure_region:
                    return False, "请填写 Azure API Key 和 Region"
                translated_text = self._translate_azure(test_text, azure_key, azure_region)
            elif service == "Google":
                # 测试时优先测试付费API（如果Key存在）
                if google_key:
                    translated_text = self._translate_google_paid(test_text, google_key)
                else:
                    # 简单测试免费接口是否能通，但不保证翻译质量
                    translated_text = self._translate_google_free(test_text)
            elif service == "DeepL":
                if not deepl_key:
                    return False, "请填写 DeepL API Key"
                translated_text = self._translate_deepl(test_text, deepl_key)
            else:
                return False, f"未知的服务: {service}"

            # 增加一个简单的检查，看是否真的返回了内容
            if translated_text and isinstance(translated_text, str) and translated_text != test_text:
                 return True, f"{service} API 测试成功"
            else:
                return False, f"{service} API 测试似乎成功，但未返回预期翻译结果。"

        except (ConnectionError, TimeoutError, ValueError, KeyError, IndexError) as e:
            return False, f"{service} API 测试失败: {str(e)}"
        except Exception as e: # 捕获其他未知错误
            return False, f"{service} API 测试遇到未知错误: {str(e)}"

    def translate(self, text: str) -> str:
        """翻译文本 (主入口)"""
        if not self.current_service:
            return "[请先在设置中选择并配置翻译服务]"
        if not text or text.isspace():
             return "[无需翻译的空文本]"

        try:
            if self.current_service == "Azure":
                if not self.azure_key or not self.azure_region: return "[Azure Key/Region 未配置]"
                return self._translate_azure(text, self.azure_key, self.azure_region)
            elif self.current_service == "Google":
                # 优先使用付费API
                if self.google_key:
                    return self._translate_google_paid(text, self.google_key)
                else:
                    # 明确告知用户正在使用免费接口
                    # return "[Google Free] " + self._translate_google_free(text)
                    # 或者直接报错提示需要key
                    return "[Google API Key 未配置]"
                    # 注意：Google Free API 非常不稳定，不推荐在正式应用中使用
            elif self.current_service == "DeepL":
                if not self.deepl_key: return "[DeepL Key 未配置]"
                return self._translate_deepl(text, self.deepl_key)
            else:
                return "[未知的翻译服务]"
        except (ConnectionError, TimeoutError) as e:
            return f"[翻译网络错误: {str(e)}]"
        except (ValueError, KeyError, IndexError) as e:
            # 通常是API返回格式问题
             return f"[翻译服务返回错误: {str(e)}]"
        except Exception as e:
            # 其他所有未预料到的错误
            return f"[翻译时发生未知错误: {str(e)}]"

    # 将具体实现拆分为私有方法，方便测试和复用
    def _translate_azure(self, text: str, key: str, region: str) -> str:
        """使用Azure翻译 (内部实现)"""
        config = API_ENDPOINTS["Azure"]
        headers = {
            **config["headers"],
            'Ocp-Apim-Subscription-Key': key,
            'Ocp-Apim-Subscription-Region': region,
        }
        # 使用 str.format 或 f-string 替换模板中的文本
        body = json.loads(json.dumps(config["body_template"]).replace('{text}', text))

        response = self._make_request("POST", config["url"], params=config["params"], headers=headers, json=body)
        data = response.json()

        # 增强 JSON 结构检查
        if isinstance(data, list) and data and 'translations' in data[0] and \
           isinstance(data[0]['translations'], list) and data[0]['translations'] and \
           'text' in data[0]['translations'][0]:
            return data[0]['translations'][0]['text']
        else:
            raise ValueError(f"Azure API 返回了非预期的格式: {data}")

    def _translate_google_paid(self, text: str, key: str) -> str:
        """使用Google翻译付费API (内部实现)"""
        config = API_ENDPOINTS["Google_Paid"]
        params = {
            **config["params"],
            'key': key,
            'q': text,
        }
        response = self._make_request(config["method"], config["url"], params=params)
        data = response.json()
        # 增强检查
        if 'data' in data and 'translations' in data['data'] and \
           isinstance(data['data']['translations'], list) and data['data']['translations'] and \
           'translatedText' in data['data']['translations'][0]:
            return data['data']['translations'][0]['translatedText']
        else:
             raise ValueError(f"Google Paid API 返回了非预期的格式: {data}")

    def _translate_google_free(self, text: str) -> str:
        """使用Google翻译免费API (内部实现 - 仅供测试或备用，不稳定)"""
        config = API_ENDPOINTS["Google_Free"]
        params = {
            **config["params"],
            'q': text
        }
        response = self._make_request(config["method"], config["url"], params=params)
        data = response.json()
        # 免费API的返回结构比较特别
        try:
            # 提取所有片段并连接
            translated_text = ''.join(item[0] for item in data[0] if item and item[0])
            if translated_text:
                return translated_text
            else:
                raise ValueError("Google Free API 返回内容为空")
        except (IndexError, TypeError):
             raise ValueError(f"Google Free API 返回了非预期的格式: {data}")

    def _translate_deepl(self, text: str, key: str) -> str:
        """使用DeepL翻译 (内部实现)"""
        config = API_ENDPOINTS["DeepL"]
        # DeepL 使用 data 而不是 params 或 json
        payload = {
            **config["params"],
            'auth_key': key,
            'text': text,
        }
        response = self._make_request(config["method"], config["url"], data=payload)
        data = response.json()
        # 增强检查
        if 'translations' in data and isinstance(data['translations'], list) and \
           data['translations'] and 'text' in data['translations'][0]:
            return data['translations'][0]['text']
        else:
             raise ValueError(f"DeepL API 返回了非预期的格式: {data}")


class SubtitleSearcher:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("字幕搜索工具 v1.1") # 加个版本号示例
        self.window.geometry("1000x800")

        # 使用更健壮的数据结构存储字幕
        # key: filename, value: list of tuples [(start_time, text), ...]
        self.subtitle_data = {}
        # 存储搜索结果的结构化数据
        # list of tuples [(filename, start_time, original_text), ...]
        self.search_results = []

        self.translator = TranslatorService()

        self.setup_ui()
        self._update_status("准备就绪")

    def _update_status(self, message: str, duration_ms: int = 0):
        """更新状态栏消息，可选自动清除"""
        self.status_var.set(message)
        if duration_ms > 0:
            self.window.after(duration_ms, lambda: self.status_var.set("准备就绪") if self.status_var.get() == message else None)

    def setup_ui(self):
        # --- Menu ---
        menubar = tk.Menu(self.window)
        self.window.config(menu=menubar)
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="翻译设置", command=self.show_translator_settings)

        # --- Top Buttons ---
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(pady=10, fill=tk.X, padx=10)
        ttk.Button(btn_frame, text="添加SRT文件", command=self.select_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="删除选中", command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清除所有", command=self.clear_all).pack(side=tk.LEFT, padx=5)

        # --- File List ---
        list_frame = ttk.LabelFrame(self.window, text="已加载的文件")
        list_frame.pack(padx=10, pady=(0, 5), fill=tk.BOTH) # 调整 pady
        self.file_tree = ttk.Treeview(list_frame, columns=("count",), height=6) # 减少默认高度
        self.file_tree.heading("#0", text="文件名")
        self.file_tree.heading("count", text="字幕数量")
        self.file_tree.column("#0", width=400, stretch=tk.YES)
        self.file_tree.column("count", width=100, anchor="center")
        # 添加滚动条
        tree_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=tree_scrollbar.set)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_tree.pack(padx=5, pady=5, fill=tk.BOTH, expand=True) # 让 Treeview 填充空间


        # --- Search Area ---
        search_frame = ttk.Frame(self.window)
        search_frame.pack(padx=10, pady=5, fill=tk.X)
        ttk.Label(search_frame, text="搜索内容:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        # 绑定回车键进行搜索
        self.search_entry.bind("<Return>", self.search)
        self.search_button = ttk.Button(search_frame, text="搜索", command=self.search)
        self.search_button.pack(side=tk.LEFT)

        # --- Results Area ---
        result_frame = ttk.LabelFrame(self.window, text="搜索结果")
        result_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # --- Translate Buttons ---
        translate_frame = ttk.Frame(result_frame)
        translate_frame.pack(fill=tk.X, padx=5, pady=(5, 2)) # 调整 pady
        self.translate_btn = ttk.Button(translate_frame, text="翻译选中文本",
                                      command=self.translate_selected_wrapper, # 使用包装器
                                      state='disabled')
        self.translate_btn.pack(side=tk.LEFT, padx=5)
        self.translate_all_btn = ttk.Button(translate_frame, text="翻译所有结果",
                                          command=self.translate_all_wrapper, # 使用包装器
                                          state='disabled')
        self.translate_all_btn.pack(side=tk.LEFT, padx=5)

        # --- Result Text Area ---
        self.result_text = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD) # 自动换行
        self.result_text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        # 配置 Tag 用于高亮显示原文和译文 (示例)
        self.result_text.tag_configure("original", foreground="black")
        self.result_text.tag_configure("translation", foreground="blue", lmargin1=10, lmargin2=10) # 缩进译文
        self.result_text.tag_configure("filename", foreground="green", font=('TkDefaultFont', 10, 'bold'))
        self.result_text.tag_configure("timestamp", foreground="gray")


        # --- Status Bar ---
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self.window, textvariable=self.status_var, anchor=tk.W) # 左对齐
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))

    def show_translator_settings(self):
        """显示翻译设置窗口 (优化测试逻辑)"""
        settings_win = tk.Toplevel(self.window)
        settings_win.title("翻译设置")
        settings_win.geometry("550x450") # 稍微调整大小
        settings_win.transient(self.window)
        settings_win.grab_set() # 模态窗口

        # --- Service Selection ---
        service_frame = ttk.LabelFrame(settings_win, text="选择翻译服务")
        service_frame.pack(padx=10, pady=5, fill=tk.X)
        service_var = tk.StringVar(value=self.translator.current_service or "")
        for service in ["Azure", "Google", "DeepL"]:
            rb = ttk.Radiobutton(service_frame, text=service, value=service, variable=service_var)
            rb.pack(anchor=tk.W, padx=5, pady=2)

        # --- API Settings ---
        api_frame = ttk.LabelFrame(settings_win, text="API 配置 (保存后生效)")
        api_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # Helper to create entry rows
        def create_entry_row(parent, label_text, value, show_char=None):
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, padx=5, pady=5)
            ttk.Label(frame, text=label_text, width=12).pack(side=tk.LEFT) # 固定宽度
            entry = ttk.Entry(frame, show=show_char)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            entry.insert(0, value)
            return frame, entry

        # Azure
        azure_frame, azure_key_entry = create_entry_row(api_frame, "Azure Key:", self.translator.azure_key, "*")
        _, azure_region_entry = create_entry_row(api_frame, "Azure Region:", self.translator.azure_region)
        test_azure_btn = ttk.Button(azure_frame, text="测试",
                   command=lambda: self.test_api_from_settings(
                       "Azure", settings_win,
                       azure_key=azure_key_entry.get(),
                       azure_region=azure_region_entry.get()
                   ))
        test_azure_btn.pack(side=tk.RIGHT, padx=(0, 5)) # 移到 Key 行的右边

        # Google
        google_frame, google_key_entry = create_entry_row(api_frame, "Google Key:", self.translator.google_key, "*")
        # 添加 Google 免费 API 提示
        google_note_label = ttk.Label(api_frame, text=" (留空将尝试使用不稳定的免费接口 - 不推荐)", foreground="gray")
        google_note_label.pack(anchor=tk.W, padx=15)
        test_google_btn = ttk.Button(google_frame, text="测试",
                   command=lambda: self.test_api_from_settings(
                       "Google", settings_win,
                       google_key=google_key_entry.get()
                   ))
        test_google_btn.pack(side=tk.RIGHT, padx=(0, 5))


        # DeepL
        deepl_frame, deepl_key_entry = create_entry_row(api_frame, "DeepL Key:", self.translator.deepl_key, "*")
        test_deepl_btn = ttk.Button(deepl_frame, text="测试",
                   command=lambda: self.test_api_from_settings(
                       "DeepL", settings_win,
                       deepl_key=deepl_key_entry.get()
                   ))
        test_deepl_btn.pack(side=tk.RIGHT, padx=(0, 5))

        # --- Save/Cancel Buttons ---
        def save_settings():
            # 获取输入值
            selected_service = service_var.get()
            new_azure_key = azure_key_entry.get()
            new_azure_region = azure_region_entry.get()
            new_google_key = google_key_entry.get()
            new_deepl_key = deepl_key_entry.get()

            # 更新 TranslatorService 实例
            self.translator.current_service = selected_service
            self.translator.azure_key = new_azure_key
            self.translator.azure_region = new_azure_region
            self.translator.google_key = new_google_key
            self.translator.deepl_key = new_deepl_key

            # 保存配置到文件
            self.translator.save_config()
            settings_win.destroy()
            messagebox.showinfo("成功", "设置已保存", parent=self.window) # parent=self.window
            self._update_status("翻译设置已更新")

        btn_frame_bottom = ttk.Frame(settings_win)
        btn_frame_bottom.pack(pady=15)
        ttk.Button(btn_frame_bottom, text="保存", command=save_settings).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame_bottom, text="取消", command=settings_win.destroy).pack(side=tk.LEFT, padx=10)

        # 绑定 Esc 键关闭窗口
        settings_win.bind("<Escape>", lambda e: settings_win.destroy())

    def test_api_from_settings(self, service, parent_window, **kwargs):
        """在设置窗口中测试API，使用输入框中的当前值"""
        # 可以在测试前禁用按钮，测试后恢复
        # (这里省略了禁用/启用逻辑，但可以添加)
        messagebox.showinfo("测试中", f"正在测试 {service} API...", parent=parent_window)
        # 使用传入的kwargs（来自Entry的值）进行测试
        success, message = self.translator.test_api(service, **kwargs)
        if success:
            messagebox.showinfo("成功", message, parent=parent_window)
        else:
            messagebox.showerror("失败", message, parent=parent_window)

    def select_files(self):
        """选择并加载文件，增加进度反馈"""
        files = filedialog.askopenfilenames(
            title="选择一个或多个SRT文件",
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")],
            parent=self.window
        )
        if not files:
            return

        loaded_count = 0
        error_files = []
        self._update_status(f"开始加载 {len(files)} 个文件...")

        for i, file_path in enumerate(files):
            filename = os.path.basename(file_path)
            # 避免重复加载
            if filename in self.subtitle_data:
                self._update_status(f"跳过已加载的文件: {filename}")
                continue

            try:
                # 可以在后台线程加载大文件，但这里为简单起见直接加载
                self.load_srt_file(file_path)
                loaded_count += 1
                self._update_status(f"加载中 ({i+1}/{len(files)}): {filename}")
            except ValueError as e: # 特定捕获 load_srt_file 抛出的编码错误
                error_files.append(f"{filename} ({e})")
                self._update_status(f"加载失败: {filename}")
            except Exception as e:
                error_files.append(f"{filename} (未知错误: {e})")
                self._update_status(f"加载失败: {filename}")
            # 短暂yield，让UI有机会更新状态
            self.window.update_idletasks()

        self.update_file_list()
        final_status = f"加载完成: 成功 {loaded_count} 个"
        if error_files:
            final_status += f", 失败 {len(error_files)} 个。"
            messagebox.showerror("加载错误", "以下文件加载失败:\n" + "\n".join(error_files), parent=self.window)
        else:
            final_status += "。"
        self._update_status(final_status, 5000) # 状态持续5秒

    def load_srt_file(self, file_path):
        """加载单个SRT文件，优化错误处理和解析"""
        content = None
        detected_encoding = None
        for encoding in SUPPORTED_ENCODINGS:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                detected_encoding = encoding
                break # 成功读取即跳出
            except UnicodeDecodeError:
                continue
            except Exception as e:
                # 捕获其他可能的读取错误，如权限问题
                print(f"读取文件 {file_path} 时发生非编码错误 (尝试 {encoding}): {e}")
                continue # 继续尝试下一种编码

        if content is None:
            # 如果所有编码都失败
            raise ValueError("无法使用支持的编码解码文件")

        # 改进的SRT解析正则表达式，更容忍微小格式差异（如时间戳后的空格）
        # 捕获字幕索引、开始时间、结束时间、文本内容
        # 使用 re.DOTALL 让 . 匹配换行符
        # 使用非贪婪匹配 .*?
        # pattern = r'(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3}).*?\n(.*?)(?=\n\n|\n\d+\s*\n|\Z)'
        # 更简单的模式，只关心时间和文本，忽略索引和结束时间，适应性可能更强
        pattern = r'(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->.*?[\n\r]+(.*?)[\n\r]{2,}'

        filename = os.path.basename(file_path)
        subtitles = []
        try:
            # 使用 re.finditer 获得匹配对象，更灵活
            for match in re.finditer(pattern, content, re.DOTALL | re.MULTILINE):
                start_time = match.group(1).replace('.', ',') # 统一时间格式为逗号
                text_block = match.group(2).strip()
                # 清理文本：移除HTML标签（常见于某些SRT），合并多行
                clean_text = re.sub(r'<.*?>', '', text_block) # 移除HTML标签
                clean_text = ' '.join(line.strip() for line in clean_text.splitlines() if line.strip())
                if clean_text: # 确保文本不为空
                    subtitles.append((start_time, clean_text))

            # 处理可能的最后一个字幕块（没有紧跟两个换行符）
            # 这部分逻辑比较复杂，可以简化为要求 SRT 文件末尾有空行
            # 或者使用更专业的 SRT 解析库

            if not subtitles:
                 # 如果标准正则没匹配到，尝试一个更宽松的模式（如果需要）
                 print(f"警告：文件 {filename} 使用标准模式未解析到字幕，可能格式特殊。")
                 # 可以选择抛出错误或允许加载空文件

        except Exception as e:
            raise RuntimeError(f"解析 SRT 文件内容时出错: {e}")

        if subtitles:
            self.subtitle_data[filename] = subtitles
        else:
            # 可以选择不加载空文件或格式错误的文件
             raise ValueError("未能解析到有效的字幕条目")


    def update_file_list(self):
        """更新文件列表显示"""
        # 记录当前选中的项
        selected_items = self.file_tree.selection()

        # 清空列表
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)

        # 重新填充
        sorted_filenames = sorted(self.subtitle_data.keys())
        for filename in sorted_filenames:
            subtitles = self.subtitle_data[filename]
            # 使用 iid (item ID) 存储文件名，更安全，避免特殊字符问题
            self.file_tree.insert("", "end", iid=filename, text=filename, values=(f"{len(subtitles)}条",))

        # 尝试恢复之前的选中状态 (如果文件还在)
        items_to_reselect = [item for item in selected_items if self.file_tree.exists(item)]
        if items_to_reselect:
            self.file_tree.selection_set(items_to_reselect)
            # 可以滚动到第一个选中的项
            # self.file_tree.see(items_to_reselect[0])

    def delete_selected(self):
        """删除选中的文件"""
        selected_items = self.file_tree.selection() # 获取的是 iid (文件名)
        if not selected_items:
            messagebox.showwarning("提示", "请先在文件列表中选择要删除的文件", parent=self.window)
            return

        if messagebox.askyesno("确认删除", f"确定要从列表中移除选定的 {len(selected_items)} 个文件吗？\n(这不会删除原始文件)", parent=self.window):
            filenames_to_delete = list(selected_items) # 创建副本以防迭代问题
            deleted_count = 0
            for filename in filenames_to_delete:
                if filename in self.subtitle_data:
                    del self.subtitle_data[filename]
                    deleted_count += 1
                    # 从 Treeview 中移除
                    if self.file_tree.exists(filename):
                        self.file_tree.delete(filename)

            self._update_status(f"已移除 {deleted_count} 个文件", 3000)
            # 如果删除了文件，可能需要清空搜索结果
            self.clear_search_results()

    def clear_all(self):
        """清除所有已加载的文件和结果"""
        if not self.subtitle_data:
            messagebox.showinfo("提示", "当前没有已加载的文件。", parent=self.window)
            return

        if messagebox.askyesno("确认清除", "确定要清除所有已加载的文件和搜索结果吗？", parent=self.window):
            self.subtitle_data.clear()
            self.update_file_list()
            self.clear_search_results()
            self._update_status("已清除所有数据", 3000)

    def clear_search_results(self):
        """清空搜索结果区域和相关状态"""
        self.search_results.clear()
        self.result_text.config(state=tk.NORMAL) # 允许修改
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state=tk.DISABLED) # 改回只读（如果需要）
        self.translate_btn.config(state='disabled')
        self.translate_all_btn.config(state='disabled')
        # 清空搜索框？（可选）
        # self.search_entry.delete(0, tk.END)

    def search(self, event=None): # 添加 event 参数以响应回车键
        """搜索对白，并将结果存入 self.search_results"""
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入搜索关键字", parent=self.window)
            return

        if not self.subtitle_data:
            messagebox.showwarning("提示", "请先添加 SRT 文件", parent=self.window)
            return

        self._update_status(f"正在搜索 \"{query}\"...")
        self.window.config(cursor="watch") # 设置等待光标
        self.search_button.config(state='disabled') # 禁用搜索按钮

        # 清空上次结果
        self.search_results.clear()
        total_matches = 0

        # 在后台线程执行搜索，避免大数据量时卡顿
        def search_task():
            nonlocal total_matches
            temp_results = []
            query_lower = query.lower() # 预先转小写以提高效率

            # 遍历所有文件和字幕
            # 使用 items() 遍历字典更标准
            for filename, subtitles in self.subtitle_data.items():
                file_matches = []
                for start_time, text in subtitles:
                    if query_lower in text.lower():
                        # 存储结构化结果
                        temp_results.append((filename, start_time, text))
                        total_matches += 1

            # 搜索完成后，通过 after 更新 UI
            def update_ui_after_search():
                self.search_results = temp_results # 更新主线程的列表

                self.result_text.config(state=tk.NORMAL)
                self.result_text.delete(1.0, tk.END)

                if not self.search_results:
                    self.result_text.insert(tk.END, "未找到匹配的对白")
                    self.translate_btn.config(state='disabled')
                    self.translate_all_btn.config(state='disabled')
                    self._update_status(f"未找到 \"{query}\" 的匹配结果", 3000)
                else:
                    # 格式化显示结果
                    self.result_text.insert(tk.END, f"找到 {total_matches} 个匹配结果:\n\n")
                    current_filename = None
                    for fn, time, txt in self.search_results:
                        if fn != current_filename:
                            if current_filename is not None:
                                self.result_text.insert(tk.END, "\n") # 文件间加空行
                            self.result_text.insert(tk.END, f"【{fn}】\n", "filename")
                            current_filename = fn
                        self.result_text.insert(tk.END, f"  时间: {time}\n", "timestamp")
                        self.result_text.insert(tk.END, f"  对白: {txt}\n\n", "original")

                    self.translate_btn.config(state='normal')
                    self.translate_all_btn.config(state='normal')
                    self._update_status(f"搜索完成，找到 {total_matches} 个结果", 5000)

                self.result_text.config(state=tk.DISABLED) # 设为只读
                self.window.config(cursor="") # 恢复默认光标
                self.search_button.config(state='normal') # 恢复搜索按钮

            self.window.after(0, update_ui_after_search)

        # 启动搜索线程
        threading.Thread(target=search_task, daemon=True).start()


    # --- Translation Wrappers and Implementation ---

    def _run_threaded_task(self, task_func, busy_message, completion_message):
        """通用方法：在线程中运行任务，并更新UI状态"""
        if not hasattr(self, '_active_thread') or not self._active_thread or not self._active_thread.is_alive():
            self._update_status(busy_message)
            # 禁用相关按钮
            self.translate_btn.config(state='disabled')
            self.translate_all_btn.config(state='disabled')
            self.search_button.config(state='disabled') # 可能也需要禁用搜索
            self.window.config(cursor="wait")

            def task_wrapper():
                try:
                    task_func()
                    # 任务成功完成
                    self.window.after(0, lambda: self._update_status(completion_message, 5000))
                except Exception as e:
                    # 任务出错
                    print(f"后台任务出错: {e}") # 打印详细错误到控制台
                    self.window.after(0, lambda: messagebox.showerror("错误", f"操作失败: {e}", parent=self.window))
                    self.window.after(0, lambda: self._update_status("操作失败", 3000))
                finally:
                    # 无论成功或失败，最后恢复UI
                    def restore_ui():
                        # 只有在有结果时才恢复翻译按钮
                        results_exist = bool(self.search_results)
                        self.translate_btn.config(state='normal' if results_exist else 'disabled')
                        self.translate_all_btn.config(state='normal' if results_exist else 'disabled')
                        self.search_button.config(state='normal')
                        self.window.config(cursor="")
                        self._active_thread = None # 标记线程结束

                    self.window.after(0, restore_ui)

            self._active_thread = threading.Thread(target=task_wrapper, daemon=True)
            self._active_thread.start()
        else:
            messagebox.showwarning("请稍候", "当前有其他操作正在进行中...", parent=self.window)


    def translate_selected_wrapper(self):
        """包装器：用于启动单条翻译的线程任务"""
        try:
            # 检查是否有选中内容
            selected_range = self.result_text.tag_ranges(tk.SEL)
            if not selected_range:
                messagebox.showinfo("提示", "请先在结果区域选择要翻译的文本块", parent=self.window)
                return

            # 获取选中内容
            selected_text = self.result_text.get(selected_range[0], selected_range[1])
            if not selected_text or selected_text.isspace():
                 messagebox.showinfo("提示", "选中的文本为空", parent=self.window)
                 return

            # 简单提取需要翻译的文本（如果包含"对白:"，取其后的内容）
            text_to_translate = selected_text
            if "对白:" in selected_text:
                parts = selected_text.split("对白:", 1)
                if len(parts) > 1:
                     # 取 "对白:" 之后到下一个空行之前的部分
                    text_to_translate = parts[1].split('\n\n', 1)[0].strip()


            if not text_to_translate or text_to_translate.isspace():
                 messagebox.showinfo("提示", "未能从选中内容中提取有效文本进行翻译", parent=self.window)
                 return

            # 使用通用线程执行器
            self._run_threaded_task(
                lambda: self._translate_and_insert(text_to_translate, selected_range),
                "正在翻译选中文本...",
                "选中文本翻译完成"
            )

        except tk.TclError:
            messagebox.showinfo("提示", "请先在结果区域选择要翻译的文本块", parent=self.window)
        except Exception as e:
             messagebox.showerror("错误", f"准备翻译时出错: {e}", parent=self.window)


    def _translate_and_insert(self, original_text, selection_range):
        """实际执行单条翻译并在UI中插入结果（在工作线程中调用）"""
        translated = self.translator.translate(original_text)

        # 准备插入的文本，带标签
        insert_text = f"\n译文: {translated}\n"

        # 回到主线程更新UI
        def update_text_area():
            # 检查选区是否仍然有效
            try:
                current_selection = self.result_text.tag_ranges(tk.SEL)
                # 如果选区与开始时不同，可能用户已改变选择，则不插入
                if current_selection != selection_range:
                    print("选区已改变，取消插入翻译结果。")
                    return
            except tk.TclError: # 如果没有选区了
                 print("选区丢失，取消插入翻译结果。")
                 return

            self.result_text.config(state=tk.NORMAL)
            # 在选区之后插入译文
            insert_pos = selection_range[1] # 在选区末尾插入
            self.result_text.insert(insert_pos, insert_text, "translation")
            # 可以选择移除原来的选区高亮
            self.result_text.tag_remove(tk.SEL, "1.0", tk.END)
            self.result_text.config(state=tk.DISABLED)

        self.window.after(0, update_text_area)


    def translate_all_wrapper(self):
        """包装器：用于启动全部翻译的线程任务"""
        if not self.search_results:
            messagebox.showinfo("提示", "没有搜索结果可供翻译", parent=self.window)
            return

        if messagebox.askyesno("确认翻译", f"将翻译当前显示的 {len(self.search_results)} 条结果，可能需要一些时间并消耗API配额。\n确定要继续吗？", parent=self.window):
            self._run_threaded_task(
                self._translate_all_results,
                f"正在翻译 {len(self.search_results)} 条结果...",
                f"全部 {len(self.search_results)} 条结果翻译完成"
            )

    def _translate_all_results(self):
        """实际执行所有结果的翻译（在工作线程中调用）"""
        translated_results_data = [] # 存储 (filename, time, original, translated)
        total = len(self.search_results)
        completed = 0
        last_status_update_time = time.time()

        for filename, start_time, original_text in self.search_results:
            translated = self.translator.translate(original_text)
            translated_results_data.append((filename, start_time, original_text, translated))
            completed += 1

            # 更新状态栏进度 (不需要太频繁)
            current_time = time.time()
            if current_time - last_status_update_time >= 0.5 or completed == total: # 每0.5秒或最后一条更新
                progress_msg = f"翻译进度: {completed}/{total}"
                self.window.after(0, lambda msg=progress_msg: self._update_status(msg))
                last_status_update_time = current_time

        # 翻译完成后，更新结果文本区域
        def update_ui_with_all_translations():
            self.result_text.config(state=tk.NORMAL)
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"共翻译 {len(translated_results_data)} 条结果:\n\n")

            current_filename = None
            for fn, time, original, translated in translated_results_data:
                if fn != current_filename:
                    if current_filename is not None:
                        self.result_text.insert(tk.END, "\n")
                    self.result_text.insert(tk.END, f"【{fn}】\n", "filename")
                    current_filename = fn
                self.result_text.insert(tk.END, f"  时间: {time}\n", "timestamp")
                self.result_text.insert(tk.END, f"  对白: {original}\n", "original")
                # 给译文加上标签
                self.result_text.insert(tk.END, f"  译文: {translated}\n\n", "translation")

            self.result_text.config(state=tk.DISABLED)

        self.window.after(0, update_ui_with_all_translations)

    def run(self):
        """启动应用主循环"""
        self.window.mainloop()

# --- Entry Point ---
if __name__ == "__main__":
    # 可以添加全局异常捕获，以防 Tkinter 之外的错误导致程序崩溃
    try:
        app = SubtitleSearcher()
        app.run()
    except Exception as e:
        # 记录或显示严重错误
        print(f"应用程序发生未捕获的致命错误: {e}")
        # 可以尝试弹出一个简单的错误消息框
        try:
            root = tk.Tk()
            root.withdraw() # 隐藏主窗口
            messagebox.showerror("严重错误", f"应用程序遇到无法恢复的错误:\n{e}\n\n请查看控制台日志获取详细信息。")
        except tk.TclError:
            pass # 如果 Tkinter 本身都无法初始化，就没办法了
