import os
import re
import json
import requests
import tempfile
from datetime import datetime, timezone # 修正了这里
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
MAGAZINES = {
    "economist": {
        "folder": "01_economist",
        "pattern": r"economist.*\.(epub|pdf|mobi)",
        "update_day": "Friday",
        "update_frequency": "weekly"
    },
    "wired": {
        "folder": "02_wired",
        "pattern": r"wired.*\.(epub|pdf|mobi)",
        "update_day": "2",
        "update_frequency": "monthly"
    },
    "atlantic": {
        "folder": "03_atlantic",
        "pattern": r"atlantic.*\.(epub|pdf|mobi)",
        "update_day": "2",
        "update_frequency": "monthly"
    }
}

TOPICS_KEYWORDS = {
    "technology": ["tech", "technology", "ai", "artificial intelligence", "digital", "software", "hardware",
                  "computer", "internet", "cyber", "machine learning", "blockchain", "data", "algorithm"],
    "finance": ["finance", "economy", "economic", "market", "stock", "banking", "investment", "trade",
               "fiscal", "monetary", "inflation", "recession", "currency", "debt"],
    "science": ["science", "mathematics", "physics", "chemistry", "biology", "research", "discovery",
               "experiment", "theory", "scientific", "quantum", "equation", "hypothesis"],
    "world_affairs": ["politics", "war", "conflict", "diplomacy", "international", "global", "government",
                     "policy", "election", "crisis", "treaty", "sanction", "alliance", "nation"]
}

# 文章存储目录
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")

def setup_storage():
    """创建存储文章的目录结构"""
    for topic in TOPICS_KEYWORDS.keys():
        os.makedirs(ARTICLES_DIR / topic, exist_ok=True)
    os.makedirs(WEBSITE_DIR, exist_ok=True)

def get_github_token():
    """获取GitHub令牌"""
    return os.environ.get("GITHUB_TOKEN")

def check_repo_updates():
    """检查目标仓库的更新"""
    token = get_github_token()
    if not token:
        logger.warning("GITHUB_TOKEN 未设置，跳过更新检查，强制执行。")
        return True # 如果没有token，无法检查，直接当作需要更新

    g = Github(token)
    try:
        repo = g.get_repo(TARGET_REPO)
        latest_commits = list(repo.get_commits(path="/"))[:5]
        recent_updated = False
        
        for commit in latest_commits:
            commit_date = commit.commit.author.date
            # 修正了时区问题
            if (datetime.now(timezone.utc) - commit_date).days <= 2:
                recent_updated = True
                logger.info(f"仓库最近有更新: {commit.commit.message}")
                break # 只要有一个满足条件就够了

        if not recent_updated:
            logger.info("目标仓库在过去两天内没有更新。")
        return recent_updated

    except Exception as e:
        logger.error(f"检查仓库更新时出错: {e}，将强制执行。")
        return True # 如果检查出错，也强制执行以防万一

def download_magazine(magazine_name, file_pattern):
    """下载杂志文件"""
    token = get_github_token()
    g = Github(token)
    repo = g.get_repo(TARGET_REPO)

    magazine_info = MAGAZINES[magazine_name]
    folder_path = magazine_info["folder"]

    try:
        contents = repo.get_contents(folder_path)
    except Exception as e:
        logger.error(f"访问文件夹 {folder_path} 出错: {e}")
        return None

    matching_files = []
    for content in contents:
        if content.type == "file" and re.match(file_pattern, content.name.lower()):
            matching_files.append(content)

    if not matching_files:
        logger.warning(f"在 {folder_path} 中未找到匹配 {file_pattern} 的文件")
        return None

    matching_files.sort(key=lambda x: x.name, reverse=True)
    latest_file = matching_files[0]

    logger.info(f"正在下载: {latest_file.name}")
    temp_dir = tempfile.mkdtemp()
    local_file_path = os.path.join(temp_dir, latest_file.name)

    try:
        file_content = latest_file.decoded_content
        with open(local_file_path, "wb") as f:
            f.write(file_content)
        return local_file_path
    except Exception as e:
        logger.error(f"下载文件 {latest_file.name} 失败: {e}")
        return None


def extract_text_from_epub(epub_path):
    """从EPUB文件中提取文本"""
    try:
        book = epub.read_epub(epub_path)
        text_content = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content().decode('utf-8', errors='ignore'), 'html.parser')
                text_content.append(soup.get_text())
        return "\n".join(text_content)
    except Exception as e:
        logger.error(f"从 EPUB {epub_path} 提取文本失败: {e}")
        return ""


