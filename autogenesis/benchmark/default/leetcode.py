import os
import time
import json
import re
import inflection
import asyncio
from typing import Optional, Dict, Any, Set, List, ClassVar
from pydantic import PrivateAttr, Field, ConfigDict
from playwright.async_api import async_playwright
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(verbose=True)

from autogenesis.logger import logger
from autogenesis.benchmark.types import Benchmark, Task, Stats
from autogenesis.registry import BENCHMARK
from autogenesis.utils import file_lock

# 创建提交锁，确保浏览器操作串行化
class SubmitLock:
    """用于序列化浏览器提交操作的锁"""
    _instance = None
    _lock = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._lock = asyncio.Lock()
        return cls._instance
    
    @property
    def lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock
    
    async def __aenter__(self):
        await self.lock.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        self.lock.release()

submit_lock = SubmitLock()

SYSTEM_PROMPT = """
You are a helpful assistant that solves LeetCode coding problems. Please think step by step and provide your solution code.

Output format:
The output should be a JSON object with the following fields:
{
    "reasoning": "Your step-by-step reasoning process",
    "result": "Your solution code".
}

Example:
Task ID: 1
Problem Name: Two Sum
Problem: Given an array of integers, return the two numbers such that they add up to a specific target.
Language: python3
Template:
```python
#
# @lc app=leetcode id=1 lang=python3
#
# [1] Two Sum
#

# @lc code=start
class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        
# @lc code=end
```

Output:
{
    "reasoning": "Step 1: I need to find two numbers that sum to the target. I can use a hashmap to store each number and its index as I iterate through the array.\\n\\nStep 2: For each number, I calculate the complement (target - current number). If the complement exists in the hashmap, I found the pair. Otherwise, I add the current number to the hashmap.\\n\\nStep 3: This approach has O(n) time complexity and O(n) space complexity.",
    "result": "#\\n# @lc app=leetcode id=1 lang=python3\\n#\\n# [1] Two Sum\\n#\\n\\n# @lc code=start\\nclass Solution:\\n    def twoSum(self, nums: List[int], target: int) -> List[int]:\\n        hashmap = {}\\n        for i, num in enumerate(nums):\\n            complement = target - num\\n            if complement in hashmap:\\n                return [hashmap[complement], i]\\n            hashmap[num] = i\\n        return []\\n# @lc code=end"
}

Please write your solution code base on your language template.
"""

