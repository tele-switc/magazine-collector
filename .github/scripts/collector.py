import os
import re
import json
import requests
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import ebooklib
from ebooklib import epub
import pdfplumber
import nltk
from bs4 import BeautifulSoup
from github import Github
import logging
from dotenv import load_dotenv
import markdown2
import jinja2

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 配置
TARGET_REPO = "hehonghui/awesome-english-ebooks"
# 把旧的 MAGAZINES 字典替换成下面这个最终版
MAGAZINES = {
    "economist": {"folder": "01_economist", "pattern": r".*(economist|Economist).*\.(epub|pdf)"},
    "wired": {"folder": "05_wired", "pattern": r".*(wired|Wired).*\.(epub|pdf)"},
    "atlantic": {"folder": "04_atlantic", "pattern": r".*(atlantic|Atlantic).*\.(epub|pdf)"},
}
TOPICS_KEYWORDS = {
    "technology": ["tech", "technology", "ai", "artificial intelligence", "digital", "software", "hardware", "computer", "internet", "cyber", "machine learning", "blockchain", "data", "algorithm"],
    "finance": ["finance", "economy", "economic", "market", "stock", "banking", "investment", "trade", "fiscal", "monetary", "inflation", "recession", "currency", "debt"],
    "science": ["science", "mathematics", "physics", "chemistry", "biology", "research", "discovery", "experiment", "theory", "scientific", "quantum", "equation", "hypothesis"],
    "world_affairs": ["politics", "war", "conflict", "diplomacy", "international", "global", "government", "policy", "election", "crisis", "treaty", "sanction", "alliance", "nation"]
}
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")

def setup_storage():
    """创建存储文章的目录结构"""
    ARTICLES_DIR.mkdir(exist_ok=True)
    for topic in TOPICS_KEYWORDS.keys():
        (ARTICLES_DIR / topic).mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)

def get_github_token():
    """获取GitHub令牌"""
    return os.environ.get("GITHUB_TOKEN")

def download_magazine(magazine_name, file_pattern):
    """下载杂志文件"""
    token = get_github_token()
    if not token:
        logger.error("GITHUB_TOKEN 未设置，无法下载文件。")
        return None
    g = Github(token)
    repo = g.get_repo(TARGET_REPO)
    folder_path = MAGAZINES[magazine_name]["folder"]
    try:
        contents = repo.get_contents(folder_path)
        matching_files = [content for content in contents if content.type == "file" and re.match(file_pattern, content.name.lower())]
        if not matching_files:
            logger.warning(f"在 {folder_path} 中未找到匹配的文件。")
            return None
        latest_file = max(matching_files, key=lambda x: x.name)
        logger.info(f"正在下载: {latest_file.name}")
        temp_dir = tempfile.mkdtemp()
        local_file_path = Path(temp_dir) / latest_file.name
        file_content = latest_file.decoded_content
        local_file_path.write_bytes(file_content)
        return str(local_file_path)
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        return None

def extract_text_from_epub(epub_path):
    """从EPUB文件中提取文本"""
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
    """从PDF文件中提取文本"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
    except Exception as e:
        logger.error(f"从 PDF {pdf_path} 提取文本失败: {e}")
        return ""

def classify_text(text):
    """对文本内容进行主题分类"""
    articles = re.split(r'\n\s*#{1,3}\s+|\n\n+(?=[A-Z])', text.lower())
    classified = {topic: [] for topic in TOPICS_KEYWORDS}
    for article in articles:
        if len(article.strip()) < 200: continue
        topic_scores = {
            topic: sum(1 for keyword in keywords if re.search(r'\b' + re.escape(keyword) + r'\b', article))
            for topic, keywords in TOPICS_KEYWORDS.items()
        }
        if any(topic_scores.values()):
            best_topic = max(topic_scores, key=topic_scores.get)
            classified[best_topic].append(article.strip())
    return classified

def save_articles(magazine_name, classified_articles):
    """保存分类后的文章"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    has_saved = False
    for topic, articles in classified_articles.items():
        if not articles: continue
        output_file = ARTICLES_DIR / topic / f"{magazine_name}_{today_str}.md"
        with output_file.open("w", encoding="utf-8") as f:
            f.write(f"# {magazine_name.capitalize()} - {topic.capitalize()} Articles ({today_str})\n\n")
            for i, article in enumerate(articles, 1):
                title = article.split('\n')[0].strip() or f"Article {i}"
                f.write(f"## {title}\n\n{article}\n\n---\n\n")
        has_saved = True
        logger.info(f"已保存 {len(articles)} 篇文章到 {output_file}")
    return has_saved

