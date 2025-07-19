import os
import re
from pathlib import Path
import ebooklib
from ebooklib import epub
import mobi
from bs4 import BeautifulSoup
import logging
import markdown2
import jinja2
import nltk
from sklearn.feature_extraction.text import TfidfVectorizer
from nltk.corpus import stopwords

# ==============================================================================
# 1. 配置和初始化
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

SOURCE_REPO_PATH = Path("source_repo")
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")
NON_ARTICLE_KEYWORDS = ['contents', 'index', 'editor', 'letter', 'subscription', 'classifieds', 'masthead', 'copyright', 'advertisement', 'the world this week', 'back issues']

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================

def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)

def extract_text(file_path):
    if file_path.suffix == '.epub':
        try:
            book = epub.read_epub(str(file_path))
            return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        except Exception as e: logger.error(f"提取EPUB失败 {file_path.name}: {e}")
    elif file_path.suffix == '.mobi':
        try:
            book = mobi.Mobi(str(file_path)); content = "".join(record.text for record in book)
            return BeautifulSoup(content, 'html.parser').get_text()
        except Exception as e: logger.error(f"提取MOBI失败 {file_path.name}: {e}")
    return ""

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

def discover_and_process_files():
    if not SOURCE_REPO_PATH.is_dir(): logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!"); return
    
    all_article_contents = []; magazine_contents = {}
    for source_folder in SOURCE_REPO_PATH.iterdir():
        if source_folder.is_dir() and not source_folder.name.startswith('.'):
            for file_path in list(source_folder.glob('*.epub')) + list(source_folder.glob('*.mobi')):
                if file_path.stem not in magazine_contents:
                    logger.info(f"读取: {file_path.name}")
                    full_text = extract_text(file_path)
                    if full_text:
                        magazine_contents[file_path.stem] = split_text_into_articles(full_text)
                        all_article_contents.extend(magazine_contents.get(file_path.stem, []))
    
    processed_fingerprints = set()
    for stem, articles_in_magazine in magazine_contents.items():
        journal_name = re.match(r'([a-zA-Z\s]+)', stem.replace('_', ' ')).group(1).strip().title()
        topic_dir = ARTICLES_DIR / journal_name; topic_dir.mkdir(exist_ok=True)
        for i, article_content in enumerate(articles_in_magazine):
            fingerprint = article_content.strip()[:60]
            if fingerprint in processed_fingerprints: continue
            processed_fingerprints.add(fingerprint)
            cleaned_content = clean_article_text(article_content)
            if len(cleaned_content.split()) < 200: continue
            title = generate_title_from_content(cleaned_content, all_article_contents)
            author_match = re.search(r'By\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', cleaned_content)
            author = author_match.group(1) if author_match else "N/A"
            output_path = topic_dir / f"{stem}_art_{i+1}.md"
            save_article(output_path, cleaned_content, title, author, journal_name)

def save_article(output_path, text_content, title, author, journal):
    word_count = len(text_content.split()); reading_time = f"~{round(word_count / 200)} min"
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nauthor: {author}\njournal: {journal}\nreading_time: {reading_time}\n---\n\n{text_content}")
    logger.info(f"已保存: {output_path.name}")

def generate_website():
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --accent-color: #00ffff; --bg-color: #000000; --card-color: rgba(22, 27, 34, 0.5); --text-color: #e0e0e0; 
                --secondary-text: #8b949e; --border-color: rgba(0, 255, 255, 0.2); }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 4rem 2rem; }
        #particles-js { position: fixed; width: 100%; height: 100%; top: 0; left: 0; z-index: -1; }
        .container { max-width: 1400px; margin: 0 auto; position: relative; z-index: 1; }
        .header h1 { font-size: 5rem; text-align: center; margin-bottom: 4rem; color: #fff; text-shadow: 0 0 20px var(--accent-color); }
        .grid { display: grid; gap: 2.5rem; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); }
        .card { background: var(--card-color); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
                border: 1px solid var(--border-color); border-radius: 16px;
                transition: all 0.3s ease; display: flex; flex-direction: column; }
        .card:hover { transform: translateY(-8px); box-shadow: 0 0 30px rgba(0, 255, 255, 0.3); }
        .card-content { padding: 2rem; flex-grow: 1; display:flex; flex-direction:column; }
        .card-title { font-size: 1.5rem; font-weight: 500; margin: 0 0 auto 0; color: #fff; line-height: 1.4; }
        .card-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 1.5rem; border-top: 1px solid var(--border-color); }
    </style></head>
    <body><div id="particles-js"></div><div class="container">
        <div class="header"><h1>AI Curated Journals</h1></div><div class="grid">
        {% for article in articles %}
            <div class="card">
                <div class="card-content">
                    <h5 class="card-title">{{ article.title }}</h5>
                    <div class="card-footer">
                        <span style="color:var(--secondary-text);">{{ article.journal }}</span>
                        <a href="{{ article.url }}" style="color:var(--accent-color);text-decoration:none;font-weight:500;">Read →</a>
                    </div>
                </div>
            </div>
        {% endfor %}
        </div>
        {% if not articles %}<div style="text-align:center;padding:4rem;background-color:var(--card-color);border-radius:16px;"><h2>No Articles Yet</h2></div>{% endif %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"></script>
    <script>
        particlesJS('particles-js', {"particles":{"number":{"value":80,"density":{"enable":true,"value_area":800}},"color":{"value":"#ffffff"},"shape":{"type":"circle"},"opacity":{"value":0.2,"random":true},"size":{"value":2,"random":true},"line_linked":{"enable":true,"distance":150,"color":"#ffffff","opacity":0.1,"width":1},"move":{"enable":true,"speed":1,"direction":"none","random":false,"straight":false,"out_mode":"out","bounce":false}},"interactivity":{"detect_on":"canvas","events":{"onhover":{"enable":true,"mode":"grab"},"onclick":{"enable":true,"mode":"push"},"resize":true}}});
    </script></body></html>
    """
    article_html_template = """... (文章页模板可以保持不变) ..."""
    
    articles_data = []; all_journals = set()
    # ... (后面的网站生成逻辑不变)

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    discover_and_process_files()
    generate_website()
