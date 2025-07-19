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
# 1. 配置和初始化
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

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================

def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values(): (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def extract_text_from_epub(epub_path):
    try:
        book = epub.read_epub(epub_path)
        return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e:
        logger.error(f"提取EPUB失败 {epub_path}: {e}")
        return ""

def process_and_save_articles_from_text(full_text, topic_dir, base_filename):
    """【返璞归真版】核心处理逻辑：找到就保存"""
    potential_articles = re.split(r'\n\s*\n\s*\n+', full_text)
    saved_count = 0
    for i, article_text in enumerate(potential_articles):
        article_text = article_text.strip()
        # 只要长度超过1000个字符，我们就认为它是一篇文章
        if len(article_text) > 1000:
            output_path = topic_dir / f"{base_filename}_art_{i+1}.md"
            # 不再做复杂的判断，直接保存
            with output_path.open("w", encoding="utf-8") as f:
                f.write(article_text)
            logger.info(f"已保存: {output_path.name}")
            saved_count += 1
    return saved_count

def find_and_process_magazines():
    """遍历所有杂志文件夹，处理所有找到的 .epub 文件"""
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!")
        return
    
    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        topic = info["topic"]
        logger.info(f"--- 正在扫描: {source_folder} ---")
        if not source_folder.is_dir():
            continue

        for file_path in source_folder.glob('*.epub'):
            if magazine_name in file_path.name.lower():
                # 检查是否已经处理过
                # 我们通过检查第一篇文章是否存在来判断
                check_path = ARTICLES_DIR / topic / f"{file_path.stem}_art_1.md"
                if check_path.exists():
                    continue

                logger.info(f"处理新杂志: {file_path.name}")
                full_text = extract_text_from_epub(str(file_path))
                if full_text:
                    process_and_save_articles_from_text(full_text, ARTICLES_DIR / topic, file_path.stem)

def generate_website():
    """生成最终的网站"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #0d1117; color: #c9d1d9; margin: 0; padding: 4rem 2rem; }
        .container { max-width: 1320px; margin: 0 auto; } .header { text-align: center; margin-bottom: 5rem; }
        h1 { font-size: 5rem; font-weight: 700; color: #fff; }
        .grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
        .card { background: #161b22; border: 1px solid rgba(139, 148, 158, 0.2); border-radius: 16px; padding: 2rem; }
        .card-title { font-size: 1.5rem; margin: 0 0 1rem 0; color: #fff; }
        .card-footer { margin-top: auto; padding-top: 1.5rem; border-top: 1px solid rgba(139, 148, 158, 0.2); }
    </style></head>
    <body><div class="container"><div class="header"><h1>AI Curated Journals</h1></div><div class="grid">
        {% for article in articles %}
            <div class="card">
                <h5 class="card-title">{{ article.title }}</h5>
                <div class="card-footer"><a href="{{ article.url }}" style="color:#33a0ff;">Read More</a></div>
            </div>
        {% endfor %}
        {% if not articles %}<div style="text-align:center;padding:4rem;background-color:#161b22;border-radius:16px;"><h2>No Articles Yet</h2></div>{% endif %}
    </div></div></body></html>
    """
    article_html_template = """
    <!DOCTYPE html><html><head><title>{{ title }}</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
    <body class="bg-dark text-light"><div class="container py-5"><h1 class="mb-4">{{ title }}</h1><div>{{ content }}</div>
    <hr class="my-4"><a href="index.html">Back to List</a></div></body></html>
    """
    articles_data = []
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            try:
                title = md_file.stem
                with md_file.open('r', encoding='utf-8') as f: content = f.read()
                article_filename = f"{md_file.stem}.html"
                article_path = WEBSITE_DIR / article_filename
                article_html = jinja2.Template(article_html_template).render(title=title, content=markdown2.markdown(content))
                article_path.write_text(article_html, encoding='utf-8')
                articles_data.append({"title": title, "url": article_filename})
            except Exception as e:
                logger.error(f"生成网页时处理文件 {md_file} 失败: {e}")
                continue
    
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data)
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    find_and_process_magazines()
    generate_website()