def generate_website():
    """生成GitHub Pages网站"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>杂志文章收集器</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>body{padding:20px;background-color:#f8f9fa;}.card-text{font-size:0.9rem;}</style></head>
    <body><div class="container"><h1 class="my-4">杂志文章更新</h1>
    <div class="row">{% for article in articles %}<div class="col-md-4 mb-4"><div class="card h-100">
    <div class="card-body"><h5 class="card-title">{{ article.title }}</h5>
    <h6 class="card-subtitle mb-2 text-muted">{{ article.magazine|capitalize }} | {{ topic_names[article.topic] }}</h6>
    <p class="card-text">{{ article.preview }}...</p></div>
    <div class="card-footer bg-transparent border-top-0"><a href="{{ article.url }}" class="btn btn-sm btn-outline-primary">阅读全文</a>
    <small class="text-muted float-end">{{ article.date }}</small></div></div></div>{% endfor %}</div></div></body></html>
    """
    articles_data = []
    topic_names = {"technology": "科技", "finance": "金融", "science": "科学", "world_affairs": "世界局势"}

    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            magazine = md_file.stem.split('_')[0]
            with md_file.open('r', encoding='utf-8') as f: content = f.read()
            article_sections = re.split(r'^## (.+?)\n', content, flags=re.MULTILINE)[1:]
            for i in range(0, len(article_sections), 2):
                title, article_content = article_sections[i], article_sections[i+1]
                article_filename = f"{md_file.stem}_{i//2}.html"
                article_path = WEBSITE_DIR / article_filename
                article_html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{title}</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
                <style>body{{padding:30px;max-width:800px;margin:0 auto;line-height:1.7;}}</style></head>
                <body><nav><a href="index.html">返回首页</a></nav><h1 class="my-4">{title}</h1><div>{markdown2.markdown(article_content)}</div></body></html>"""
                article_path.write_text(article_html, encoding='utf-8')
                articles_data.append({
                    "title": title, "preview": re.sub(r'\s+', ' ', article_content[:150]), "url": article_filename,
                    "topic": topic_dir.name, "magazine": magazine, "date": md_file.stem.split('_')[-1]
                })

    if not articles_data:
        logger.warning("没有找到任何 .md 文章来生成网站。")
        return

    articles_data.sort(key=lambda x: x['date'], reverse=True)
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data, topic_names=topic_names)
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。")

def main():
    """主函数"""
    logger.info("开始运行杂志收集器")
    setup_storage()
    has_downloaded_new = False
    for magazine_name, info in MAGAZINES.items():
        logger.info(f"处理 {magazine_name} 杂志")
        file_path = download_magazine(magazine_name, info["pattern"])
        if not file_path: continue
        text_content = ""
        if file_path.endswith(".epub"): text_content = extract_text_from_epub(file_path)
        elif file_path.endswith(".pdf"): text_content = extract_text_from_pdf(file_path)
        if text_content:
            classified_articles = classify_text(text_content)
            if save_articles(magazine_name, classified_articles):
                has_downloaded_new = True
        os.remove(file_path)
    logger.info("开始生成网站，使用所有已存在的文章。")
    generate_website()

if __name__ == "__main__":
    main()
