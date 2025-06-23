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
    g = Github(token)
    repo = g.get_repo(TARGET_REPO)
    
    # 获取最近更新的内容
    latest_commits = list(repo.get_commits(path="/"))[:5]  # 获取最近5个提交
    recent_updated = False
    
    for commit in latest_commits:
        commit_date = commit.commit.author.date
        # 使用 timezone.utc 来获取一个带时区的当前时间
        if (datetime.now(timezone.utc) - commit_date).days <= 2:  # 检查最近2天的更新
            recent_updated = True
            logger.info(f"仓库最近有更新: {commit.commit.message}")
            
    return recent_updated

def download_magazine(magazine_name, file_pattern):
    """下载杂志文件"""
    token = get_github_token()
    g = Github(token)
    repo = g.get_repo(TARGET_REPO)
    
    magazine_info = MAGAZINES[magazine_name]
    folder_path = magazine_info["folder"]
    
    # 获取目录内容
    try:
        contents = repo.get_contents(folder_path)
    except Exception as e:
        logger.error(f"访问文件夹{folder_path}出错: {e}")
        return None
    
    # 排序文件找到最新的
    matching_files = []
    for content in contents:
        if content.type == "file" and re.match(file_pattern, content.name.lower()):
            matching_files.append(content)
    
    if not matching_files:
        logger.warning(f"未找到匹配{magazine_name}的文件")
        return None
    
    # 按照名称排序，通常最新的文件名包含最近日期
    matching_files.sort(key=lambda x: x.name, reverse=True)
    latest_file = matching_files[0]
    
    # 下载文件内容
    logger.info(f"下载 {latest_file.name}")
    
    temp_dir = tempfile.mkdtemp()
    local_file_path = os.path.join(temp_dir, latest_file.name)
    
    with open(local_file_path, "wb") as f:
        file_content = repo.get_contents(latest_file.path).decoded_content
        f.write(file_content)
    
    return local_file_path

def extract_text_from_epub(epub_path):
    """从EPUB文件中提取文本"""
    book = epub.read_epub(epub_path)
    text_content = []
    
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content().decode('utf-8'), 'html.parser')
            text_content.append(soup.get_text())
    
    return "\n".join(text_content)

def extract_text_from_pdf(pdf_path):
    """从PDF文件中提取文本"""
    text_content = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_content.append(text)
    
    return "\n".join(text_content)

def classify_text(text, file_type="article"):
    """对文本内容进行主题分类"""
    text = text.lower()
    
    # 分割文本为文章/段落
    if file_type == "article":
        # 尝试基于标题或段落标记分割文章
        articles = re.split(r'\n\s*#{1,3}\s+|\n\n+(?=[A-Z])', text)
    else:
        # 将整个内容作为一个文章
        articles = [text]
    
    # 将文章按主题分类
    classified_articles = {topic: [] for topic in TOPICS_KEYWORDS}
    
    for article in articles:
        if len(article.strip()) < 100:  # 忽略太短的文本
            continue
            
        # 检测主题
        article_topics = []
        for topic, keywords in TOPICS_KEYWORDS.items():
            # 计算关键词命中率
            hits = sum(1 for keyword in keywords if re.search(r'\b' + re.escape(keyword) + r'\b', article))
            if hits > 0:
                article_topics.append((topic, hits))
        
        # 按命中次数排序并分配到最匹配的主题
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
            
        # 创建输出文件
        output_file = ARTICLES_DIR / topic / f"{magazine_name}_{today}.md"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# {magazine_name.capitalize()} - {topic.capitalize()} Articles ({today})\n\n")
            
            for i, article in enumerate(articles, 1):
                # 尝试提取文章标题
                lines = article.split('\n')
                title = lines[0] if lines else f"Article {i}"
                
                f.write(f"## {title}\n\n")
                f.write(f"{article}\n\n")
                f.write("---\n\n")
        
        results[topic] = len(articles)
    
    return results

