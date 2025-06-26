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
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def clean_article_text(text):
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text); text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'subscribe now|for more information|visit our website|follow us on', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Page\s+\d+', '', text); return re.sub(r'\n\s*\n', '\n\n', text).strip()

def split_text_into_articles(text):
    ending_punctuations = ('.', '?', '!', '"', '”', '’'); potential_articles = re.split(r'\n\s*\n\s*\n+', text)
    articles = []
    for article_text in potential_articles:
        article_text = article_text.strip()
        if not article_text or not article_text.endswith(ending_punctuations): continue
        lower_text = article_text.lower()
        if sum(1 for keyword in NON_ARTICLE_KEYWORDS if keyword in lower_text) > 1: continue
        if len(article_text.split()) < 250: continue
        articles.append(article_text)
    return articles

def generate_title_from_content(text_content, all_texts_corpus):
    try:
        stop_words = list(stopwords.words('english'))
        stop_words.extend(['would', 'could', 'said', 'also', 'like', 'get', 'one', 'two', 'told', 'mr', 'ms'])
        vectorizer = TfidfVectorizer(max_features=20, stop_words=stop_words, ngram_range=(1, 2), token_pattern=r'(?u)\b[a-zA-Z-]{3,}\b')
        vectorizer.fit(all_texts_corpus)
        response = vectorizer.transform([text_content])
        feature_names = vectorizer.get_feature_names_out()
        scores = response.toarray().flatten()
        top_keyword_indices = scores.argsort()[-7:][::-1]
        good_keywords = []
        for i in top_keyword_indices:
            keyword = feature_names[i]
            pos_tag = nltk.pos_tag([keyword.split()[0]])[0][1]
            if pos_tag.startswith('NN') or pos_tag.startswith('JJ'):
                good_keywords.append(keyword)
        if len(good_keywords) < 3: return nltk.sent_tokenize(text_content)[0]
        title = ' '.join(word.capitalize() for word in good_keywords[:4])
        return title
    except Exception as e:
        logger.error(f"AI生成标题失败: {e}"); return nltk.sent_tokenize(text_content)[0]

def process_all_magazines():
    if not SOURCE_REPO_PATH.is_dir(): logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!"); return
    try:
        nltk.data.find('corpora/stopwords'); nltk.data.find('tokenizers/punkt'); nltk.data.find('taggers/averaged_perceptron_tagger')
    except LookupError:
        nltk.download('stopwords'); nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')
    all_article_contents = []; magazine_contents = {}
    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        if not source_folder.is_dir(): continue
        for file_path in source_folder.rglob('*.epub'):
            if magazine_name in file_path.name.lower():
                if file_path.stem not in magazine_contents:
                    logger.info(f"读取新杂志: {file_path.name}")
                    full_text = extract_text_from_epub(str(file_path))
                    if full_text: magazine_contents[file_path.stem] = split_text_into_articles(full_text)
                    all_article_contents.extend(magazine_contents.get(file_path.stem, []))
    processed_fingerprints = set()
    for stem, articles_in_magazine in magazine_contents.items():
        magazine_name, topic = "unknown", "unknown"
        for m, info in MAGAZINES.items():
            if m in stem: magazine_name, topic = m, info['topic']
        for i, article_content in enumerate(articles_in_magazine):
            fingerprint = article_content.strip()[:60]
            if fingerprint in processed_fingerprints: continue
            processed_fingerprints.add(fingerprint)
            cleaned_content = clean_article_text(article_content)
            if len(cleaned_content.split()) < 200: continue
            title = generate_title_from_content(cleaned_content, all_article_contents)
            author_match = re.search(r'By\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', cleaned_content)
            author = author_match.group(1) if author_match else "N/A"
            article_md_filename = f"{stem}_art_{i+1}.md"
            output_path = ARTICLES_DIR / topic / article_md_filename
            save_article(output_path, cleaned_content, title, author)

def extract_text_from_epub(epub_path):
    try:
        book = epub.read_epub(epub_path); return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e: logger.error(f"提取EPUB失败 {epub_path}: {e}"); return ""

def save_article(output_path, text_content, title, author):
    word_count = len(text_content.split()); reading_time = round(word_count / 200) 
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nauthor: {author}\nwords: {word_count}\nreading_time: {reading_time} min\n---\n\n{text_content}")
    logger.info(f"已保存: {output_path.name}")

def generate_website():
    """【最终艺术品版】"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    # 注入 particles.js 库
    particles_js_url = "https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"
    # 主页模板
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --accent-color: #33a0ff; --bg-color: #0d1117; --card-color: #161b22; --text-color: #c9d1d9; 
                --secondary-text: #8b949e; --border-color: rgba(139, 148, 158, 0.2); }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 4rem 2rem; }
        #particles-js { position: fixed; width: 100%; height: 100%; top: 0; left: 0; z-index: 0; }
        .content-wrapper { position: relative; z-index: 1; }
        .container { max-width: 1320px; margin: 0 auto; }
        .header h1 { font-size: 5rem; text-align: center; margin-bottom: 4rem; color: #fff; }
        .grid { display: grid; gap: 2.5rem; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
        .card { background: var(--card-color); border: 1px solid var(--border-color); border-radius: 16px;
                transition: all 0.3s ease; display: flex; flex-direction: column; }
        .card:hover { transform: translateY(-8px); box-shadow: 0 0 30px rgba(51, 160, 255, 0.2); border-color: var(--accent-color); }
        .card-content { padding: 2rem; flex-grow: 1; } .card-title { font-size: 1.5rem; margin: 0 0 1rem 0; color: #fff; }
        .card-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 1.5rem; margin-top: auto; border-top: 1px solid var(--border-color); }
    </style></head>
    <body><div id="particles-js"></div><div class="content-wrapper"><div class="container">
        <div class="header"><h1>AI Curated Journals</h1></div><div class="grid">
        {% for article in articles %}
            <div class="card"><div class="card-content">
                <h5 class="card-title">{{ article.title }}</h5>
                <div class="card-footer"><span>By {{ article.author }}</span><a href="{{ article.url }}" style="color:var(--accent-color);">Read →</a></div>
            </div></div>
        {% endfor %}
        </div></div></div>
    <script src="{{ particles_js_url }}"></script>
    <script>
        particlesJS('particles-js', { "particles": { "number": { "value": 60, "density": { "enable": true, "value_area": 800 } },
            "color": { "value": "#ffffff" }, "shape": { "type": "circle" }, "opacity": { "value": 0.3, "random": true },
            "size": { "value": 2, "random": true }, "line_linked": { "enable": true, "distance": 150, "color": "#8b949e", "opacity": 0.2, "width": 1 },
            "move": { "enable": true, "speed": 1, "direction": "none", "random": true, "straight": false, "out_mode": "out" } },
            "interactivity": { "detect_on": "canvas", "events": { "onhover": { "enable": true, "mode": "grab" }, "onclick": { "enable": true, "mode": "push" } } }
        });
    </script></body></html>
    """
    # ... (后面的代码不变)
