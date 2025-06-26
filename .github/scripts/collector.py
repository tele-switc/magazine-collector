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
    for info in MAGAZINES.values(): (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def clean_article_text(text):
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text); text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'subscribe now|for more information|visit our website|follow us on', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Page\s+\d+', '', text); return re.sub(r'\n\s*\n', '\n\n', text).strip()

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
            keyword = feature_names[i]; pos_tag = nltk.pos_tag([keyword.split()[0]])[0][1]
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
        for file_path in source_folder.rglob('*.epub'):
            if magazine_name in file_path.name.lower() and file_path.stem not in magazine_contents:
                logger.info(f"读取: {file_path.name}")
                full_text = extract_text_from_epub(str(file_path))
                if full_text: magazine_contents[file_path.stem] = split_text_into_articles(full_text)
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
    try:
        book = epub.read_epub(epub_path); return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e: logger.error(f"提取EPUB失败 {epub_path}: {e}"); return ""

def save_article(output_path, text_content, title, author):
    word_count = len(text_content.split()); reading_time = f"~{round(word_count / 200)} min"
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nauthor: {author}\nwords: {word_count}\nreading_time: {reading_time}\n---\n\n{text_content}")
    logger.info(f"已保存: {output_path.name}")

def generate_website():
    # ... (此函数无需修改)
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --accent-color: #33a0ff; --bg-color: #0d1117; --card-color: #161b22; --text-color: #c9d1d9; 
                --secondary-text: #8b949e; --border-color: rgba(139, 148, 158, 0.2); }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 4rem 2rem;
               background-image: radial-gradient(var(--secondary-text) 1px, transparent 0); background-size: 40px 40px; }
        .container { max-width: 1320px; margin: 0 auto; } .header { text-align: center; margin-bottom: 5rem; }
        .header h1 { font-size: 5rem; font-weight: 700; color: #fff; margin: 0; letter-spacing: -2px; }
        .grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
        .card { background: var(--card-color); border: 1px solid var(--border-color); border-radius: 16px;
                transition: transform 0.3s ease, box-shadow 0.3s ease; display: flex; flex-direction: column; }
        .card:hover { transform: translateY(-8px); box-shadow: 0 0 30px rgba(51, 160, 255, 0.2); border-color: var(--accent-color); }
        .card-content { padding: 2rem; flex-grow: 1; } .card-title { font-size: 1.5rem; margin: 0 0 1rem 0; color: #fff; }
        .card-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 1.5rem; margin-top: auto; border-top: 1px solid var(--border-color); }
        .meta-info { font-size: 0.85rem; color: #8e8e8e; }
        .read-more-btn { font-size: 0.9rem; font-weight: 500; color: #fff; border: 1px solid var(--accent-color);
                         padding: 0.8rem 1.6rem; border-radius: 12px; text-decoration: none; transition: all 0.2s ease; }
        .read-more-btn:hover { background-color: var(--accent-color); color: var(--bg-color); }
    </style></head>
    <body><div class="container"> <div class="header"><h1>AI Curated Journals</h1></div> <div class="grid">
        {% for article in articles %}
            <div class="card"><div class="card-content">
                <h5 class="card-title">{{ article.title }}</h5>
                <div class="card-footer"><span class="meta-info">By {{ article.author }} | {{ article.reading_time }}</span><a href="{{ article.url }}" class="read-more-btn">Read Article</a></div>
            </div></div>
        {% endfor %}
        </div>{% if not articles %}<div style="text-align:center;padding:4rem;background-color:#1e1e1e;border-radius:16px;"><h2>No Articles Yet</h2></div>{% endif %}
    </div></body></html>
    """
    article_html_template = '''
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Lora', serif; background-color: #0a0a0a; color: #e0e0e0; margin: 0;
               background-image: radial-gradient(#222 1px, transparent 0); background-size: 30px 30px; }
        .container { max-width: 760px; margin: 5rem auto; padding: 3rem; background-color: #121212; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1);}
        .back-link { font-family: 'Inter', sans-serif; display: inline-block; margin-bottom: 4rem; text-decoration: none; color: #8e8e8e; }
        .back-link:hover { color: #00aaff; } h1 { font-family: 'Inter', sans-serif; font-size: 3.5rem; line-height: 1.2; color: #fff; }
        .article-meta { font-family: 'Inter', sans-serif; color: #888; margin: 1.5rem 0 4rem 0; border-bottom: 1px solid #333; padding-bottom: 2rem;}
        .article-body { font-size: 1.25rem; line-height: 2.2; }
    </style></head>
    <body><div class="container"><a href="index.html" class="back-link">← Back to List</a><h1>{{ title }}</h1>
    <p class="article-meta">By {{ author }} | From {{ magazine }} | {{ reading_time }}</p>
    <div class="article-body">{{ content }}</div></div></body></html>
    '''
    
    articles_data = []
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            try:
                with md_file.open('r', encoding='utf-8') as f: content_lines = f.readlines()
                title = content_lines[1].replace('title: ', '').strip(); author = content_lines[2].replace('author: ', '').strip()
                reading_time = content_lines[4].replace('reading_time: ', '').strip(); content = "".join(content_lines[6:])
                magazine = re.match(r'([a-zA-Z]+)', md_file.name).group(1).capitalize()
                article_filename = f"{md_file.stem}.html"; article_path = WEBSITE_DIR / article_filename
                article_template = jinja2.Template(article_html_template)
                article_html = article_template.render(title=title, content=markdown2.markdown(content), author=author, magazine=magazine, topic=topic_dir.name.capitalize(), reading_time=reading_time)
                article_path.write_text(article_html, encoding='utf-8')
                articles_data.append({"title": title, "preview": re.sub(r'\s+', ' ', content[:200]), "url": article_filename, "topic": topic_dir.name, "magazine": magazine, "author": author, "reading_time": reading_time})
            except Exception as e: logger.error(f"生成网页时处理文件 {md_file} 失败: {e}"); continue
    articles_data.sort(key=lambda x: x['title'])
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data)
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。")

if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
