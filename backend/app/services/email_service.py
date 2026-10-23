"""邮件验证码发送服务（QQ邮箱 SMTP）"""
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from ..config import settings


def send_verification_email(to_email: str, code: str) -> bool:
    """发送验证码邮件到指定邮箱"""
    if not settings.SMTP_EMAIL or not settings.SMTP_AUTH_CODE:
        raise RuntimeError("未配置 SMTP_EMAIL 或 SMTP_AUTH_CODE，请在 .env 中设置")

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = "墨韵 - 验证码"

    html = f"""
    <div style="max-width:400px;margin:0 auto;font-family:sans-serif;">
      <h2 style="color:#e8718b;text-align:center;">墨韵</h2>
      <p>你的验证码是：</p>
      <div style="font-size:32px;font-weight:bold;color:#e8718b;letter-spacing:8px;text-align:center;padding:20px 0;">
        {code}
      </div>
      <p style="color:#999;font-size:12px;text-align:center;">验证码5分钟内有效，请勿泄露给他人</p>
    </div>
    """
    msg.attach(MIMEText(html, "html", "utf-8"))

    server = None
    try:
        server = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=10)
        server.ehlo()

        # QQ SMTP 对带初始响应的 AUTH LOGIN 兼容性不稳定，按传统的
        # username/password 两步方式认证，并保留服务端的明确错误码。
        auth_code, auth_message = server.docmd("AUTH", "LOGIN")
        if auth_code != 334:
            raise smtplib.SMTPAuthenticationError(auth_code, auth_message)
        user_code, user_message = server.docmd(
            base64.b64encode(settings.SMTP_EMAIL.encode("utf-8")).decode("ascii")
        )
        if user_code != 334:
            raise smtplib.SMTPAuthenticationError(user_code, user_message)
        login_code, login_message = server.docmd(
            base64.b64encode(settings.SMTP_AUTH_CODE.encode("utf-8")).decode("ascii")
        )
        if login_code != 235:
            raise smtplib.SMTPAuthenticationError(login_code, login_message)

        server.sendmail(settings.SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except smtplib.SMTPAuthenticationError as e:
        detail = e.smtp_error.decode("utf-8", errors="replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        raise RuntimeError(
            "QQ 邮箱 SMTP 登录失败。请确认 SMTP 服务已开启，并重新生成授权码"
            f"（不是 QQ 登录密码）。服务器返回：{e.smtp_code} {detail}"
        )
    except Exception as e:
        raise RuntimeError(f"邮件发送失败：{e}")
    finally:
        if server is not None:
            try:
                server.close()
            except Exception:
                pass
