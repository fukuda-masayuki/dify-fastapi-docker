from fastapi import FastAPI, Body,Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import requests
import configparser
import time
import hmac
import hashlib
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import json
from fastapi.responses import JSONResponse

app = FastAPI()
# ConfigParserオブジェクトを生成
config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")

# フロントエンドのURLをリストで指定
origins = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",  # 必要に応じて追加
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # or ["*"] で全許可
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

API_KEY = config['Dify']['key']  # 必要に応じて環境変数などを利用して安全に管理してください
SLACK_SIGNING_SECRET = config['Dify']['slack_key']
BOT_TOKEN = config['Dify']['bot_token']
BOT_USER_ID = config['Dify']['bot_member']
MENTION_TOKEN = f"<@{BOT_USER_ID}>"
client = WebClient(token=BOT_TOKEN)

# ──────────────────────────────────────────────
def verify_slack_request(req: Request, body: bytes):
    timestamp = req.headers.get("X-Slack-Request-Timestamp", "")
    sig_basestring = f"v0:{timestamp}:{body.decode()}".encode()
    my_sig = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), sig_basestring, hashlib.sha256
    ).hexdigest()
    slack_sig = req.headers.get("X-Slack-Signature", "")
    if abs(time.time() - int(timestamp)) > 60 * 5 or not hmac.compare_digest(my_sig, slack_sig):
        raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/slack/events")
async def slack_events(request: Request):
    raw = await request.body()

    # 1) 署名検証（既存関数）
    verify_slack_request(request, raw)

    # 2) JSON 変換
    try:
        payload = await request.json()
    except Exception:
        # application/x-www-form-urlencoded の可能性もある
        form = await request.form()
        payload = json.loads(form.get("payload", "{}"))

    print(payload)

    # 3) URL 検証 (challenge) は即返す
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    # app_mention 以外は無視
    event = payload.get("event", {})
    if event.get("type") != "app_mention":
        return {"ok": True}

    channel   = event["channel"]
    user_text = event.get("text", "")

    # --- AI で返信を生成（ここではダミー） ---
    reply = "tesの返事"
    # --- Slack へ投稿 ---
    try:
        client.chat_postMessage(channel=channel, text=reply, thread_ts=event.get("ts"))
    except Exception as e:
        print(f"Slack post error: {e}")

    # Slack は本文を見ないので simple OK を返す
    return {"ok": True}



@app.get("/slack-test")
def slack_test():
    """
    Slack からのリクエストを受け取るためのエンドポイント
    """
    
    test_data = {
        "inputs": {},
        "query": "iPhone 13 Pro Maxの仕様は何ですか？",
        "response_mode": "blocking",
        "conversation_id": "",
        "user": "abc-123",
        "files": []
    }

    # 同じアプリのPOSTエンドポイントへアクセス
    url = "http://localhost:8000/send-chat-message"
    try:
        response = requests.post(url, json=test_data)
        response.raise_for_status()  # 4xx/5xxで例外
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


@app.get("/debug-chat-message")
def debug_chat_message():
    """
    デバッグ用:
    GETリクエストで呼び出すと、自動でPOST /send-chat-messageに
    テスト用データを投げて結果を取得して返す
    """
    test_data = {
        "inputs": {},
        "query": "iPhone 13 Pro Maxの仕様は何ですか？",
        "response_mode": "blocking",
        "conversation_id": "",
        "user": "abc-123",
        "files": []
    }

    # 同じアプリのPOSTエンドポイントへアクセス
    url = "http://localhost:8000/send-chat-message"
    try:
        response = requests.post(url, json=test_data)
        response.raise_for_status()  # 4xx/5xxで例外
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


@app.post("/send-chat-message")
def send_chat_message(payload: dict = Body(...)):
    """
    クライアントから送られた JSON データをもとに、
    Dify にリクエストを送り、その結果を返すエンドポイント例
    """

    # クライアントから送られてきたデータ (payload) をそのまま利用するか、
    # あるいは加工して下のように使う
    # ここでは「Dify 側に送る JSON」を固定ではなくpayloadから生成するイメージ
    dify_data = {
        "inputs": payload.get("inputs", {}),
        "query": payload.get("query", ""),
        "response_mode": payload.get("response_mode", "streaming"),
        "conversation_id": payload.get("conversation_id", ""),
        "user": payload.get("user", ""),
        "files": payload.get("files", []),
        "response_mode": "blocking",
    }

    dify_headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # Dify 側のエンドポイント (本来は https://xxx.dify.ai/v1/chat-messages など)
    dify_url = "http://api:5001/v1/chat-messages"

    try:
        response = requests.post(dify_url, headers=dify_headers, json=dify_data)
        # ここで本当にJSON形式かどうかを確認する
        json_data = response.json()

        print(json_data.get("answer"))  # ここでエラーが出る場合は、JSON形式ではない

        return json_data.get("answer")
    except requests.exceptions.RequestException as e:
        # まずはステータスコードとレスポンスボディをログに出力
        print("Status Code:", response.status_code if 'response' in locals() else None)
        print("Response Text:", response.text if 'response' in locals() else None)
        return {"error": "Request to Dify failed", "detail": str(e)}
    except ValueError as e:
        # JSON デコードエラー等
        print("Status Code:", response.status_code if 'response' in locals() else None)
        print("Response Text:", response.text if 'response' in locals() else None)
        return {"error": "Failed to parse JSON", "detail": str(e)}


