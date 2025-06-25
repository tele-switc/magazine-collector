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
# 源仓库在本地的路径 (由 a.yml 文件中的 git clone 命令创建)
SOURCE_REPO_PATH = Path("source_repo")
MAGAZINES = {
    "economist": {"folder": "01_economist", "pattern": r"economist.*(\d{4}[-.]\d{2}[-.]\d{2}).*\.epub", "topic": "world_affairs"},
    "wired": {"folder": "05_wired", "pattern": r"wired.*(\d{4}[-.]\d{2}[-.]\d{2}).*\.epub", "topic": "technology"},
    "atlantic": {"folder": "04_atlantic", "pattern": r"atlantic.*(\d{4}[-.]\d{2}[-.]\d{2}).*\.epub", "topic": "world_affairs"}
}
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")

def setup_storage():
    """创建存储目录"""
    ARTICLES_DIR.mkdir(exist_ok=True)
    for topic in set(m['topic'] for m in MAGAZINES.values()):
        (ARTICLES_DIR / topic).mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)

def find_and_process_magazines():
    """在本地克隆的仓库中查找并处理文件"""
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 不存在！脚本将退出。")
        return

    # 下载 nltk 数据
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords')

    for magazine_name, info in MAGAZINES.items():
        logger.info(f"--- 开始处理 {magazine_name} ---")
        source_folder = SOURCE_REPO_PATH / info["folder"]
        pattern = info["pattern"]
        topic = info["topic"]

        if not source_folder.is_dir():
            logger.warning(f"在源仓库中找不到文件夹: {source_folder}")
            continue

        for file_path in source_folder.iterdir():
            if file_path.is_file() and re.search(pattern, file_path.name.lower()):
                match = re.search(r'(\d{4}[-.]\d{2}[-.]\d{2})', file_path.name)
                if not match:
                    continue
                
                date_str = match.group(1).replace('.', '-')
                output_filename = f"{magazine_name}_{date_str}.md"
                output_path = ARTICLES_DIR / topic / output_filename

                if output_path.exists():
                    continue

                logger.info(f"发现新文件: {file_path.name}。正在处理...")
                text_content = ""
                if file_path.suffix == ".epub":
                    text_content = extract_text_from_epub(str(file_path))
                # 暂时移除PDF处理，因为它可能非常慢或出错
                # elif file_path.suffix == ".pdf":
                #     text_content = extract_text_from_pdf(str(file_path))

                if text_content:
                    save_article(output_path, text_content, magazine_name.capitalize(), topic.capitalize(), date_str)

def extract_text_from_epub(epub_path):
    try:
        book = epub.read_epub(epub_path)
        return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e:
        logger.error(f"提取EPUB失败 {epub_path}: {e}")
        return ""

def save_article(output_path, text_content, magazine_title, topic_title, date_str):
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"# {magazine_title} - {topic_title} ({date_str})\n\n{text_content}")
    logger.info(f"已保存文章到 {output_path}")

def generate_website():
    """生成网站"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>杂志文章收集器</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>body{padding:20px;background-color:#f8f9fa;}.card-text{font-size:0.9rem;}</style></head>
    <body><div class="container"><h1 class="my-4">杂志文章更新</h1>
    <div class="row">{% for article in articles %}<div class="col-md-4 mb-4"><div class="card h-100">
    <div class="card-body"><h5 class="card-title">{{ article.title }}</h5>
    <h6 class="card-subtitle mb-2 text-muted">{{ article.magazine|capitalize }} | {{ article.topic.capitalize() }}</h6>
    <p class="card-text">{{ article.preview }}...</p></div>
    <div class="card-footer bg-transparent border-top-0"><a href="{{ article.url }}" class="btn btn-sm btn-outline-primary">阅读全文</a>
    <small class="text-muted float-end">{{ article.date }}</small></div></div></div>{% endfor %}</div></div></body></html>
    """
    articles_data = []
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            try:
                magazine, date = md_file.stem.split('_')
                with md_file.open('r', encoding='utf-8') as f: content = f.read()
                title = f"{magazine.capitalize()} - {date}"
                article_filename = f"{md_file.stem}.html"
                article_path = WEBSITE_DIR / article_filename
                article_html = f'<!DOCTYPE html><html><head><title>{title}</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"><style>body{{padding:30px;max-width:800px;margin:0 auto;line-height:1.7;}}</style></head><body><h1>{title}</h1><div>{markdown2.markdown(content)}</div></body></html>'
                article_path.write_text(article_html, encoding='utf-8')
                articles_data.append({"title": title, "preview": re.sub(r'\s+', ' ', content[:150]), "url": article_filename, "topic": topic_dir.name, "magazine": magazine, "date": date})
            except Exception as e:
                logger.error(f"生成网页时处理文件 {md_file} 失败: {e}")
                continue
    if not articles_data:
        logger.warning("没有找到任何 .md 文章来生成网站。")
        return
    articles_data.sort(key=lambda x: x['date'], reverse=True)
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data)
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info(f"网站生成完成，总共包含 {len(articles_data)} 篇文章。")

def main():
    logger.info("开始运行杂志收集器")
    setup_storage()
    find_and_process_magazines()
    generate_website()

if __name__ == "__main__":
    main()
