import os
import random
import re
from datetime import datetime, timedelta
import feedparser
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'trade-secret-2026'

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DOC_STORAGE = {
    "HDMU10293847": {
        "CI": {"filename": "sample_ci.pdf", "original_name": "Commercial_Invoice_HDMU.pdf", "uploaded_at": "2026-09-14 14:20"},
        "PL": {"filename": "sample_pl.pdf", "original_name": "Packing_List_HDMU.pdf", "uploaded_at": "2026-09-14 14:21"}
    }
}

@app.route('/')
def index():
    return render_template('index.html')

# 분야별 뉴스 피드 API (쿼리 파라미터 category 지원)
NEWS_FEEDS = {
    "all": "https://news.google.com/rss/search?q=%EB%AC%B4%EC%97%AD+%EB%AC%BC%EB%A5%98+%ED%95%B4%EC%9A%B4&hl=ko&gl=KR&ceid=KR:ko",
    "shipping": "https://news.google.com/rss/search?q=%ED%95%B4%EC%9A%B4+%EC%BB%A8%ED%85%8C%EC%9D%B4%EB%84%88+%EC%9A%B4%EC%9E%84+SCFI&hl=ko&gl=KR&ceid=KR:ko",
    "customs": "https://news.google.com/rss/search?q=%EA%B4%80%EC%84%B8%EC%B2%AD+%EC%88%98%EC%B6%9C%EC%9E%85+%ED%86%B5%EA%B4%80&hl=ko&gl=KR&ceid=KR:ko",
    "air": "https://news.google.com/rss/search?q=%ED%95%AD%EA%B3%B5%ED%99%94%EB%AC%BC+%ED%95%AD%EA%B3%B5%EB%AC%BC%EB%A5%98&hl=ko&gl=KR&ceid=KR:ko"
}

@app.route('/api/news', methods=['GET'])
def get_live_news():
    category = request.args.get('category', 'all')
    feed_url = NEWS_FEEDS.get(category, NEWS_FEEDS['all'])
    
    try:
        feed = feedparser.parse(feed_url)
        articles = []
        for entry in feed.entries[:30]:  # 최대 30개까지 확보 후 프론트에서 더보기 지원
            raw_summary = getattr(entry, 'summary', '')
            clean_summary = re.sub('<[^<]+?>', '', raw_summary)
            if not clean_summary:
                clean_summary = "클릭하시면 해당 언론사의 기사 원문 전문으로 바로 이동합니다."

            title_parts = entry.title.rsplit(' - ', 1)
            title = title_parts[0]
            source = title_parts[1] if len(title_parts) > 1 else "무역경제"

            published = getattr(entry, 'published', '')
            if published:
                try:
                    pub_dt = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %Z")
                    pub_str = pub_dt.strftime("%Y.%m.%d %H:%M")
                except Exception:
                    pub_str = published[:16]
            else:
                pub_str = datetime.now().strftime("%Y.%m.%d")

            articles.append({
                "title": title,
                "source": source,
                "date": pub_str,
                "summary": clean_summary,
                "link": entry.link
            })
        return jsonify({"success": True, "articles": articles})
    except Exception as e:
        return jsonify({"success": False, "articles": [], "error": str(e)})

@app.route('/api/documents/<bl_no>', methods=['GET'])
def get_documents(bl_no):
    docs = DOC_STORAGE.get(bl_no, {})
    return jsonify({"success": True, "documents": docs})

@app.route('/api/documents/upload', methods=['POST'])
def upload_document():
    bl_no = request.form.get('bl_no')
    doc_type = request.form.get('doc_type')
    file = request.files.get('file')

    if not bl_no or not doc_type or not file:
        return jsonify({"success": False, "message": "필수 정보가 누락되었습니다."}), 400

    if bl_no in DOC_STORAGE and doc_type in DOC_STORAGE[bl_no]:
        old_filename = DOC_STORAGE[bl_no][doc_type].get('filename')
        if old_filename:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
            if os.path.exists(old_path):
                try: os.remove(old_path)
                except Exception as e: print(f"삭제 오류: {e}")

    orig_name = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_filename = f"{bl_no}_{doc_type}_{timestamp}_{orig_name}"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_filename)
    file.save(save_path)

    if bl_no not in DOC_STORAGE:
        DOC_STORAGE[bl_no] = {}

    DOC_STORAGE[bl_no][doc_type] = {
        "filename": saved_filename,
        "original_name": orig_name,
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    return jsonify({"success": True, "message": "서류가 성공적으로 업로드되었습니다.", "doc": DOC_STORAGE[bl_no][doc_type]})

@app.route('/api/documents/download/<bl_no>/<doc_type>', methods=['GET'])
def download_document(bl_no, doc_type):
    doc_info = DOC_STORAGE.get(bl_no, {}).get(doc_type)
    if not doc_info:
        return "파일을 찾을 수 없습니다.", 404
    return send_from_directory(app.config['UPLOAD_FOLDER'], doc_info['filename'], as_attachment=True, download_name=doc_info['original_name'])

@app.route('/api/documents/delete', methods=['POST'])
def delete_document():
    data = request.get_json() or {}
    bl_no = data.get('bl_no')
    doc_type = data.get('doc_type')

    if bl_no in DOC_STORAGE and doc_type in DOC_STORAGE[bl_no]:
        filename = DOC_STORAGE[bl_no][doc_type].get('filename')
        if filename:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except Exception as e: print(f"파일 삭제 오류: {e}")
        del DOC_STORAGE[bl_no][doc_type]
        return jsonify({"success": True, "message": "서류가 정상적으로 삭제되었습니다."})
    return jsonify({"success": False, "message": "삭제할 대상 서류가 없습니다."}), 404

@app.route('/api/shipments/sync-eta', methods=['POST'])
def sync_eta():
    data = request.get_json() or {}
    bl_no = data.get('bl_no')
    updated_date = (datetime.now() + timedelta(days=random.randint(3, 10))).strftime("%m/%d %H:00")
    return jsonify({
        "success": True,
        "bl_no": bl_no,
        "latest_eta": updated_date,
        "status_msg": "관세청 입항적하목록 동기화 완료"
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_msg = data.get('message', '').strip()
    return jsonify({"reply": f"'{user_msg}' 관련 알림: Cut-Off 24시간 전에 필수 서류를 꼭 업로드해주세요."})

if __name__ == '__main__':
    app.run(debug=True, port=5500)