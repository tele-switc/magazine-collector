import os
import re
from pathlib import Path
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import logging
import markdown2
import jinja2
import nltk
from sklearn.feature_extraction.text import TfidfVectorizer
from nltk.corpus import stopwords

# ==============================================================================
# 1. 配置区域
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

SOURCE_REPO_PATH = Path("source_repo")
MAGAZINES = {
    "economist": {"folder": "01_economist", "topic": "world_affairs"},
    "wired": {"folder": "05_wired", "topic": "technology"},
    "atlantic": {"folder": "04_atlantic", "topic": "world_affairs"}
}
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")
NON_ARTICLE_KEYWORDS = ['contents', 'index', 'editor', 'letter', 'subscription', 'classifieds', 'masthead', 'copyright', 'advertisement', 'the world this week', 'back issues']

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================
def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values(): (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def clean_article_text(text):
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text); text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'subscribe now|for more information|visit our website|follow us on', '', text, flags=re.IGNORECASE)
    return re.sub(r'\n\s*\n', '\n\n', text).strip()

def split_text_into_articles(text):
    ending_punctuations = ('.', '?', '!', '"', '”', '’'); articles = []
    for article_text in re.split(r'\n\s*\n\s*\n+', text):
        article_text = article_text.strip()
        if not article_text or not article_text.endswith(ending_punctuations): continue
        if sum(1 for keyword in NON_ARTICLE_KEYWORDS if keyword in article_text.lower()) > 1: continue
        if len(article_text.split()) < 250: continue
        articles.append(article_text)
    return articles

def generate_title_from_content(text_content, all_texts_corpus):
    try:
        stop_words = list(stopwords.words('english')); stop_words.extend(['would', 'could', 'said', 'also', 'like', 'get', 'one', 'two', 'told', 'mr', 'ms'])
        vectorizer = TfidfVectorizer(max_features=20, stop_words=stop_words, ngram_range=(1, 2), token_pattern=r'(?u)\b[a-zA-Z-]{3,}\b')
        vectorizer.fit(all_texts_corpus)
        response = vectorizer.transform([text_content]); feature_names = vectorizer.get_feature_names_out()
        scores = response.toarray().flatten(); top_keyword_indices = scores.argsort()[-7:][::-1]
        good_keywords = []
        for i in top_keyword_indices:
            keyword = feature_names[i]
            if not keyword.strip(): continue
            pos_tag_list = nltk.pos_tag(nltk.word_tokenize(keyword))
            if not pos_tag_list: continue
            pos_tag = pos_tag_list[0][1]
            if pos_tag.startswith('NN') or pos_tag.startswith('JJ'): good_keywords.append(keyword)
        if len(good_keywords) < 3: return nltk.sent_tokenize(text_content)[0]
        title = ' '.join(word.capitalize() for word in good_keywords[:4]); return title
    except Exception as e: logger.error(f"AI生成标题失败: {e}"); return nltk.sent_tokenize(text_content)[0]

def process_all_magazines():
    if not SOURCE_REPO_PATH.is_dir(): logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!"); return
    all_article_contents = []; magazine_contents = {}
    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        if not source_folder.is_dir(): continue
        
        # ↓↓↓↓↓↓【返璞归真】回归最成功的、最简单的文件查找逻辑 ↓↓↓↓↓↓
        for file_path in source_folder.glob('*.epub'):
            if magazine_name in file_path.name.lower():
        # ↑↑↑↑↑↑【返璞归真】回归最成功的、最简单的文件查找逻辑 ↑↑↑↑↑↑
                if file_path.stem not in magazine_contents:
                    logger.info(f"读取: {file_path.name}")
                    full_text = extract_text_from_epub(str(file_path))
                    if full_text:
                        magazine_contents[file_path.stem] = split_text_into_articles(full_text)
                        all_article_contents.extend(magazine_contents.get(file_path.stem, []))
    
    processed_fingerprints = set()
    for stem, articles_in_magazine in magazine_contents.items():
        magazine_name, topic = next(((m, info['topic']) for m, info in MAGAZINES.items() if m in stem), ("unknown", "unknown"))
        for i, article_content in enumerate(articles_in_magazine):
            fingerprint = article_content.strip()[:60]
            if fingerprint in processed_fingerprints: continue
            processed_fingerprints.add(fingerprint)
            cleaned_content = clean_article_text(article_content)
            if len(cleaned_content.split()) < 200: continue
            title = generate_title_from_content(cleaned_content, all_article_contents)
            author_match = re.search(r'By\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', cleaned_content)
            author = author_match.group(1) if author_match else "N/A"
            output_path = ARTICLES_DIR / topic / f"{stem}_art_{i+1}.md"
            save_article(output_path, cleaned_content, title, author)