def generate_website():
    """生成GitHub Pages网站"""
    # 创建网站首页
    index_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>杂志文章收集器</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                padding: 20px;
                background-color: #f8f9fa;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            .card {
                margin-bottom: 20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                transition: all 0.3s ease;
            }
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 8px 15px rgba(0,0,0,0.1);
            }
            .card-header {
                font-weight: bold;
                background-color: #f1f1f1;
            }
            .badge {
                margin-right: 5px;
            }
            .update-info {
                font-size: 0.8em;
                color: #6c757d;
                margin-top: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="mt-4 mb-4">杂志文章每日更新</h1>
            <p class="mb-4">以下是从经济学人、Wired和The Atlantic杂志收集的科技、金融、科学和世界局势相关文章</p>
            
            <div class="row">
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-header">主题</div>
                        <div class="card-body">
                            <div class="list-group">
                                <a href="#" class="list-group-item list-group-item-action active" data-topic="all">全部文章</a>
                                {% for topic in topics %}
                                <a href="#" class="list-group-item list-group-item-action" data-topic="{{ topic }}">{{ topic_names[topic] }}</a>
                                {% endfor %}
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="card-header">杂志</div>
                        <div class="card-body">
                            <div class="list-group">
                                <a href="#" class="list-group-item list-group-item-action active" data-magazine="all">全部杂志</a>
                                {% for magazine in magazines %}
                                <a href="#" class="list-group-item list-group-item-action" data-magazine="{{ magazine }}">{{ magazine|capitalize }}</a>
                                {% endfor %}
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-9">
                    <div class="row" id="articles-container">
                        {% for article in articles %}
                        <div class="col-md-6 article-card" 
                             data-topic="{{ article.topic }}" 
                             data-magazine="{{ article.magazine }}">
                            <div class="card">
                                <div class="card-header d-flex justify-content-between align-items-center">
                                    {{ article.magazine|capitalize }}
                                    <span class="badge bg-primary">{{ topic_names[article.topic] }}</span>
                                </div>
                                <div class="card-body">
                                    <h5 class="card-title">{{ article.title }}</h5>
                                    <p class="card-text">{{ article.preview }}...</p>
                                    <a href="{{ article.url }}" class="btn btn-sm btn-outline-primary">阅读全文</a>
                                    <div class="update-info">{{ article.date }}</div>
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                // 主题筛选
                document.querySelectorAll('[data-topic]').forEach(item => {
                    item.addEventListener('click', function(e) {
                        e.preventDefault();
                        const topic = this.getAttribute('data-topic');
                        
                        // 更新活动状态
                        document.querySelectorAll('[data-topic]').forEach(el => {
                            el.classList.remove('active');
                        });
                        this.classList.add('active');
                        
                        // 筛选文章
                        filterArticles();
                    });
                });
                
                // 杂志筛选
                document.querySelectorAll('[data-magazine]').forEach(item => {
                    item.addEventListener('click', function(e) {
                        e.preventDefault();
                        const magazine = this.getAttribute('data-magazine');
                        
                        // 更新活动状态
                        document.querySelectorAll('[data-magazine]').forEach(el => {
                            el.classList.remove('active');
                        });
                        this.classList.add('active');
                        
                        // 筛选文章
                        filterArticles();
                    });
                });
                
                // 筛选文章函数
                function filterArticles() {
                    const selectedTopic = document.querySelector('[data-topic].active').getAttribute('data-topic');
                    const selectedMagazine = document.querySelector('[data-magazine].active').getAttribute('data-magazine');
                    
                    document.querySelectorAll('.article-card').forEach(article => {
                        const articleTopic = article.getAttribute('data-topic');
                        const articleMagazine = article.getAttribute('data-magazine');
                        
                        const topicMatch = selectedTopic === 'all' || selectedTopic === articleTopic;
                        const magazineMatch = selectedMagazine === 'all' || selectedMagazine === articleMagazine;
                        
                        if (topicMatch && magazineMatch) {
                            article.style.display = 'block';
                        } else {
                            article.style.display = 'none';
                        }
                    });
                }
            });
        </script>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    
    # 获取文章数据
    articles_data = []
    magazines = set()
    topics = set()
    topic_names = {
        "technology": "科技",
        "finance": "金融",
        "science": "科学",
        "world_affairs": "世界局势"
    }
    
    # 遍历所有主题目录
    for topic in TOPICS_KEYWORDS.keys():
        topic_dir = ARTICLES_DIR / topic
        if not topic_dir.exists():
            continue
            
        topics.add(topic)
        
        # 遍历主题目录下的所有markdown文件
        for md_file in topic_dir.glob("*.md"):
            magazine = md_file.stem.split('_')[0]  # 从文件名提取杂志名
            magazines.add(magazine)
            
            # 解析markdown文件获取文章
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # 提取文章标题和内容
                article_sections = re.split(r'^## (.+)$', content, flags=re.MULTILINE)[1:]  # 分割为[标题, 内容, 标题, 内容...]
                
                for i in range(0, len(article_sections), 2):
                    if i+1 < len(article_sections):
                        title = article_sections[i].strip()
                        content = article_sections[i+1].strip()
                        
                        # 创建单独的文章HTML文件
                        article_id = f"{magazine}_{topic}_{i//2}_{md_file.stem.split('_')[-1]}"
                        article_filename = f"article_{article_id}.html"
                        article_path = WEBSITE_DIR / article_filename
                        
                        # 文章HTML模板
                        article_html = f"""
                        <!DOCTYPE html>
                        <html lang="en">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            <title>{title}</title>
                            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
                            <style>
                                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 30px; max-width: 800px; margin: 0 auto; line-height: 1.6; }}
                                h1 {{ margin-bottom: 20px; }}
                                .breadcrumb {{ margin-bottom: 30px; }}
                                .article-content {{ background-color: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                                .article-meta {{ margin-bottom: 20px; color: #6c757d; }}
                            </style>
                        </head>
                        <body>
                            <nav aria-label="breadcrumb">
                                <ol class="breadcrumb">
                                    <li class="breadcrumb-item"><a href="index.html">首页</a></li>
                                    <li class="breadcrumb-item"><a href="index.html">{topic_names[topic]}</a></li>
                                    <li class="breadcrumb-item active" aria-current="page">{magazine.capitalize()}</li>
                                </ol>
                            </nav>
                            
                            <div class="article-content">
                                <h1>{title}</h1>
                                <div class="article-meta">
                                    <span class="badge bg-primary">{topic_names[topic]}</span>
                                    <span class="badge bg-secondary">{magazine.capitalize()}</span>
                                    <span class="text-muted ms-2">{md_file.stem.split('_')[-1]}</span>
                                </div>
                                <div class="article-body">
                                    {markdown2.markdown(content)}
                                </div>
                            </div>
                            
                            <div class="text-center mt-4">
                                <a href="index.html" class="btn btn-outline-primary">返回首页</a>
                            </div>
                        </body>
                        </html>
                        """
                        
                        with open(article_path, 'w', encoding='utf-8') as af:
                            af.write(article_html)
                        
                        # 提取预览文本
                        preview = re.sub(r'\s+', ' ', content[:200])
                        
                        # 添加到文章列表
                        articles_data.append({
                            "title": title,
                            "preview": preview,
                            "url": article_filename,
                            "topic": topic,
                            "magazine": magazine,
                            "date": md_file.stem.split('_')[-1]
                        })
    
    # 渲染首页模板
    template = jinja2.Template(index_template)
    index_html = template.render(
        articles=articles_data,
        magazines=list(magazines),
        topics=list(topics),
        topic_names=topic_names
    )
    
    # 保存首页
    with open(WEBSITE_DIR / "index.html", 'w', encoding='utf-8') as f:
        f.write(index_html)
    
    # 创建一个空的.nojekyll文件，防止GitHub Pages使用Jekyll处理
    with open(WEBSITE_DIR / ".nojekyll", 'w') as f:
        pass

