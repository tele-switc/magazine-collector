import os
import re
import requests
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import ebooklib
from ebooklib import epub
import pdfplumber
from bs4 import BeautifulSoup
from github import Github
import logging
import markdown2
import jinja2

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 配置
TARGET_REPO = "hehonghui/awesome-english-ebooks"
MAGAZINES = {
    "economist": {"folder": "01_economist", "pattern": r"economist.*(\d{4}[-.]\d{2}[-.]\d{2}).*\.(epub|pdf)", "topic": "world_affairs"},
    "wired": {"folder": "05_wired", "pattern": r"wired.*(\d{4}[-.]\d{2}[-.]\d{2}).*\.(epub|pdf)", "topic": "technology"},
    "atlantic": {"folder": "04_atlantic", "pattern": r"atlantic.*(\d{4}[-.]\d{2}[-.]\d{2}).*\.(epub|pdf)", "topic": "world_affairs"}
}
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")

def setup_storage():
    """创建存储文章和网站的目录"""
    ARTICLES_DIR.mkdir(exist_ok=True)
    for topic in set(m['topic'] for m in MAGAZINES.values()):
        (ARTICLES_DIR / topic).mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)

def get_github_token():
    """获取 GitHub 令牌"""
    return os.environ.get("GITHUB_TOKEN")

def download_and_process_magazine(magazine_name, magazine_info):
    """下载并处理指定杂志的所有历史文件（如果本地不存在）"""
    token = get_github_token()
    if not token:
        logger.error("GITHUB_TOKEN 未设置，无法继续。")
        return False
    
    g = Github(token)
    repo = g.get_repo(TARGET_REPO)
    folder_path = magazine_info["folder"]
    pattern = magazine_info["pattern"]
    topic = magazine_info["topic"]
    
    try:
        contents = repo.get_contents(folder_path)
    except Exception as e:
        logger.error(f"访问文件夹 {folder_path} 失败: {e}")
        return False

    downloaded_new = False
    for content in contents:
        if content.type == "file" and re.search(pattern, content.name.lower()):
            match = re.search(r'(\d{4}[-.]\d{2}[-.]\d{2})', content.name)
            if not match:
                logger.warning(f"无法从文件名 {content.name} 中提取日期，跳过。")
                continue
            
            date_str = match.group(1).replace('.', '-')
            output_filename = f"{magazine_name}_{date_str}.md"
            output_path = ARTICLES_DIR / topic / output_filename

            if output_path.exists():
                continue

            logger.info(f"发现新/未处理文件: {content.name}。准备处理...")
            temp_dir = tempfile.mkdtemp()
            local_file_path = Path(temp_dir) / content.name
            
            try:
                local_file_path.write_bytes(content.decoded_content)
                text_content = ""
                if local_file_path.suffix == ".epub":
                    text_content = extract_text_from_epub(str(local_file_path))
                elif local_file_path.suffix == ".pdf":
                    text_content = extract_text_from_pdf(str(local_file_path))
                
                if text_content:
                    save_single_article(output_path, text_content, magazine_name.capitalize(), topic.capitalize(), date_str)
                    downloaded_new = True
                
                os.remove(local_file_path)
            except Exception as e:
                logger.error(f"处理文件 {content.name} 时出错: {e}")
                continue
    
    return downloaded_new

def extract_text_from_epub(epub_path):
    try:
        book = epub.read_epub(epub_path)
        return "\n".join(
            BeautifulSoup(item.get_content(), 'html.parser').get_text()
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
        )
    except Exception as e:
        logger.error(f"从 EPUB {epub_path} 提取文本失败: {e}")
        return ""

def extract_text_from_pdf(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
    except Exception as e:
        logger.error(f"从 PDF {pdf_path} 提取文本失败: {e}")
        return ""

def save_single_article(output_path, text_content, magazine_title, topic_title, date_str):
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"# {magazine_title} - {topic_title} ({date_str})\n\n{text_content}")
    logger.info(f"已保存文章到 {output_path}")

def generate_website():
    """使用 articles 文件夹中所有 .md 文件生成网站"""
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
                articles_data.append({
                    "title": title, "preview": re.sub(r'\s+', ' ', content[:150]), "url": article_filename,
                    "topic": topic_dir.name, "magazine": magazine, "date": date
                })
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
    """主函数"""
    logger.info("开始运行杂志收集器")
    setup_storage()
    
    for magazine_name, info in MAGAZINES.items():
        logger.info(f"--- 开始处理 {magazine_name} ---")
        download_and_process_magazine(magazine_name, info)

    logger.info("所有杂志处理完毕，开始生成网站。")
    generate_website()

if __name__ == "__main__":
    main()