def extract_text_from_pdf(pdf_path):
    """从PDF文件中提取文本"""
    try:
        text_content = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_content.append(text)
        return "\n".join(text_content)
    except Exception as e:
        logger.error(f"从 PDF {pdf_path} 提取文本失败: {e}")
        return ""

def classify_text(text, file_type="article"):
    """对文本内容进行主题分类"""
    text = text.lower()
    articles = re.split(r'\n\s*#{1,3}\s+|\n\n+(?=[A-Z])', text)
    classified_articles = {topic: [] for topic in TOPICS_KEYWORDS}

    for article in articles:
        if len(article.strip()) < 100:
            continue

        article_topics = []
        for topic, keywords in TOPICS_KEYWORDS.items():
            hits = sum(1 for keyword in keywords if re.search(r'\b' + re.escape(keyword) + r'\b', article))
            if hits > 0:
                article_topics.append((topic, hits))

        if article_topics:
            article_topics.sort(key=lambda x: x[1], reverse=True)
            best_topic = article_topics[0][0]
            classified_articles[best_topic].append(article.strip())

    return classified_articles

def save_articles(magazine_name, classified_articles):
    """保存分类后的文章"""
    today = datetime.now().strftime("%Y-%m-%d")
    results = {}

    for topic, articles in classified_articles.items():
        if not articles:
            continue

        output_file = ARTICLES_DIR / topic / f"{magazine_name}_{today}.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# {magazine_name.capitalize()} - {topic.capitalize()} Articles ({today})\n\n")
            for i, article in enumerate(articles, 1):
                lines = article.split('\n')
                title = lines[0] if lines else f"Article {i}"
                f.write(f"## {title}\n\n{article}\n\n---\n\n")

        results[topic] = len(articles)
    return results

