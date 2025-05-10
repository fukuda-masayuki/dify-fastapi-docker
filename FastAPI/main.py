from fastapi import FastAPI, Body,Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import requests
import configparser
import time
import hmac
import hashlib
import logging

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
SLACK_SIGNING_SECRET = config['Dify']['key']

def verify_slack_signature(
    timestamp: str,
    signature: str,
    body: bytes,
    signing_secret: str,
    tolerance_sec: int = 60 * 5,  # 5 分以内のみ許可
) -> bool:
    """
    X‑Slack‑Request‑Timestamp と X‑Slack‑Signature を使って
    リクエストが正当かどうかを検証する。
    """
    # リプレイ攻撃対策：古いリクエストは拒否
    if abs(time.time() - int(timestamp)) > tolerance_sec:
        return False

    basestring = f"v0:{timestamp}:{body.decode()}".encode()
    my_signature = (
        "v0="
        + hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    )

    # 署名を安全に比較
    return hmac.compare_digest(my_signature, signature)

@app.post("/slack/events")
async def slack_events(
    request: Request,
    x_slack_signature: str = Header(..., alias="X-Slack-Signature"),
    x_slack_request_timestamp: str = Header(..., alias="X-Slack-Request-Timestamp"),
):
    """
    Slack Events API 受信エンドポイント

    1. 署名を検証して正当性を確認
    2. url_verification の `challenge` に応答
    3. 必要なイベントを処理
    """
    if not SLACK_SIGNING_SECRET:
        logging.error("環境変数 SLACK_SIGNING_SECRET が未設定です。")
        raise HTTPException(status_code=500, detail="Signing secret not configured")

    body = await request.body()

    # 署名チェック
    if not verify_slack_signature(
        x_slack_request_timestamp,
        x_slack_signature,
        body,
        SLACK_SIGNING_SECRET,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = await request.json()

    # --- ② URL Verification フロー ---
    if payload.get("type") == "url_verification":
        return JSONResponse({"challenge": payload["challenge"]})

    # --- ③ イベント処理例（必要に応じて実装） ---
    event = payload.get("event", {})
    if event.get("type") == "app_mention":
        user = event.get("user")
        text = event.get("text", "")
        logging.info(f"メンション: {user=} {text=}")
        # ここで Slack Web API を呼び出して返信しても良い

    # Slack には JSON で OK を返す
    return JSONResponse({"ok": True})


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


