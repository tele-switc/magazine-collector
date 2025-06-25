import os
import re
from pathlib import Path
import ebooklib
from ebooklib import epub
import pdfplumber
from bs4 import BeautifulSoup
import logging
import markdown2
import jinja2
import nltk

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 配置
SOURCE_REPO_PATH = Path("source_repo")
MAGAZINES = {
    "economist": {"folder": "01_economist", "topic": "world_affairs"},
    "wired": {"folder": "05_wired", "topic": "technology"},
    "atlantic": {"folder": "04_atlantic", "topic": "world_affairs"}
}
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")

def setup_directories():
    """创建所有需要的目录"""
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def process_all_magazines():
    """遍历、下载、处理所有在目标仓库中能找到的杂志文件"""
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!")
        return

    # 下载 NLTK 数据
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')

    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        topic = info["topic"]
        logger.info(f"--- 正在扫描: {source_folder} ---")

        if not source_folder.is_dir():
            logger.warning(f"找不到目录: {source_folder}")
            continue

        for file_path in source_folder.iterdir():
            # 简化匹配逻辑：只要文件名包含杂志名，并且是 epub 格式
            if magazine_name in file_path.name.lower() and file_path.suffix == '.epub':
                
                # 用文件名本身作为唯一ID，避免日期解析问题
                output_filename = f"{file_path.stem}.md"
                output_path = ARTICLES_DIR / topic / output_filename

                # 如果处理过的文件已存在，则跳过
                if output_path.exists():
                    continue

                logger.info(f"发现并处理新文件: {file_path.name}")
                
                try:
                    text_content = extract_text_from_epub(str(file_path))
                    if text_content:
                        save_article(output_path, text_content, file_path.stem)
                except Exception as e:
                    logger.error(f"处理文件 {file_path.name} 时出错: {e}")

def extract_text_from_epub(epub_path):
    try:
        book = epub.read_epub(epub_path)
        return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e:
        logger.error(f"提取 EPUB 失败 {epub_path}: {e}")
        return ""

def save_article(output_path, text_content, title):
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{text_content}")
    logger.info(f"已保存文章到 {output_path}")

def generate_website():
    """根据所有已有的 .md 文件生成网站"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>文章收集器</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
    <body><div class="container"><h1 class="my-4">文章列表</h1><div class="list-group">
    {% for article in articles %}<a href="{{ article.url }}" class="list-group-item list-group-item-action">
    <div class="d-flex w-100 justify-content-between"><h5 class="mb-1">{{ article.title }}</h5><small>{{ article.topic }}</small></div>
    </a>{% endfor %}</div></div></body></html>
    """
    articles_data = []
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            articles_data.append({
                "title": md_file.stem,
                "url": f"{md_file.stem}.html",
                "topic": topic_dir.name.capitalize()
            })
            # 同时生成单独的 HTML 页面
            with md_file.open('r', encoding='utf-8') as f: content = f.read()
            article_html_path = WEBSITE_DIR / f"{md_file.stem}.html"
            article_html = f'<!DOCTYPE html><html><head><title>{md_file.stem}</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"><style>body{{padding:30px;max-width:800px;margin:0 auto;}}</style></head><body>{markdown2.markdown(content)}<hr/><a href="index.html">返回列表</a></body></html>'
            article_html_path.write_text(article_html, encoding='utf-8')
    
    articles_data.sort(key=lambda x: x['title'], reverse=True)
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data)
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()

    if articles_data:
        logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。")
    else:
        logger.info("网站生成完成，但没有找到任何文章。")

if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
