"""发送日报邮件（含播客附件）的参考脚本"""
import smtplib, ssl, os, re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

date = "YYYY-MM-DD"
sender = "only_for_aics_tic@163.com"
password = "FZbuF344Ef7zDKLr"
recipient = "yyc54321@126.com"  # review 收件人
mp3_path = f"/tmp/ai-daily-news-podcast-{date}.mp3"

with open(f"/tmp/ai-daily-news-html-{date}.html", "r", encoding="utf-8") as f:
    html_content = f.read()

msg = MIMEMultipart("mixed")
msg["Subject"] = f"每日AI热点新闻（试运营）— {date}"
msg["From"] = sender
msg["To"] = recipient

# text + html alternative
alt = MIMEMultipart("alternative")
plain = re.sub(r"<[^>]+>", "", html_content).strip()
alt.attach(MIMEText(plain, "plain", "utf-8"))
alt.attach(MIMEText(html_content, "html", "utf-8"))
msg.attach(alt)

# podcast attachment
with open(mp3_path, "rb") as f:
    mp3 = MIMEBase("audio", "mpeg")
    mp3.set_payload(f.read())
    encoders.encode_base64(mp3)
    mp3.add_header("Content-Disposition", f'attachment; filename="ai-daily-news-{date}.mp3"')
    msg.attach(mp3)

ctx = ssl.create_default_context()
with smtplib.SMTP_SSL("smtp.163.com", 465, context=ctx) as server:
    server.login(sender, password)
    server.sendmail(sender, [recipient], msg.as_string())
print("Sent!")
