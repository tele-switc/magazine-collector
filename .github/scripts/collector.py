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
# 2. 核心功能函数 (这部分代码保持不变，因为我们的逻辑已经很完善了)
# ==============================================================================

def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def clean_article_text(text):
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'subscribe now|for more information|visit our website|follow us on', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Page\s+\d+', '', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

def split_text_into_articles(text):
    ending_punctuations = ('.', '?', '!', '"', '”', '’')
    potential_articles = re.split(r'\n\s*\n\s*\n+', text)
    articles = []
    for article_text in potential_articles:
        article_text = article_text.strip()
        if not article_text or not article_text.endswith(ending_punctuations): continue
        lower_text = article_text.lower()
        if sum(1 for keyword in NON_ARTICLE_KEYWORDS if keyword in lower_text) > 1: continue
        if len(article_text.split()) < 250: continue
        articles.append(article_text)
    if not articles: logger.warning("本次未能从文本中识别出任何符合质量标准的完整文章。")
    return articles

def generate_title_from_content(text_content):
    try:
        stop_words = list(stopwords.words('english'))
        stop_words.extend([r'\b\d+\b'])
        vectorizer = TfidfVectorizer(max_features=15, stop_words=stop_words, ngram_range=(1, 3))
        preview_text = " ".join(text_content.split()[:len(text_content.split())//3])
        if len(preview_text) < 100: preview_text = text_content
        vectorizer.fit([preview_text])
        keywords = vectorizer.get_feature_names_out()
        keywords = [k for k in keywords if not k.replace(' ', '').isdigit()]
        title = ' '.join(word.capitalize() for word in keywords[:5])
        if not title or len(title.split()) < 3:
            return nltk.sent_tokenize(text_content)[0]
        return title
    except Exception as e:
        logger.error(f"AI生成标题失败: {e}")
        try: return nltk.sent_tokenize(text_content)[0]
        except: return "Untitled Article"

def process_all_magazines():
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!")
        return
    try:
        nltk.data.find('tokenizers/punkt')
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('punkt')
        nltk.download('stopwords')
    processed_fingerprints = set()
    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        topic = info["topic"]
        logger.info(f"--- 正在扫描: {source_folder} ---")
        if not source_folder.is_dir(): continue
        for file_path in source_folder.rglob('*.epub'):
            if magazine_name in file_path.name.lower():
                check_path = ARTICLES_DIR / topic / f"{file_path.stem}_art_1.md"
                if check_path.exists(): continue
                logger.info(f"处理新杂志: {file_path.name}")
                try:
                    full_text = extract_text_from_epub(str(file_path))
                    if full_text:
                        articles_in_magazine = split_text_into_articles(full_text)
                        for i, article_content in enumerate(articles_in_magazine):
                            fingerprint = article_content.strip()[:60]
                            if fingerprint in processed_fingerprints: continue
                            processed_fingerprints.add(fingerprint)
                            cleaned_content = clean_article_text(article_content)
                            if len(cleaned_content.split()) < 200: continue
                            title = generate_title_from_content(cleaned_content)
                            author_match = re.search(r'By\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', cleaned_content)
                            author = author_match.group(1) if author_match else "N/A"
                            article_md_filename = f"{file_path.stem}_art_{i+1}.md"
                            output_path = ARTICLES_DIR / topic / article_md_filename
                            save_article(output_path, cleaned_content, title, author)
                except Exception as e: logger.error(f"处理文件 {file_path.name} 时出错: {e}")

def extract_text_from_epub(epub_path):
    try:
        book = epub.read_epub(epub_path)
        return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e: logger.error(f"提取EPUB失败 {epub_path}: {e}"); return ""

def save_article(output_path, text_content, title, author):
    word_count = len(text_content.split())
    reading_time = round(word_count / 200) 
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nauthor: {author}\nwords: {word_count}\nreading_time: {reading_time} min\n---\n\n{text_content}")
    logger.info(f"已保存: {output_path.name} (作者: {author})")

def generate_website():
    """【最终美学版】生成全新风格的网站。"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    # ↓↓↓ 这是最终的、融合了两种美学风格的模板 ↓↓↓
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg-color: #121212; --card-color: #1e1e1e; --text-color: #e0e0e0; --secondary-text: #8e8e8e;
                --border-color: rgba(255, 255, 255, 0.1); --accent-gradient: linear-gradient(45deg, #6c5dd3, #3f5efb); }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 4rem 2rem; }
        .container { max-width: 1320px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 5rem; }
        .header h1 { font-size: 4.5rem; font-weight: 700; color: #fff; margin: 0; }
        .header p { font-size: 1.25rem; color: var(--secondary-text); margin-top: 0.5rem; }
        .grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
        .card { background: var(--card-color); border: 1px solid var(--border-color); border-radius: 16px;
                transition: transform 0.3s ease, box-shadow 0.3s ease; display: flex; flex-direction: column; }
        .card:hover { transform: translateY(-10px); box-shadow: 0 20px 40px rgba(0,0,0,0.3); }
        .card-content { padding: 2rem; flex-grow: 1; display: flex; flex-direction: column; }
        .card-title { font-size: 1.5rem; font-weight: 500; margin: 0 0 1rem 0; color: #fff; line-height: 1.3; }
        .card-preview { font-size: 1rem; line-height: 1.7; color: var(--secondary-text); margin-bottom: 2rem; flex-grow: 1; border-left: 3px solid var(--border-color); padding-left: 1.5rem; }
        .card-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 1.5rem; border-top: 1px solid var(--border-color); }
        .meta-info { font-size: 0.85rem; color: #8e8e8e; }
        .read-more-btn { font-size: 0.9rem; font-weight: 500; color: #fff; background: var(--accent-gradient);
                         padding: 0.8rem 1.6rem; border-radius: 12px; text-decoration: none; transition: transform 0.2s ease; }
        .read-more-btn:hover { transform: scale(1.05); }
    </style></head>
    <body><div class="container">
        <div class="header"><h1>AI Curated Journals</h1><p>Intelligently curated articles from the world's leading journals.</p></div>
        <div class="grid">
        {% for article in articles %}
            <div class="card">
                <div class="card-content">
                    <h5 class="card-title">{{ article.title }}</h5>
                    <p class="card-preview">{{ article.preview }}...</p>
                    <div class="card-footer">
                        <span class="meta-info">By {{ article.author }} | ~{{ article.reading_time }}</span>
                        <a href="{{ article.url }}" class="read-more-btn">Read Article</a>
                    </div>
                </div>
            </div>
        {% endfor %}
        </div>
        {% if not articles %}<div class="no-articles" style="text-align:center;padding:4rem;background-color:#1e1e1e;border-radius:16px;"><h2>No Articles Yet</h2><p>The system will automatically update in the next cycle.</p></div>{% endif %}
    </div></body></html>
    """
    article_html_template = '''
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Lora', serif; background-color: #121212; color: #e0e0e0; margin: 0; }
        .container { max-width: 760px; margin: 5rem auto; padding: 0 2rem; }
        .back-link { font-family: 'Inter', sans-serif; display: inline-block; margin-bottom: 4rem; text-decoration: none; color: #8e8e8e; font-weight: 500; }
        .back-link:hover { color: #fff; }
        h1 { font-family: 'Inter', sans-serif; font-size: 3.5rem; font-weight: 700; line-height: 1.2; margin-bottom: 1.5rem; color: #fff; }
        .article-meta { font-family: 'Inter', sans-serif; color: #8e8e8e; margin-bottom: 4rem; border-bottom: 1px solid #333; padding-bottom: 2rem;}
        .article-body { font-size: 1.25rem; line-height: 2.2; }
        .article-body p { margin-bottom: 2rem; }
    </style></head>
    <body><div class="container">
        <a href="index.html" class="back-link">← Back to List</a>
        <h1>{{ title }}</h1>
        <p class="article-meta">By {{ author }} | From {{ magazine }} | ~{{ reading_time }} Read</p>
        <div class="article-body">{{ content }}</div>
    </div></body></html>
    '''
    
    articles_data = []
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            try:
                with md_file.open('r', encoding='utf-8') as f: content_lines = f.readlines()
                title = content_lines[1].replace('title: ', '').strip()
                author = content_lines[2].replace('author: ', '').strip()
                reading_time = content_lines[4].replace('reading_time: ', '').strip()
                content = "".join(content_lines[6:])
                magazine_match = re.match(r'([a-zA-Z]+)', md_file.name)
                magazine = magazine_match.group(1).capitalize() if magazine_match else "Unknown"
                article_filename = f"{md_file.stem}.html"
                article_path = WEBSITE_DIR / article_filename
                
                article_template = jinja2.Template(article_html_template)
                article_html = article_template.render(title=title, content=markdown2.markdown(content), author=author, magazine=magazine, topic=topic_dir.name.capitalize(), reading_time=reading_time)
                article_path.write_text(article_html, encoding='utf-8')
                
                articles_data.append({"title": title, "preview": re.sub(r'\s+', ' ', content[:200]), "url": article_filename, "topic": topic_dir.name, "magazine": magazine, "author": author, "reading_time": reading_time})
            except Exception as e:
                logger.error(f"生成网页时处理文件 {md_file} 失败: {e}")
                continue

    articles_data.sort(key=lambda x: x['title'])
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data)
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()

    if articles_data: logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。")
    else: logger.info("网站生成完成，但没有找到任何文章。")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
