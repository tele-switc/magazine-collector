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
    """【返璞归真版】使用最简单可靠的文件查找逻辑。"""
    if not SOURCE_REPO_PATH.is_dir(): logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!"); return
    all_article_contents = []; magazine_contents = {}
    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        if not source_folder.is_dir(): continue
        
        for file_path in source_folder.glob('*.epub'):
            if magazine_name in file_path.name.lower():
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
    """【终极美学版】带有动态科技图案和流光卡片"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        @property --angle { syntax: '<angle>'; initial-value: 0deg; inherits: false; }
        :root { --bg-color: #02040a; --text-color: #e6f1ff; --secondary-text: #8892b0;
                --card-bg: linear-gradient(145deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0));
                --border-color: rgba(255, 255, 255, 0.1); --glow-color: rgba(0, 191, 255, 0.5); }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 5rem 2rem;
               background-image: url('data:image/svg+xml,%3Csvg width="60" height="60" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg"%3E%3Cg fill="none" fill-rule="evenodd"%3E%3Cg fill="%231a1a1a" fill-opacity="0.4"%3E%3Cpath d="M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z"/%3E%3C/g%3E%3C/g%3E%3C/svg%3E');
               animation: bg-pan 60s linear infinite; }
        @keyframes bg-pan { 0% { background-position: 0% 0%; } 100% { background-position: 100% 100%; } }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { font-size: 5rem; text-align: center; margin-bottom: 5rem; color: #fff; text-shadow: 0 0 25px var(--glow-color); }
        .grid { display: grid; gap: 2.5rem; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); }
        .card { backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); background: var(--card-bg); border-radius: 20px; position: relative;
                padding: 1px; transition: all 0.4s ease; animation: fadeIn 0.5s ease-out backwards; animation-delay: calc(var(--i) * 0.1s); }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        .card:before { content: ''; position: absolute; inset: -1px; z-index: -1;
                       background: conic-gradient(from var(--angle), transparent 50%, var(--glow-color), transparent);
                       border-radius: inherit; animation: rotate 8s linear infinite; opacity: 0; transition: opacity 0.4s ease; }
        .card:hover:before { opacity: 1; }
        .card-inner { background: #0c0f18; border-radius: 19px; padding: 2rem; height: 100%; display: flex; flex-direction: column; }
        .card-title { font-size: 1.6rem; line-height: 1.4; color: #fff; margin: 0 0 2rem 0; flex-grow: 1; }
        .card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: auto; padding-top: 1.5rem; border-top: 1px solid var(--border-color); }
    </style></head>
    <body><div class="container"><h1>AI Curated Journals</h1><div class="grid">
    {% for article in articles %}
        <div class="card" style="--i: {{ loop.index0 }};">
            <div class="card-inner">
                <h5 class="card-title">{{ article.title }}</h5>
                <div class="card-footer"><span style="color:#8892b0;">By {{ article.author }}</span><a href="{{ article.url }}" style="color:#fff;text-decoration:none;">Read →</a></div>
            </div>
        </div>
    {% endfor %}
    </div>{% if not articles %}<div style="text-align:center;padding:4rem;background-color:rgba(22, 27, 34, 0.8);border-radius:16px;"><h2>No Articles Yet</h2></div>{% endif %}
    </div></body></html>
    """
    article_html_template = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }}</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet"><style>body { font-family: 'Lora', serif; background-color: #0d1117; color: #e6f1ff; margin: 0; background-image: url('data:image/svg+xml,...'); } .container { max-width: 760px; margin: 5rem auto; padding: 4rem; background-color: rgba(12, 15, 24, 0.8); backdrop-filter: blur(10px); border-radius: 16px; border: 1px solid rgba(255,255,255,0.1);} .back-link { font-family: 'Inter', sans-serif; display: inline-block; margin-bottom: 4rem; text-decoration: none; color: #8892b0; } .back-link:hover { color: #fff; } h1 { font-family: 'Inter', sans-serif; font-size: 3.5rem; line-height: 1.2; color: #fff; } .article-meta { font-family: 'Inter', sans-serif; color: #8892b0; margin: 1.5rem 0 4rem 0; border-bottom: 1px solid #333; padding-bottom: 2rem;} .article-body { font-size: 1.25rem; line-height: 2.2; }</style></head><body><div class="container"><a href="index.html" class="back-link">← Back to List</a><h1>{{ title }}</h1><p class="meta-info">By {{ author }} | From {{ magazine }} | {{ reading_time }}</p><div class="article-body">{{ content }}</div></div></body></html>"""
    
    articles_data = []
    # ... (后面的 generate_website 函数逻辑保持不变)
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            try:
                with md_file.open('r', encoding='utf-8') as f: content_lines = f.readlines()
                title, author, reading_time, content = content_lines[1].split(': ')[1].strip(), content_lines[2].split(': ')[1].strip(), content_lines[4].split(': ')[1].strip(), "".join(content_lines[6:])
                magazine = re.match(r'([a-zA-Z]+)', md_file.name).group(1).capitalize()
                article_filename, article_path = f"{md_file.stem}.html", WEBSITE_DIR / f"{md_file.stem}.html"
                article_template = jinja2.Template(article_html_template)
                article_html = article_template.render(title=title, content=markdown2.markdown(content), author=author, magazine=magazine, topic=topic_dir.name.capitalize(), reading_time=reading_time)
                article_path.write_text(article_html, encoding='utf-8')
                articles_data.append({"title": title, "preview": re.sub(r'\s+', ' ', content[:200]), "url": article_filename, "topic": topic_dir.name, "magazine": magazine, "author": author, "reading_time": reading_time})
            except Exception as e: logger.error(f"生成网页时处理文件 {md_file} 失败: {e}"); continue
    articles_data.sort(key=lambda x: x['title'])
    template = jinja2.Template(index_template_str)
    (WEBSITE_DIR / "index.html").write_text(template.render(articles=articles_data), encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。") if articles_data else logger.info("网站生成完成，但没有找到任何文章。")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    # 删除了脚本内部的 nltk 下载，完全依赖 yml 文件
    process_all_magazines()
    generate_website()
