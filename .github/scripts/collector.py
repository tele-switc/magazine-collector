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
NON_ARTICLE_KEYWORDS = ['contents', 'index', 'editor', 'letter', 'subscription', 'classifieds', 'masthead', 'copyright', 'advertisement', 'the world this week']

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================

def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def split_text_into_articles(text):
    potential_articles = re.split(r'\n\s*\n\s*\n+', text)
    articles = []
    for article_text in potential_articles:
        article_text = article_text.strip()
        lower_text = article_text.lower()
        if sum(1 for keyword in NON_ARTICLE_KEYWORDS if keyword in lower_text) > 1: continue
        if len(article_text.split()) < 200: continue
        first_line = article_text.split('\n')[0].strip()
        if len(first_line) > 150 or len(first_line) < 10: continue
        articles.append(article_text)
    return articles

def process_all_magazines():
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!")
        return
    try: nltk.data.find('tokenizers/punkt')
    except LookupError: nltk.download('punkt')
    
    processed_fingerprints = set()
    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        topic = info["topic"]
        if not source_folder.is_dir(): continue
        logger.info(f"--- 正在扫描: {source_folder} ---")

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

                            first_line = article_content.strip().split('\n')[0]
                            title = first_line.replace('#', '').strip()
                            author_match = re.search(r'By\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', article_content)
                            author = author_match.group(1) if author_match else "N/A"
                            
                            article_md_filename = f"{file_path.stem}_art_{i+1}.md"
                            output_path = ARTICLES_DIR / topic / article_md_filename
                            save_article(output_path, article_content, title, author)
                except Exception as e:
                    logger.error(f"处理文件 {file_path.name} 时出错: {e}")

def extract_text_from_epub(epub_path):
    try:
        book = epub.read_epub(epub_path)
        return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e: logger.error(f"提取EPUB失败 {epub_path}: {e}"); return ""

def save_article(output_path, text_content, title, author):
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nauthor: {author}\n---\n\n{text_content}")
    logger.info(f"已保存: {output_path.name} (作者: {author})")

def generate_website():
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --accent-color: #007aff; --background-color: #f0f2f5; --card-background: rgba(255, 255, 255, 0.7);
                --text-color: #1d1d1f; --secondary-text: #6e6e73; --border-radius: 20px; }
        body { font-family: 'Inter', sans-serif; background-color: var(--background-color); color: var(--text-color); margin: 0; padding: 4rem 2rem; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { font-size: 4rem; font-weight: 700; text-align: center; margin-bottom: 4rem; color: #000; }
        .grid { display: grid; gap: 2.5rem; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); }
        .card { background: var(--card-background); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.2); border-radius: var(--border-radius);
                box-shadow: 0 10px 30px rgba(0,0,0,0.1); transition: all 0.3s ease; display: flex; flex-direction: column; }
        .card:hover { transform: translateY(-8px); box-shadow: 0 15px 40px rgba(0,0,0,0.15); }
        .card-content { padding: 2rem; flex-grow: 1; display: flex; flex-direction: column; }
        .card-title { font-size: 1.4rem; font-weight: 500; margin: 0 0 1rem 0; }
        .card-preview { font-size: 1rem; line-height: 1.6; color: var(--secondary-text); margin-bottom: 2rem; flex-grow: 1; }
        .card-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 1.5rem; border-top: 1px solid rgba(0,0,0,0.05); }
        .meta-info { font-size: 0.85rem; color: var(--secondary-text); }
        .read-more-btn { font-size: 0.9rem; font-weight: 500; color: #fff; background-color: var(--accent-color);
                         padding: 0.7rem 1.4rem; border-radius: 10px; text-decoration: none; transition: all 0.2s ease; }
        .read-more-btn:hover { background-color: #0056b3; transform: scale(1.05); }
    </style></head>
    <body><div class="container"><h1>Journals</h1><div class="grid">
    {% for article in articles %}
        <div class="card">
            <div class="card-content">
                <h5 class="card-title">{{ article.title }}</h5>
                <p class="card-preview">{{ article.preview }}...</p>
                <div class="card-footer">
                    <span class="meta-info">By {{ article.author }} in {{ article.magazine }}</span>
                    <a href="{{ article.url }}" class="read-more-btn">Read More</a>
                </div>
            </div>
        </div>
    {% endfor %}
    </div>{% if not articles %}<div class="no-articles" style="text-align:center;padding:4rem;"><h2>No Articles Yet</h2></div>{% endif %}
    </div></body></html>
    """
    article_html_template = '''
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Lora', serif; background-color: #fff; color: #1a1a1a; margin: 0; }
        .container { max-width: 720px; margin: 5rem auto; padding: 0 2rem; }
        .back-link { font-family: 'Inter', sans-serif; display: inline-block; margin-bottom: 3rem; text-decoration: none; color: #555; font-weight: 500; }
        .back-link:hover { text-decoration: underline; color: #007aff; }
        h1 { font-family: 'Inter', sans-serif; font-size: 3rem; font-weight: 700; line-height: 1.2; margin-bottom: 1rem; }
        .article-meta { font-family: 'Inter', sans-serif; color: #888; margin-bottom: 3rem; border-bottom: 1px solid #eee; padding-bottom: 1rem;}
        .article-body { font-size: 1.2rem; line-height: 2.2; }
    </style></head>
    <body><div class="container">
        <a href="index.html" class="back-link">← Back to Article List</a>
        <h1>{{ title }}</h1>
        <p class="article-meta">By {{ author }} | From {{ magazine }} | Topic: {{ topic }}</p>
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
                content = "".join(content_lines[4:])
                magazine_match = re.match(r'([a-zA-Z]+)', md_file.name)
                magazine = magazine_match.group(1).capitalize() if magazine_match else "Unknown"
                article_filename = f"{md_file.stem}.html"
                article_path = WEBSITE_DIR / article_filename
                
                article_template = jinja2.Template(article_html_template)
                article_html = article_template.render(title=title, content=markdown2.markdown(content), author=author, magazine=magazine, topic=topic_dir.name.capitalize())
                article_path.write_text(article_html, encoding='utf-8')
                
                articles_data.append({"title": title, "preview": re.sub(r'\s+', ' ', content[:200]), "url": article_filename, "topic": topic_dir.name, "magazine": magazine, "author": author})
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