def main():
    """主函数"""
    logger.info("开始运行杂志收集器")
    
    # 创建存储结构
    setup_storage()
    
    # 检查仓库更新
    if not check_repo_updates() and not os.path.exists("FORCE_UPDATE"):
        logger.info("目标仓库没有最近更新，无需处理")
        return
    
    magazine_results = {}
    
    # 处理每本杂志
    for magazine_name, info in MAGAZINES.items():
        logger.info(f"处理 {magazine_name} 杂志")
        
        # 下载最新杂志
        file_path = download_magazine(magazine_name, info["pattern"])
        if not file_path:
            logger.warning(f"无法下载 {magazine_name}")
            continue
        
        # 根据文件类型提取文本
        if file_path.endswith(".epub"):
            text_content = extract_text_from_epub(file_path)
        elif file_path.endswith(".pdf"):
            text_content = extract_text_from_pdf(file_path)
        else:
            logger.warning(f"不支持的文件格式: {file_path}")
            continue
        
        # 分类文章
        classified_articles = classify_text(text_content)
        
        # 保存文章
        topic_counts = save_articles(magazine_name, classified_articles)
        magazine_results[magazine_name] = topic_counts
        
        # 清理临时文件
        os.remove(file_path)
    
    # 生成网站
    if magazine_results:
        generate_website()
        logger.info("网站生成完成")
    else:
        logger.warning("没有收集到任何文章")

if __name__ == "__main__":
    main()