def extract_text_from_epub(epub_path):
    try: book = epub.read_epub(epub_path); return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e: logger.error(f"提取EPUB失败 {epub_path}: {e}"); return ""

def save_article(output_path, text_content, title, author):
    word_count = len(text_content.split()); reading_time = f"~{round(word_count / 200)} min"
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nauthor: {author}\nwords: {word_count}\nreading_time: {reading_time}\n---\n\n{text_content}")
    logger.info(f"已保存: {output_path.name}")

def generate_website():
    """【最终美学版】带有粒子特效和流光卡片"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        @property --angle { syntax: '<angle>'; initial-value: 0deg; inherits: false; }
        :root { --bg-color: #0d1117; --card-color: #161b22; --text-color: #c9d1d9; --secondary-text: #8b949e; 
                --border-color: rgba(255, 255, 255, 0.1); --glow-color: rgba(0, 191, 255, 0.6); }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 4rem 2rem; overflow-x: hidden; }
        #particles-js { position: fixed; width: 100%; height: 100%; top: 0; left: 0; z-index: -1; }
        .container { max-width: 1320px; margin: 0 auto; } .header { text-align: center; margin-bottom: 5rem; }
        .header h1 { font-size: 5rem; font-weight: 700; color: #fff; margin: 0; letter-spacing: -2px; }
        .grid { display: grid; gap: 2.5rem; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
        .card { background: var(--card-color); border: 1px solid var(--border-color); border-radius: 16px;
                transition: transform 0.3s ease; display: flex; flex-direction: column; position: relative; padding: 1px; }
        .card:hover { transform: translateY(-8px); }
        .card::before, .card::after { content: ''; position: absolute; inset: -1px; z-index: -1; background: conic-gradient(from var(--angle), transparent 50%, var(--glow-color), transparent);
                                     border-radius: inherit; animation: rotate 6s linear infinite; }
        .card::after { filter: blur(20px); }
        .card-inner { background: var(--card-color); border-radius: 15px; padding: 2rem; height: 100%; display: flex; flex-direction: column; }
        .card-title { font-size: 1.5rem; line-height: 1.4; color: #fff; margin: 0 0 1rem 0; }
        .card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: auto; padding-top: 1.5rem; border-top: 1px solid var(--border-color); }
        @keyframes rotate { to { --angle: 360deg; } }
    </style></head>
    <body><div id="particles-js"></div><div class="container">
        <div class="header"><h1>AI Curated Journals</h1></div><div class="grid">
        {% for article in articles %}
            <div class="card"><div class="card-inner">
                <h5 class="card-title">{{ article.title }}</h5>
                <div class="card-footer"><span style="color:#8e8e8e;">By {{ article.author }}</span><a href="{{ article.url }}" style="color:#fff;text-decoration:none;">Read →</a></div>
            </div></div>
        {% endfor %}
        </div></div>
    <script src="https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"></script>
    <script>
        particlesJS('particles-js', {"particles":{"number":{"value":50,"density":{"enable":true,"value_area":800}},"color":{"value":"#ffffff"},"shape":{"type":"circle"},"opacity":{"value":0.1,"random":true},"size":{"value":2,"random":true},"line_linked":{"enable":false},"move":{"enable":true,"speed":1,"direction":"none","random":true,"straight":false,"out_mode":"out"}},"interactivity":{}});
    </script></body></html>
    """
    article_html_template = """... (文章页模板保持不变) ..."""
    # ... (后面的网站生成逻辑保持不变)
