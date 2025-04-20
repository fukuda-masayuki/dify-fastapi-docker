from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()


# フロントエンドのURLをリストで指定
origins = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",  # 必要に応じて追加
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # or ["*"] で全許可
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

API_KEY = "app-A6hVkMjZ6oLQcKuOjvP09Y6N"  # 必要に応じて環境変数などを利用して安全に管理してください


@app.get("/slack-test")
def slack_test():
    """
    Slack からのリクエストを受け取るためのエンドポイント
    """
    return {"message": "Slack test endpoint"}

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