def generate_website():
    """生成GitHub Pages网站"""
    index_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>杂志文章收集器</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; background-color: #f8f9fa; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: all 0.3s ease; }
            .card:hover { transform: translateY(-5px); box-shadow: 0 8px 15px rgba(0,0,0,0.1); }
            .card-header { font-weight: bold; background-color: #f1f1f1; } .badge { margin-right: 5px; }
            .update-info { font-size: 0.8em; color: #6c757d; margin-top: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="mt-4 mb-4">杂志文章每日更新</h1>
            <p class="mb-4">以下是从经济学人、Wired和The Atlantic杂志收集的科技、金融、科学和世界局势相关文章</p>
            <div class="row">
                <div class="col-md-3">
                    <div class="card"><div class="card-header">主题</div><div class="card-body"><div class="list-group">
                        <a href="#" class="list-group-item list-group-item-action active" data-topic="all">全部文章</a>
                        {% for topic in topics %}<a href="#" class="list-group-item list-group-item-action" data-topic="{{ topic }}">{{ topic_names[topic] }}</a>{% endfor %}
                    </div></div></div>
                    <div class="card"><div class="card-header">杂志</div><div class="card-body"><div class="list-group">
                        <a href="#" class="list-group-item list-group-item-action active" data-magazine="all">全部杂志</a>
                        {% for magazine in magazines %}<a href="#" class="list-group-item list-group-item-action" data-magazine="{{ magazine }}">{{ magazine|capitalize }}</a>{% endfor %}
                    </div></div></div>
                </div>
                <div class="col-md-9"><div class="row" id="articles-container">
                    {% for article in articles %}<div class="col-md-6 article-card" data-topic="{{ article.topic }}" data-magazine="{{ article.magazine }}"><div class="card">
                        <div class="card-header d-flex justify-content-between align-items-center">{{ article.magazine|capitalize }}<span class="badge bg-primary">{{ topic_names[article.topic] }}</span></div>
                        <div class="card-body">
                            <h5 class="card-title">{{ article.title }}</h5><p class="card-text">{{ article.preview }}...</p>
                            <a href="{{ article.url }}" class="btn btn-sm btn-outline-primary">阅读全文</a><div class="update-info">{{ article.date }}</div>
                        </div>
                    </div></div>{% endfor %}
                </div></div>
            </div>
        </div>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                function filterArticles() {
                    const selectedTopic = document.querySelector('[data-topic].active').getAttribute('data-topic');
                    const selectedMagazine = document.querySelector('[data-magazine].active').getAttribute('data-magazine');
                    document.querySelectorAll('.article-card').forEach(article => {
                        const topicMatch = selectedTopic === 'all' || selectedTopic === article.getAttribute('data-topic');
                        const magazineMatch = selectedMagazine === 'all' || selectedMagazine === article.getAttribute('data-magazine');
                        article.style.display = topicMatch && magazineMatch ? 'block' : 'none';
                    });
                }
                document.querySelectorAll('[data-topic], [data-magazine]').forEach(item => {
                    item.addEventListener('click', function(e) {
                        e.preventDefault();
                        const group = this.hasAttribute('data-topic') ? 'data-topic' : 'data-magazine';
                        document.querySelectorAll(`[${group}]`).forEach(el => el.classList.remove('active'));
                        this.classList.add('active');
                        filterArticles();
                    });
                });
            });
        </script>
    </body>
    </html>
    """
    articles_data = []
    magazines = set()
    topics = set()
    topic_names = {"technology": "科技", "finance": "金融", "science": "科学", "world_affairs": "世界局势"}

    for topic in TOPICS_KEYWORDS.keys():
        topic_dir = ARTICLES_DIR / topic
        if not topic_dir.exists(): continue
        topics.add(topic)
        for md_file in topic_dir.glob("*.md"):
            magazine = md_file.stem.split('_')[0]
            magazines.add(magazine)
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            article_sections = re.split(r'^## (.+)$', content, flags=re.MULTILINE)[1:]
            for i in range(0, len(article_sections), 2):
                if i + 1 < len(article_sections):
                    title = article_sections[i].strip()
                    article_content = article_sections[i+1].strip()
                    article_id = f"{magazine}_{topic}_{i//2}_{md_file.stem.split('_')[-1]}"
                    article_filename = f"article_{article_id}.html"
                    article_path = WEBSITE_DIR / article_filename
                    article_html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>{title}</title>
                        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
                        <style>body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 30px; max-width: 800px; margin: 0 auto; line-height: 1.6; }}</style></head>
                        <body><nav aria-label="breadcrumb"><ol class="breadcrumb"><li class="breadcrumb-item"><a href="index.html">首页</a></li>
                        <li class="breadcrumb-item active" aria-current="page">{topic_names[topic]}</li></ol></nav>
                        <h1>{title}</h1>{markdown2.markdown(article_content)}</body></html>"""
                    with open(article_path, 'w', encoding='utf-8') as af: af.write(article_html)
                    preview = re.sub(r'\s+', ' ', article_content[:200])
                    articles_data.append({
                        "title": title, "preview": preview, "url": article_filename,
                        "topic": topic, "magazine": magazine, "date": md_file.stem.split('_')[-1]
                    })
    
    template = jinja2.Template(index_template)
    index_html = template.render(articles=sorted(articles_data, key=lambda x: x['date'], reverse=True), magazines=list(magazines), topics=list(topics), topic_names=topic_names)
    with open(WEBSITE_DIR / "index.html", 'w', encoding='utf-8') as f: f.write(index_html)
    with open(WEBSITE_DIR / ".nojekyll", 'w') as f: pass
    logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。")

def main():
    """主函数"""
    logger.info("开始运行杂志收集器")
    setup_storage()

    # 删除了更新检查和 FORCE_UPDATE 逻辑，确保每次都运行
    
    has_new_content = False
    for magazine_name, info in MAGAZINES.items():
        logger.info(f"处理 {magazine_name} 杂志")
        file_path = download_magazine(magazine_name, info["pattern"])
        if not file_path:
            logger.warning(f"无法下载 {magazine_name}")
            continue

        if file_path.endswith(".epub"): text_content = extract_text_from_epub(file_path)
        elif file_path.endswith(".pdf"): text_content = extract_text_from_pdf(file_path)
        else:
            logger.warning(f"不支持的文件格式: {file_path}")
            os.remove(file_path)
            continue
        
        if text_content:
            classified_articles = classify_text(text_content)
            topic_counts = save_articles(magazine_name, classified_articles)
            if any(topic_counts.values()):
                has_new_content = True
        
        os.remove(file_path)

# 我们暂时不关心有没有新内容，总是尝试生成网站
logger.info("无论是否有新内容，都尝试根据现有文章生成网站。")
generate_website()


if __name__ == "__main__":
    main()