class CodeSubmitter:
    def __init__(self, headless: bool = False, base_dir: Optional[str] = None):
        """
        Initialization: Automatically load configuration from environment variables
        Uses git workflow: clone -> write file -> commit -> push -> codespace pull -> open -> submit
        """
        self.username = os.getenv("GITHUB_USERNAME")
        self.password = os.getenv("GITHUB_PASSWORD")
        self.project_url = os.getenv("GITHUB_PROJECT_URL")
        self.codespace_url = os.getenv("GITHUB_CODESPACE_URL")
        self.leetcode_cookie = os.getenv("LEETCODE_COOKIE") or None

        self.playwright = None
        self.context = None
        self.page = None
        self.repo_path = None
        self.headless = headless

        # 标记是否需要在下次评测前同步 Codespace
        # 当 batch_push 以 sync_codespace=False 调用时，会设置为 True
        self._needs_sync = False

        # 预先设置 output_file，确保即使浏览器初始化失败也能保存结果
        self._setup_output_file(base_dir=base_dir)

    def _setup_output_file(self, base_dir: Optional[str] = None):
        """设置输出文件路径（不依赖浏览器初始化）"""
        self.output_dir = base_dir or os.path.join(os.getcwd(), "results")

        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"| ⚠️ Failed to create output directory: {e}")
            self.output_dir = "."

        self.output_file = os.path.join(self.output_dir, "results.jsonl")

    async def initialize(self):
        logger.info("| 🚀 Initializing LeetCode Benchmark Submitter...")
        
        self.repo_slug = self.project_url.rstrip('/').replace('https://github.com/', '').replace('http://github.com/', '')
        self.leetcode_cookie = os.getenv("LEETCODE_COOKIE") or None
        
        # output_file 已在 __init__ 中设置，这里只打印日志
        logger.info(f"| 📝 Results will be saved to: {self.output_file}")
        # 保持原始引用
        os.makedirs(self.base_dir, exist_ok=True)
        
        # 1. Setup git repository
        await self._setup_git_repo()
        
        # 2. Setup browser
        self.playwright = await async_playwright().start()
        user_data_dir = os.path.join(self.base_dir, "playwright_user_data")
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=self.headless,
            viewport={'width': 1280, 'height': 800},
            args=["--disable-blink-features=AutomationControlled"],
            permissions=["clipboard-read", "clipboard-write"]
        )
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # 3. Setup LeetCode cookie
        await self._setup_leetcode_cookie()
        
        # 4. Login GitHub and enter Codespace
        await self._login_and_navigate()
        
        # 5. Verify LeetCode login status
        await self._ensure_leetcode_login()
        
        logger.info("| ✅ Environment all ready, can start evaluation")

    

    async def save_result(self, task: Task) -> None:
        try:
            record = {
                "task_id": task.task_id,
                "prediction": task.extra.get("prediction"),
                "score": task.score,
                "metrics": task.extra.get("metrics"),
                "start_time": task.extra.get("start_time"),
                "end_time": task.extra.get("end_time"),
                "spend_time": task.extra.get("spend_time"),
            }
            with open(self.output_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record) + "\n")
            logger.info(f"| 💾 Saved result for Task {task.task_id} (Score: {task.score})")
        except Exception as e:
            logger.error(f"| ❌ Failed to save result to file: {e}")


    async def _setup_git_repo(self):
        """Create temp directory and clone the project"""
        logger.info("| 🔍 Cloning git repository...")
        
        repo_name = self.repo_slug.split('/')[-1]
        self.repo_path = os.path.join(self.base_dir, repo_name)
        
        # Convert to SSH format: git@github.com:username/repo.git
        ssh_url = f"git@github.com:{self.repo_slug}.git"
        
        try:
            if os.path.exists(self.repo_path):
                logger.info(f"| 🔍 Repository already exists, skipping clone")
                return
            await self._run_git_command(['clone', ssh_url, repo_name], self.base_dir)
            logger.info(f"| 🔍 Successfully cloned repository to {self.repo_path}")
        except Exception as e:
            raise Exception(f"| ❌ Failed to clone repository: {str(e)}")

    async def _run_git_command(self, args: List[str], cwd: str) -> str:
        """Run git command asynchronously"""
        process = await asyncio.create_subprocess_exec(
            'git', *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            raise Exception(f"Git command failed (exit {process.returncode}): {error_msg}")
        return stdout.decode().strip()
    
    async def _setup_leetcode_cookie(self):
        """Use Playwright to login and extract cookies to bypass Cloudflare 403"""
        logger.info("| 🔍 Logging in to LeetCode via browser to fetch session cookies...")
        
        try:
            if self.leetcode_cookie:
                logger.info("| 🔍 LeetCode cookie already exists, skipping login")
                return
            
            # 1. Navigate to login page
            await self.page.goto("https://leetcode.com/accounts/login/", wait_until="networkidle")
            await asyncio.sleep(2)

            # 2. Check if already logged in (due to persistent context)
            if "login" not in self.page.url:
                logger.info("| 🔍 Already logged in to LeetCode.")
            else:
                logger.info("| 🔍 Entering LeetCode credentials...")
                # LeetCode uses specific IDs for login inputs
                await self.page.fill('input[name="login"]', os.getenv("LEETCODE_USERNAME"))
                await self.page.fill('input[name="password"]', os.getenv("LEETCODE_PASSWORD"))
                
                # Click sign in and wait for navigation
                await self.page.click('button[type="submit"], #signin_btn')
                
                # Wait for navigation back to home or dashboard
                try:
                    await self.page.wait_for_url("https://leetcode.com/", timeout=20000)
                    logger.info("| ✅ LeetCode web login successful.")
                except:
                    logger.warning("| ⚠️ Login navigation timed out, checking cookies anyway...")

            # 3. Extract cookies from context
            cookies = await self.context.cookies()
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies if c['domain'].endswith("leetcode.com")])
            
            if "LEETCODE_SESSION" in cookie_str:
                self.leetcode_cookie = cookie_str
                logger.info(f"| ✅ Successfully extracted LeetCode cookies (length: {len(cookie_str)})")
            else:
                logger.error("| ❌ Failed to find LEETCODE_SESSION in cookies.")
                
        except Exception as e:
            logger.error(f"| ❌ Error during LeetCode cookie setup: {str(e)}")
            raise e

    async def _login_and_navigate(self):
        """Login GitHub and enter specified Codespace"""
        try:
            await self.page.goto("https://github.com/login")
            await asyncio.sleep(1)
            if await self.page.locator('input[name="login"]').count() > 0:
                logger.info("| 🔍 Logging in to GitHub...")
                await self.page.fill('input[name="login"]', self.username)
                await self.page.fill('input[name="password"]', self.password)
                await self.page.click('input[type="submit"][value="Sign in"]')
                await self.page.wait_for_url("https://github.com/", timeout=15000)
            
            logger.info(f"| 🔍 Visiting project: {self.project_url}")
            await self.page.goto(self.project_url)
            await asyncio.sleep(2)
            
            logger.info(f"| 🔍 Going to Codespace: {self.codespace_url} ...")
            await self.page.goto(self.codespace_url)
            await asyncio.sleep(10)
            
        except Exception as e:
            raise Exception(f"| ❌ Failed to enter Codespace: {str(e)}")

    async def _ensure_leetcode_login(self):
        """Check LeetCode plugin status, if not logged in then use Cookie to log in"""
        logger.info("| 🔍 Verifying LeetCode login status...")
        try:
            leetcode_icon = self.page.locator('a[aria-label="LeetCode"], li[aria-label="LeetCode"], .codicon-leetcode').first
            if await leetcode_icon.is_visible():
                await leetcode_icon.click()
                await asyncio.sleep(10)
            
            needs_login = await self.page.get_by_text("Sign in to LeetCode", exact=False).is_visible()
            
            if needs_login:
                logger.info("| 🔍 Detected not logged in, using Cookie to log in...")
                await self._perform_leetcode_login()
            else:
                logger.info("| 🔍 Looks like already logged in (or no login prompt detected).")
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.warning(f"| ⚠️ Non-fatal error occurred during LeetCode login verification: {e}")

    async def _perform_leetcode_login(self):
        await self.page.keyboard.press("F1")
        await asyncio.sleep(1)
        await self.page.keyboard.type("LeetCode: Sign In")
        await asyncio.sleep(0.5)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(1)
        await self.page.keyboard.press("Enter") 
        await asyncio.sleep(1)
        await self.page.keyboard.type("Cookie")
        await asyncio.sleep(0.5)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(1)
        
        logger.info("| 🔍 Entering Cookie...")
        json_cookie = json.dumps(self.leetcode_cookie)
        await self.page.evaluate(f"navigator.clipboard.writeText({json_cookie})")
        await asyncio.sleep(0.2)
        await self.page.keyboard.press("Control+V") 
        await asyncio.sleep(0.5)
        await self.page.keyboard.press("Enter")
        
        logger.info("| 🔍 Waiting for login to take effect...")
        await asyncio.sleep(30)

    async def _sync_codespace_repo(self):
        """[新增] 在 Codespace 执行 Git Pull 确保代码同步"""
        logger.info("| 🔄 Syncing Codespace with remote repository (Git Pull)...")
        
        # 此时可能没有打开的文件编辑器，点击 body 确保获取焦点以便唤起命令面板
        try:
            await self.page.click("body", timeout=1000)
        except:
            pass

        # 唤起命令面板
        await self.page.keyboard.press("Control+Shift+P")
        await asyncio.sleep(1)
        
        # 输入并执行 Git Pull
        await self.page.keyboard.type("Git: Pull")
        await asyncio.sleep(0.5)
        await self.page.keyboard.press("Enter")
        
        # 等待同步完成（根据网络情况可调整）
        logger.info("| ⏳ Waiting 5 seconds for git pull to complete...")
        await asyncio.sleep(5)

    async def _safe_close_all_editors(self, max_retries: int = 2) -> bool:
        """
        安全地关闭所有编辑器窗口，支持重试和错误处理。
        在多协程环境下，键盘操作可能会失败，此方法确保不会抛出异常。
        
        Args:
            max_retries: 最大重试次数
            
        Returns:
            是否成功关闭
        """
        for attempt in range(max_retries):
            try:
                # 先按 Escape 关闭可能存在的弹窗/命令面板
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
                
                # 打开命令面板
                await self.page.keyboard.press("Meta+Shift+P")
                #await self.page.keyboard.press("Control+Shift+P")
                await asyncio.sleep(0.5)
                
                # 输入关闭命令
                await self.page.keyboard.type("Close All Editors")
                await asyncio.sleep(0.3)
                
                # 执行
                await self.page.keyboard.press("Enter")
                await asyncio.sleep(0.5)
                
                return True
                
            except Exception as e:
                logger.warning(f"| ⚠️ Close editors attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    
        logger.warning("| ⚠️ Failed to close all editors, continuing anyway...")
        return False

    async def _open_editor_file(self, filename):
        """Open explorer and open code file"""
        logger.info(f"| 🔍 Opening work file: {filename}")
        
        # 先关闭所有已打开的编辑器
        await self._safe_close_all_editors()

        # Switch back to explorer
        explorer_icon = self.page.locator('li[aria-label="Explorer"], li[aria-label="资源管理器"], .codicon-files').first
        if await explorer_icon.is_visible():
            await explorer_icon.click()
            await asyncio.sleep(0.5)

        # Summon file search
        # 尝试点击编辑器区域，如果不存在（例如还没打开文件），则点击空白处
        try:
            await self.page.click('.monaco-editor', timeout=1000)
        except:
            await self.page.mouse.click(500, 500)
            
        await asyncio.sleep(0.5)
        await self.page.keyboard.press("Control+P")
        await asyncio.sleep(0.5)
        await self.page.keyboard.type(filename)
        await asyncio.sleep(1)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(2)

    # ==================== 批量提交方法 ====================
    
    async def batch_write_files(self, file_contents: List[Dict[str, str]]) -> List[str]:
        """
        批量写入代码文件到本地仓库
        
        Args:
            file_contents: [{"filename": "1.two-sum.py", "code": "..."}, ...]
        
        Returns:
            成功写入的文件名列表
        """
        written_files = []
        for item in file_contents:
            filename = item["filename"]
            code = item["code"]
            file_path = os.path.join(self.repo_path, filename)
            
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(code)
                written_files.append(filename)
                logger.info(f"| 📝 Written: {filename}")
            except Exception as e:
                logger.error(f"| ❌ Failed to write {filename}: {e}")
        
        return written_files
    
    async def batch_push(self, filenames: List[str], max_retries: int = 3, sync_codespace: bool = True) -> bool:
        """
        批量 git add, commit, push 多个文件，支持重试
        
        Args:
            filenames: 要提交的文件名列表
            max_retries: 最大重试次数（默认 3 次）
            sync_codespace: 是否在 push 后同步 Codespace（默认 True）
                           如果为 False，需要调用者稍后在持有 submit_lock 时调用 sync
        
        Returns:
            是否成功 push
        """
        if not filenames:
            return True
            
        logger.info(f"| 📦 Batch pushing {len(filenames)} files...")
        
        # 先完成 git add 和 commit（这部分不需要重试）
        try:
            # Configure git user
            await self._run_git_command(['config', 'user.name', self.username], self.repo_path)
            await self._run_git_command(['config', 'user.email', f'{self.username}@users.noreply.github.com'], self.repo_path)
            
            # Git add all files
            for filename in filenames:
                await self._run_git_command(['add', filename], self.repo_path)
            
            # Check if there are changes to commit
            status_out = await self._run_git_command(['status', '--porcelain'], self.repo_path)
            
            if status_out.strip():
                # Git commit with batch message
                commit_msg = f'Batch add {len(filenames)} solutions: {", ".join(f for f in filenames[:3])}...'
                await self._run_git_command(['commit', '-m', commit_msg], self.repo_path)
            else:
                logger.info("| 🔍 No changes to commit (files unchanged)")
                return True
                
        except Exception as e:
            logger.error(f"| ❌ Git add/commit failed: {e}")
            return False
        
        # Git push 部分支持重试
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"| 🔄 Push attempt {attempt}/{max_retries}...")
                await self._run_git_command(['push'], self.repo_path)
                logger.info(f"| ✅ Successfully batch pushed {len(filenames)} files to GitHub")
                
                # Wait for GitHub to sync
                await asyncio.sleep(3)
                
                # Pull in Codespace (only if sync_codespace=True and we have submit_lock)
                # Note: _sync_codespace_repo() operates the browser, so it must be called
                # when the caller holds submit_lock to avoid conflicts with browser operations
                if sync_codespace:
                    await self._sync_codespace_repo()
                else:
                    # Mark that sync is needed before next evaluation
                    self._needs_sync = True
                    logger.info("| 📌 Marked Codespace sync as pending (will sync before next evaluation)")
                
                return True
                
            except Exception as e:
                logger.error(f"| ❌ Push attempt {attempt}/{max_retries} failed: {e}")
                if attempt < max_retries:
                    wait_time = attempt * 5  # 递增等待时间：5s, 10s
                    logger.info(f"| ⏳ Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"| ❌ All {max_retries} push attempts failed, giving up")
                    return False
        
        return False
    
    async def eval_single_file(self, filename: str) -> Dict[str, Any]:
        """
        在 Codespace 中打开文件并提交到 LeetCode 评测（不执行 push）
        
        Args:
            filename: 要评测的文件名
        
        Returns:
            评测结果字典
        """
        logger.info(f"| 🔍 Evaluating: {filename}")
        
        # 0. Check if Codespace sync is needed (from previous batch_push with sync_codespace=False)
        # This is safe here because the caller should hold submit_lock
        if self._needs_sync:
            logger.info("| 🔄 Performing pending Codespace sync before evaluation...")
            await self._sync_codespace_repo()
            self._needs_sync = False
        
        # 1. Open file in Codespace
        await self._open_editor_file(filename)
        await asyncio.sleep(2)
        
        # 2. Trigger LeetCode submission
        logger.info("| 🔍 Triggering LeetCode submission...")
        await self.page.keyboard.press("Meta+Shift+P")
        #await self.page.keyboard.press("Control+Shift+P")
        await asyncio.sleep(1)
        await self.page.keyboard.type("LeetCode: Submit to LeetCode")
        await asyncio.sleep(1)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(5)
        
        # 3. Wait for result
        result = await self._wait_for_result()
        
        # 4. Close editors (使用安全方法，失败也不影响结果)
        await self._safe_close_all_editors()
        
        return result
    
    # ==================== 原有的单个提交方法（保留兼容性） ====================
    
    async def submit_code(self, code_content: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """Submit code using git workflow: write -> commit -> push -> PULL in codespace -> open -> submit"""

        target_file = filename or "code.py"
        logger.info(f"| 🔍 Preparing evaluation for {target_file}...")
        
        # 1. Write code to file in repo (Local)
        file_path = os.path.join(self.repo_path, target_file)
        
        logger.info(f"| 🔍 Writing code to {file_path}...")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code_content)
        
        # 2. Git add, commit, and push (Local)
        logger.info("| 🔍 Committing and pushing to GitHub...")
        try:
            # Configure git user (required for commit)
            await self._run_git_command(['config', 'user.name', self.username], self.repo_path)
            await self._run_git_command(['config', 'user.email', f'{self.username}@users.noreply.github.com'], self.repo_path)
            
            # Git add
            await self._run_git_command(['add', target_file], self.repo_path)
            
            # Check if there are changes to commit
            status_out = await self._run_git_command(['status', '--porcelain'], self.repo_path)
            
            if status_out.strip():
                # Git commit
                await self._run_git_command(['commit', '-m', f'Add solution: {target_file}'], self.repo_path)
                
                # Git push
                await self._run_git_command(['push'], self.repo_path)
                logger.info("| 🔍 Successfully pushed to GitHub")
            else:
                logger.info("| 🔍 No changes to commit (file unchanged)")
        except Exception as e:
            logger.warning(f"| ⚠️ Git operation failed: {str(e)}")
            # Continue anyway, file might already be in repo or push might not be needed
        
        # 3. Wait a bit for GitHub to sync
        await asyncio.sleep(3)

        # 4. [修改] Pull latest code inside Codespace FIRST
        # 只有先 Pull 把文件拉下来，后面的 Open 才能找到文件
        await self._sync_codespace_repo()
        
        # 5. [修改] Open file in Codespace
        await self._open_editor_file(target_file)
        await asyncio.sleep(2)
        
        # 6. Trigger LeetCode submission
        logger.info("| 🔍 Triggering LeetCode submission...")
        await self.page.keyboard.press("Control+Shift+P")
        await asyncio.sleep(1)
        await self.page.keyboard.type("LeetCode: Submit to LeetCode")
        await asyncio.sleep(1)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(5)
        
        # 7. Wait for result
        result = await self._wait_for_result()
        
        # 8. Close all editors (使用安全方法)
        await self._safe_close_all_editors()

        return result

    async def _wait_for_result(self) -> Dict[str, Any]:
        """
        Wait for LeetCode result and parse detailed metrics from the UI text.
        Returns a dictionary containing raw status and parsed metrics.
        """
        # 初始化默认数据结构
        metrics = {
            "status": "Timeout",
            "total_cases": 0,
            "passed_cases": 0,
            "runtime": 0.0,            # ms
            "memory_usage": 0.0,       # MB
            "runtime_beats": 0.0,      # percentage
            "memory_beats": 0.0,       # percentage
        }
        
        end_time = time.time() + 60
        # 结果关键词
        keywords = ["Accepted", "Wrong Answer", "Time Limit Exceeded", "Runtime Error", "Memory Limit Exceeded", "Compile Error"]
        found = False
        
        logger.info("| 🔍 Waiting for detailed evaluation results...")
        
        while time.time() < end_time and not found:
            for frame in self.page.frames:
                try:
                    content_locator = frame.locator("body")
                    # 获取页面全部文本
                    page_text = await content_locator.inner_text()
                    
                    # 1. 优先检测状态关键词
                    detected_status = next((kw for kw in keywords if kw in page_text), None)
                    
                    if detected_status:
                        metrics["status"] = detected_status
                        metrics["details_text"] = page_text

                        # --- 通用解析：对 Accepted, Wrong Answer, TLE 等都尝试抓取用例数 ---
                        # 兼容 "68/68 cases passed" 和 "34/68 test cases passed"
                        cases_match = re.search(r"(\d+)\s*/\s*(\d+)\s*(?:test\s*)?cases\s*passed", page_text, re.IGNORECASE)
                        if cases_match:
                            metrics["passed_cases"] = int(cases_match.group(1))
                            metrics["total_cases"] = int(cases_match.group(2))
                        
                        # --- 特有解析：只有 Accepted 才会有运行时间和击败比例 ---
                        if detected_status == "Accepted":
                            # 解析运行时: 抓取 "27 ms" 或 "Runtime: 27 ms"
                            runtime_match = re.search(r"(\d+(?:\.\d+)?)\s*ms", page_text, re.IGNORECASE)
                            if runtime_match:
                                metrics["runtime"] = float(runtime_match.group(1))

                            # 解析内存: 抓取 "21.4 MB" 或 "Memory: 21.4 MB"
                            memory_match = re.search(r"(\d+(?:\.\d+)?)\s*MB", page_text, re.IGNORECASE)
                            if memory_match:
                                metrics["memory_usage"] = float(memory_match.group(1))
                                
                            # 解析击败率: 抓取 "beats 27.14 %"
                            beats_matches = re.findall(r"beats\s*([\d\.]+)\s*%", page_text, re.IGNORECASE)
                            if len(beats_matches) >= 1:
                                metrics["runtime_beats"] = float(beats_matches[0])
                            if len(beats_matches) >= 2:
                                metrics["memory_beats"] = float(beats_matches[1])

                        # --- 特有解析：Wrong Answer 有时会有输入/输出详情，如果有需要可以后续添加 ---
                        # 目前只要用例数抓对了，Result 里的 extra 就会正确显示

                        found = True
                        break
                except Exception:
                    continue
            
            if found: break
            await asyncio.sleep(1)
            
        logger.info(f"| 🔍 Result Parsed: {metrics['status']} (Passed: {metrics['passed_cases']}/{metrics['total_cases']})")
        return metrics
    async def close(self):
        """Cleanup browser and temp directory"""
        if self.context: 
            await self.context.close()
        if self.playwright: 
            await self.playwright.stop()

@BENCHMARK.register_module(force=True)
class LeetCodeBenchmark(Benchmark):
    """
    LeetCode Benchmark with Resume Capability and Batch Evaluation.
    
    批量评测模式：
    - 每 BATCH_SIZE (默认5) 个任务为一组
    - 批量写入文件并一次性 git push
    - 然后依次在 Codespace 中评测
    - 最后不满 BATCH_SIZE 的也算一组
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    name: str = Field(default="leetcode", description="The name of the benchmark")
    path: str = Field(default="datasets/leetcode", description="The path to the benchmark dataset")
    hf_repo_id: Optional[str] = Field(default=None, description="HuggingFace repo to download the dataset from when missing locally. None: LeetCode data is sourced live via the browser, not HF.")
    language: str = Field(default="python3", description="Programming language for LeetCode (e.g., python3, cpp, java)")
    batch_size: int = Field(default=5, description="Number of tasks to batch before pushing to GitHub")
    
    system_prompt: Optional[str] = Field(default=SYSTEM_PROMPT, description="The system prompt for the benchmark")
    
    _id_to_record_map: Dict[str, Dict] = PrivateAttr(default_factory=dict)
    _submitter: Any = PrivateAttr(default=None)
    _submitter_started: bool = PrivateAttr(default=False)
    
    _data_records: List[Dict] = PrivateAttr(default_factory=list)
    _index: int = PrivateAttr(default=0)
    _tasks: List[Task] = PrivateAttr(default_factory=list)
    
    # 批量队列相关
    _pending_queue: List[Task] = PrivateAttr(default_factory=list)  # 等待批量提交的任务队列
    _batch_pushed: bool = PrivateAttr(default=False)  # 当前批次是否已经 push
    _queue_lock: Any = PrivateAttr(default=None)  # 队列操作锁

    # Configuration for different languages
    LANGUAGE_CONFIG: ClassVar[Dict[str, Dict[str, str]]] = {
        "python3": {"ext": "py", "lang_tag": "python3", "comment": "#"},
        "python": {"ext": "py", "lang_tag": "python", "comment": "#"},
        "cpp": {"ext": "cpp", "lang_tag": "cpp", "comment": "//"},
        "c++": {"ext": "cpp", "lang_tag": "cpp", "comment": "//"},
        "java": {"ext": "java", "lang_tag": "java", "comment": "//"},
        "javascript": {"ext": "js", "lang_tag": "javascript", "comment": "//"},
        "typescript": {"ext": "ts", "lang_tag": "typescript", "comment": "//"},
        "c": {"ext": "c", "lang_tag": "c", "comment": "//"},
        "csharp": {"ext": "cs", "lang_tag": "csharp", "comment": "//"},
        "c#": {"ext": "cs", "lang_tag": "csharp", "comment": "//"},
        "go": {"ext": "go", "lang_tag": "golang", "comment": "//"},
        "ruby": {"ext": "rb", "lang_tag": "ruby", "comment": "#"},
        "swift": {"ext": "swift", "lang_tag": "swift", "comment": "//"},
        "rust": {"ext": "rs", "lang_tag": "rust", "comment": "//"},
        "scala": {"ext": "scala", "lang_tag": "scala", "comment": "//"},
        "kotlin": {"ext": "kt", "lang_tag": "kotlin", "comment": "//"},
        "php": {"ext": "php", "lang_tag": "php", "comment": "//"},
    }

    def __init__(self, base_dir: Optional[str] = None, start: Optional[int] = None, end: Optional[int] = None, **kwargs):
        super().__init__(base_dir=base_dir, start=start, end=end, **kwargs)
        self._submitter_started = False
        self._queue_lock = asyncio.Lock()  # 初始化队列锁

    async def initialize(self):
        """Initialize the benchmark by loading dataset, filtering finished tasks, and starting browser."""
        try:
            self._submitter = CodeSubmitter(headless=False, base_dir=self.base_dir)

            if self.hf_repo_id:
                from autogenesis.benchmark.utils import ensure_dataset
                import os
                ensure_dataset(os.path.basename(self.path), self.hf_repo_id)
            from autogenesis.data.leetcode import LeetCodeDataset
            # 1. 加载数据集
            dataset = LeetCodeDataset(
                path=self.path,
                split=self.split,
                name=self.subset if self.subset else None
            )
            self._id_to_record_map = {}
            
            # 获取原始数据记录
            if hasattr(dataset, 'data'):
                self._data_records = self._apply_slice(dataset.data.to_dict(orient="records"))
            else:
                self._data_records = []

            # ================= [新增逻辑：断点续跑过滤] =================
            
            # A. 使用 base_dir 定位结果文件路径（与 CodeSubmitter 保持一致）
            result_file = self._submitter.output_file

            # B. 读取已完成的任务 ID
            finished_ids = set()
            if os.path.exists(result_file):
                logger.info(f"| 🔄 Found existing result file: {result_file}, checking for finished tasks...")
                try:
                    with open(result_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line: continue
                            try:
                                record = json.loads(line)
                                if "task_id" in record:
                                    finished_ids.add(str(record["task_id"]))
                            except json.JSONDecodeError:
                                continue
                except Exception as e:
                    logger.warning(f"| ⚠️ Error reading result file for filtering: {e}")
            
            # C. 过滤 self._data_records
            original_count = len(self._data_records)
            self._data_records = [
                r for r in self._data_records 
                if str(r.get("id") or r.get("task_id", "0")) not in finished_ids
            ]
            filtered_count = len(self._data_records)
            
            if len(finished_ids) > 0:
                logger.info(f"| ⏭️ Skipped {original_count - filtered_count} tasks (already in results). Remaining: {filtered_count} tasks.")
            else:
                logger.info(f"| 🆕 No finished tasks found. Starting fresh with all {filtered_count} tasks.")

            # ================= [逻辑结束] =================

            # 2. 基于过滤后的数据建立索引映射
            for record in self._data_records:
                tid = str(record.get("id") or record.get("task_id", "0"))
                self._id_to_record_map[tid] = record
                
            logger.info(f"[{self.name}] Index built: {len(self._id_to_record_map)} records mapped.")
            
            # ================= [新增：提前初始化浏览器] =================
            # 在 benchmark 初始化阶段就启动浏览器，而不是等到第一次 eval
            # 这样多个并发任务可以共享同一个浏览器实例
            if not self._submitter_started and self._data_records:
                logger.info(f"| 🚀 Pre-initializing browser for concurrent evaluation...")
                try:
                    await self._submitter.initialize()
                    self._submitter_started = True
                    logger.info(f"| ✅ Browser initialized successfully, ready for concurrent tasks")
                except Exception as e:
                    logger.error(f"| ❌ Failed to initialize browser during benchmark init: {e}")
                    # 不抛出异常，允许后续尝试
            # ================= [逻辑结束] =================
            
        except ImportError:
            logger.error(f"[{self.name}] Failed to import LeetCodeDataset")
            
    async def reset(self) -> Optional[Task]:
        self._index = 0
        self._tasks = []
        return await self.step()

    async def step(self) -> Optional[Task]:
        if self._index >= len(self._data_records):
            return None
        
        record = self._data_records[self._index]
        self._index += 1
        
        task_id = str(record.get("id") or record.get("task_id", ""))
        task_name = record.get("name") or record.get("problem_name") or "Unknown"
        
        # templates are in record
        templates = record.get("code_template", {})
        # Map our language to potential keys in the template dict
        lang_key = self.language.lower()
        lang_config = self.LANGUAGE_CONFIG.get(lang_key, {})
        lang_tag = lang_config.get("lang_tag", lang_key)
        template = templates.get(lang_tag)
        
        input_text = f"""
TASK ID: {task_id}
Problem Name: {task_name}
Problem: {record.get("question") or record.get("prompt") or "Unknown"}
Template:
```{lang_key}
#
# @lc app=leetcode id={task_id} lang={lang_tag}
#
# [{task_id}] {task_name}
#
# @lc code=start
{template}
# @lc code=end
```
"""
        file_ext = self.LANGUAGE_CONFIG[self.language]["ext"]
        file_name = f"{task_id}.{inflection.parameterize(task_name)}"

        return Task(
            task_id=task_id,
            input=input_text,
            system_prompt=self.system_prompt,
            ground_truth=record.get("true_answer") or record.get("answer"),
            extra={
                "file_name": file_name,
                "file_ext": file_ext,
                "task_start_time": time.time()  # <--- 新增：记录任务开始时间
            }
        )

    def get_queue_size(self) -> int:
        """获取当前队列中的任务数量"""
        return len(self._pending_queue)
    
    async def save_error_result_directly(self, task: Task, prediction: str = "response_error") -> None:
        """
        直接保存错误结果，不入队列。用于推理失败的任务。
        
        Args:
            task: 失败的任务
            prediction: 错误类型（如 response_error, inference_error）
        """
        task.score = 0.0
        task.extra["submit_time"] = 0.0
        task.extra["spend_time"] = task.extra.get("inference_time", 0.0)
        self._tasks.append(task)
        
        task.extra["prediction"] = prediction
        task.extra["metrics"] = {"inference_time": task.extra.get("inference_time", 0.0), "submit_time": 0.0}
        task.extra["start_time"] = task.extra.get("inference_start_time", time.time())
        task.extra["end_time"] = time.time()
        task.extra["spend_time"] = task.extra.get("inference_time", 0.0)
        await self._submitter.save_result(task)
        logger.info(f"| 💾 [Task {task.task_id}] Error result saved directly (prediction: {prediction})")

    async def queue_for_eval(self, task: Task) -> bool:
        """
        将任务加入评测队列。当队列达到 batch_size 时自动触发批量评测。
        使用锁确保同一时间只有一个 task 入队列。
        
        Args:
            task: 已完成推理的任务
            
        Returns:
            是否触发了批量评测
        """
        async with self._queue_lock:
            self._pending_queue.append(task)
            queue_size = len(self._pending_queue)
            
            # 实时打印队列状态
            print(f"\r📊 Queue: {queue_size}/{self.batch_size} tasks", end="", flush=True)
            logger.info(f"| 📥 [Task {task.task_id}] Added to queue ({queue_size}/{self.batch_size})")
            
            # 当队列达到 batch_size 时，自动触发批量评测
            if queue_size >= self.batch_size:
                print()  # 换行
                await self.flush_eval_queue()
                return True
            return False
    
    async def flush_eval_queue(self) -> List[Task]:
        """
        刷新评测队列：批量 push 代码并依次评测。
        
        Returns:
            评测完成的任务列表
        """
        if not self._pending_queue:
            return []
        
        async with submit_lock:
            logger.info(f"| 🔒 Acquired lock for batch evaluation ({len(self._pending_queue)} tasks)")
            
            # 1. 确保 submitter 已初始化
            if not self._submitter_started:
                logger.info("| 🔍 Starting CodeSubmitter browser...")
                try:
                    await self._submitter.initialize()
                    self._submitter_started = True
                except Exception as e:
                    logger.error(f"| ❌ Failed to start submitter: {e}")
                    # 标记所有任务为失败，并保存结果（output_file 在 __init__ 中已设置）
                    for task in self._pending_queue:
                        task.score = 0.0
                        task.extra["submit_time"] = 0.0
                        task.extra["spend_time"] = task.extra.get("inference_time", 0.0)
                        self._tasks.append(task)
                        
                        # 保存错误结果
                        task.extra["prediction"] = "browser_init_error"
                        task.extra["metrics"] = {"error": str(e), "inference_time": task.extra.get("inference_time", 0.0), "submit_time": 0.0}
                        task.extra["start_time"] = task.extra.get("inference_start_time", time.time())
                        task.extra["end_time"] = time.time()
                        task.extra["spend_time"] = task.extra.get("inference_time", 0.0)
                        await self._submitter.save_result(task)
                    
                    result = self._pending_queue.copy()
                    self._pending_queue.clear()
                    return result
            
            # 2. 准备批量写入的文件
            batch_tasks = self._pending_queue.copy()
            self._pending_queue.clear()
            
            file_contents = []
            valid_tasks = []  # 有代码的任务
            
            for task in batch_tasks:
                code_content = task.result
                if not code_content:
                    # 无代码，直接标记失败
                    logger.error(f"| ❌ No code provided for Task {task.task_id}")
                    task.score = 0.0
                    task.extra["submit_time"] = 0.0
                    task.extra["spend_time"] = task.extra.get("inference_time", 0.0)
                    self._tasks.append(task)
                    
                    # 保存错误结果
                    task.extra["prediction"] = "response_error"
                    task.extra["metrics"] = {"inference_time": task.extra.get("inference_time", 0.0), "submit_time": 0.0}
                    task.extra["start_time"] = task.extra.get("inference_start_time", time.time())
                    task.extra["end_time"] = time.time()
                    task.extra["spend_time"] = task.extra.get("inference_time", 0.0)
                    await self._submitter.save_result(task)
                else:
                    file_name = f"{task.extra['file_name']}.{task.extra['file_ext']}"
                    file_contents.append({"filename": file_name, "code": code_content, "task": task})
                    valid_tasks.append(task)
            
            if not valid_tasks:
                logger.info("| ⚠️ No valid tasks in batch, skipping push")
                return batch_tasks
            
            # 3. 批量写入文件
            logger.info(f"| 📦 Batch writing {len(file_contents)} files...")
            filenames = [item["filename"] for item in file_contents]
            await self._submitter.batch_write_files([{"filename": item["filename"], "code": item["code"]} for item in file_contents])
            
            # 4. 批量 push（最多重试 3 次）
            logger.info(f"| 🚀 Batch pushing {len(filenames)} files to GitHub...")
            push_success = await self._submitter.batch_push(filenames, max_retries=3)
            
            if not push_success:
                # Push 失败，跳过这一批的评测，保存错误结果
                logger.error(f"| ❌ Batch push failed after all retries, skipping evaluation for {len(valid_tasks)} tasks")
                
                for item in file_contents:
                    task = item["task"]
                    task.score = 0.0
                    task.extra["submit_time"] = 0.0
                    task.extra["spend_time"] = task.extra.get("inference_time", 0.0)
                    self._tasks.append(task)
                    
                    task.extra["prediction"] = "push_failed"
                    task.extra["metrics"] = {"error": "Git push failed after 3 retries", "inference_time": task.extra.get("inference_time", 0.0), "submit_time": 0.0}
                    task.extra["start_time"] = task.extra.get("inference_start_time", time.time())
                    task.extra["end_time"] = time.time()
                    await self._submitter.save_result(task)
                    logger.info(f"| 💾 [Task {task.task_id}] Saved as push_failed")
                
                logger.info(f"| ⏭️ Skipped {len(valid_tasks)} tasks due to push failure")
                return batch_tasks
            
            # 5. 依次评测每个文件
            logger.info(f"| 🔍 Starting sequential evaluation of {len(valid_tasks)} tasks...")
            
            for item in file_contents:
                task = item["task"]
                file_name = item["filename"]
                task_id = task.task_id
                
                submit_start_time = time.time()
                task.extra["submit_start_time"] = submit_start_time
                
                try:
                    logger.info(f"| 📤 [Task {task_id}] Evaluating {file_name}...")
                    result_dict = await self._submitter.eval_single_file(file_name)
                    
                    # 计算时间
                    submit_end_time = time.time()
                    submit_time = submit_end_time - submit_start_time
                    inference_time = task.extra.get("inference_time", 0.0)
                    spend_time = inference_time + submit_time
                    
                    # 更新任务信息
                    task.extra["submit_time"] = submit_time
                    task.extra["spend_time"] = spend_time
                    task.extra["result"] = result_dict
                    task.score = self._parse_result_score(result_dict)
                    self._tasks.append(task)
                    
                    # 添加时间到 metrics
                    result_dict["inference_time"] = inference_time
                    result_dict["submit_time"] = submit_time
                    
                    task.extra["prediction"] = result_dict.get("status", "Unknown")
                    task.extra["metrics"] = result_dict
                    task.extra["start_time"] = task.extra.get("inference_start_time", submit_start_time)
                    task.extra["end_time"] = submit_end_time
                    await self._submitter.save_result(task)
                    
                    logger.info(f"| ✅ [Task {task_id}] Score: {task.score:.2f} (inference: {inference_time:.2f}s, submit: {submit_time:.2f}s)")
                    
                except Exception as e:
                    logger.error(f"| ❌ [Task {task_id}] Evaluation error: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    submit_end_time = time.time()
                    submit_time = submit_end_time - submit_start_time
                    inference_time = task.extra.get("inference_time", 0.0)
                    
                    task.extra["prediction"] = "system_error"
                    task.extra["metrics"] = {"error": str(e), "inference_time": inference_time, "submit_time": submit_time}
                    task.extra["start_time"] = task.extra.get("inference_start_time", submit_start_time)
                    task.extra["end_time"] = submit_end_time
                    task.extra["spend_time"] = inference_time + submit_time
                    await self._submitter.save_result(task)
                    
                    task.score = 0.0
                    self._tasks.append(task)
            
            logger.info(f"| 🔓 Batch evaluation complete, releasing lock")
            return batch_tasks

    async def eval(self, task: Task) -> Optional[Task]:
        """
        评测任务 - 现在使用批量队列模式。
        
        将任务加入队列，当队列满时自动批量评测。
        调用方需要在所有任务完成后调用 flush_eval_queue() 处理剩余任务。
        
        时间记录：
        - inference_time: 推理耗时（由调用方设置）
        - submit_time: 浏览器提交耗时
        - spend_time: 总处理时间 = inference_time + submit_time
        """
        await self.queue_for_eval(task)
        
        # 检查任务是否已被评测（队列满时会自动触发评测）
        if task in self._tasks:
            return task
        
        # 任务还在队列中，返回未评测状态
        return task
        
    async def stats(self) -> Optional[Stats]:
        total = len(self._data_records)
        attempted = len(self._tasks)
        correct = sum(1 for r in self._tasks if r.score and r.score >= 1.0)
        
        task_times = {r.task_id: r.time for r in self._tasks if r.time is not None}
        avg_time = sum(task_times.values()) / len(task_times) if task_times else 0.0
        
        return Stats(
            accuracy=correct / attempted if attempted > 0 else 0.0,
            total=total,
            correct=correct,
            wrong=attempted - correct,
            times=task_times,
            average_time=avg_time
        )

    def _parse_result_score(self, result: Dict[str, Any]) -> float:
        """
        Calculates score based on passed cases / total cases.
        """
        # 1. 直接从 result 获取我们在 browser 中解析好的整数
        # 使用 .get(key, 0) 防止键不存在报错
        passed = result.get("passed_cases", 0)
        total = result.get("total_cases", 0)

        # 2. 只要有总用例数，就按照比例计算分数 (涵盖了 Accepted, Wrong Answer, TLE 等)
        if total > 0:
            return float(passed) / float(total)

        # 3. 如果没有用例数据 (比如 total 为 0)
        status = result.get("status", "")
        
        # 如果是 Accepted 但没抓取到用例数，保底给 1.0
        if status == "Accepted":
            return 1.0
            
        # Compile Error 或其他无法解析的情况，给 0.0
        return 0.0
    
    async def cleanup(self):
        """Cleanup benchmark resources (close browser)."""
        if self._submitter_started and self._submitter:
            try:
                await self._submitter.close()
                self._submitter_started = False
                logger.info(f"| [{self.name}] 🚪 Browser closed successfully")
            except Exception as e:
                logger.warning(f"| [{self.name}] ⚠️ Error during browser cleanup: {e}")

    def __del__(self):
        if hasattr(self, '_submitter') and self._submitter_started:
            try:
                if hasattr(self._submitter, 'close'):
                    self._submitter.close()
            except Exception:
                pass