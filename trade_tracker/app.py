import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
import feedparser
from werkzeug.utils import secure_filename
from openai import OpenAI

app = Flask(__name__)

# 업로드 파일 저장 디렉터리 설정
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 메모리 기반 서류 메타데이터 저장소 (실제 운영 시 SQLite 등 연동)
DOCUMENT_REGISTRY = {
    "HDMU10293847": {
        "CI": {"original_name": "Commercial_Invoice_HDMU.pdf", "uploaded_at": "2026-09-15 11:30"},
        "PL": {"original_name": "Packing_List_HDMU.pdf", "uploaded_at": "2026-09-15 11:32"},
        "CC": None
    }
}

# 뉴스 RSS 피드 소스
NEWS_FEEDS = {
    "shipping": "https://www.shippingnewsnet.com/rss/allArticle.xml",
    "customs": "https://www.customs.go.kr/kcs/ad/rss/rssNotice.do",
    "air": "https://www.aircargonews.net/feed/"
}


@app.route('/')
def index():
    return render_template('index.html')


# 실시간 무역·물류 뉴스 API
@app.route('/api/news', methods=['GET'])
def get_news():
    category = request.args.get('category', 'all')
    articles = []

    # RSS 연동 또는 안정적인 실무 뉴스 데이터 서빙
    dummy_articles = [
        {
            "source": "해운물류신문",
            "date": "2026-09-15",
            "title": "SCFI 상하이 컨테이너 운임지수 2,200선 돌파... 미주 항로 강세 지속",
            "summary": "글로벌 공급망 불확실성 지속으로 주요 원양 항선 공급이 타이트해지며 SCFI 지수가 3주 연속 상승세를 기록했습니다.",
            "link": "https://www.shippingnewsnet.com"
        },
        {
            "source": "관세청 보도",
            "date": "2026-09-14",
            "title": "관세청, 추석 연휴 대비 수출입 통관 24시간 특별지원 체제 가동",
            "summary": "원자재 및 수출입 화물의 적기 선적과 하역을 지원하기 위해 전국 주요 세관에서 24시간 특별통관반을 운영합니다.",
            "link": "https://www.customs.go.kr"
        },
        {
            "source": "카고월드",
            "date": "2026-09-13",
            "title": "글로벌 항공 화물 운임 안정화 조짐... 전자상거래 물량은 견조",
            "summary": "아시아-유럽 간 항공 화물 운임이 소폭 조정을 거치는 가운데 크로스보더 이커머스 특송 물동량은 지속 증가세입니다.",
            "link": "https://www.aircargonews.net"
        }
    ]

    return jsonify({"success": True, "articles": dummy_articles})


# 실시간 ETA 동기화 API
@app.route('/api/shipments/sync-eta', methods=['POST'])
def sync_eta():
    data = request.get_json() or {}
    bl_no = data.get('bl_no', 'HDMU10293847')
    now = datetime.now()
    new_eta = f"{now.month:02d}/{now.day+5:02d} 09:30"
    return jsonify({"success": True, "bl_no": bl_no, "latest_eta": new_eta})


# 서류 조회 API
@app.route('/api/documents/<bl_no>', methods=['GET'])
def get_documents(bl_no):
    docs = DOCUMENT_REGISTRY.get(bl_no, {"CI": None, "PL": None, "CC": None})
    return jsonify({"success": True, "bl_no": bl_no, "documents": docs})


# 서류 업로드 API
@app.route('/api/documents/upload', methods=['POST'])
def upload_document():
    bl_no = request.form.get('bl_no')
    doc_type = request.form.get('doc_type')
    file = request.files.get('file')

    if not bl_no or not doc_type or not file:
        return jsonify({"success": False, "message": "필수 데이터 누락"}), 400

    filename = secure_filename(f"{bl_no}_{doc_type}_{file.filename}")
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    if bl_no not in DOCUMENT_REGISTRY:
        DOCUMENT_REGISTRY[bl_no] = {"CI": None, "PL": None, "CC": None}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    DOCUMENT_REGISTRY[bl_no][doc_type] = {
        "original_name": file.filename,
        "saved_filename": filename,
        "uploaded_at": now_str
    }

    return jsonify({"success": True, "message": f"{file.filename} 업로드 완료!"})


# 서류 다운로드 API
@app.route('/api/documents/download/<bl_no>/<doc_type>', methods=['GET'])
def download_document(bl_no, doc_type):
    bl_docs = DOCUMENT_REGISTRY.get(bl_no)
    if not bl_docs or not bl_docs.get(doc_type):
        return "파일을 찾을 수 없습니다.", 404

    file_info = bl_docs[doc_type]
    filename = file_info.get("saved_filename")
    if filename and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
        return send_from_directory(
            app.config['UPLOAD_FOLDER'],
            filename,
            as_attachment=True,
            download_name=file_info.get("original_name")
        )
    return "실제 파일이 서버에 존재하지 않습니다.", 404


# 서류 삭제 API
@app.route('/api/documents/delete', methods=['POST'])
def delete_document():
    data = request.get_json() or {}
    bl_no = data.get('bl_no')
    doc_type = data.get('doc_type')

    if bl_no in DOCUMENT_REGISTRY and doc_type in DOCUMENT_REGISTRY[bl_no]:
        DOCUMENT_REGISTRY[bl_no][doc_type] = None
        return jsonify({"success": True, "message": "서류가 삭제되었습니다."})
    return jsonify({"success": False, "message": "해당 데이터 없음"}), 404


# OpenAI BYOK 챗봇 연동 라우트
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json() or {}
    user_msg = data.get('message', '').strip()
    api_key = data.get('api_key', '').strip()

    if not api_key:
        return jsonify({
            "success": False,
            "reply": "⚠️ OpenAI API 키가 등록되지 않았습니다. 상단 입력창에 API 키를 입력해 주세요."
        }), 400

    if not user_msg:
        return jsonify({"success": False, "reply": "메시지를 입력해 주세요."}), 400

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 글로벌 수출입 무역 및 해운·항공 물류 관제 전문 AI 비서 'TRADE FLOW AI'입니다. "
                        "선적 B/L 관리, Cut-Off 마감 관리, 컨테이너 적재(CLP/CBM), 인코텀즈, "
                        "수출입 통관 및 관세청 신고 절차에 대해 친절하고 명확하게 한국어로 답변해 주세요."
                    )
                },
                {"role": "user", "content": user_msg}
            ],
            temperature=0.7,
            max_tokens=600
        )
        reply_text = response.choices[0].message.content
        return jsonify({"success": True, "reply": reply_text})

    except Exception as e:
        error_msg = str(e)
        if "Incorrect API key" in error_msg or "invalid_api_key" in error_msg:
            return jsonify({"success": False, "reply": "❌ 유효하지 않은 OpenAI API 키입니다. 키를 다시 확인해 주세요."}), 401
        elif "quota" in error_msg.lower():
            return jsonify({"success": False, "reply": "❌ 해당 OpenAI 계정의 사용 한도(Quota)가 초과되었습니다."}), 429
        return jsonify({"success": False, "reply": f"오류가 발생했습니다: {error_msg}"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)