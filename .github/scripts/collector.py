import os
import re
from pathlib import Path
import ebooklib
from ebooklib import epub
import mobi
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

if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

SOURCE_REPO_PATHS = [Path("source_repo_1"), Path("source_repo_2")]
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")

# 【智能分类器】定义主题和对应的关键词
TOPICS = {
    "Technology": ["tech", "technology", "ai", "software", "digital", "computer", "internet", "cyber", "data"],
    "Science": ["science", "physics", "chemistry", "biology", "research", "discovery", "quantum", "universe", "dna"],
    "Business & Finance": ["finance", "economy", "market", "stock", "banking", "investment", "business", "trade"],
    "World Affairs": ["politics", "war", "conflict", "diplomacy", "international", "government", "policy", "election"],
    "Culture & Life": ["culture", "art", "history", "books", "life", "society", "psychology", "health"]
}
# 忽略列表
IGNORE_DIRS = ['.git', 'docs', 'images']

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================
def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for topic in TOPICS:
        (ARTICLES_DIR / topic).mkdir(exist_ok=True)

def extract_text(file_path):
    """根据文件类型提取文本"""
    if file_path.suffix == '.epub':
        try:
            book = epub.read_epub(str(file_path))
            return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        except Exception as e:
            logger.error(f"提取EPUB失败 {file_path.name}: {e}")
    elif file_path.suffix == '.mobi':
        try:
            book = mobi.Mobi(str(file_path))
            content = "".join(record.text for record in book)
            return BeautifulSoup(content, 'html.parser').get_text()
        except Exception as e:
            logger.error(f"提取MOBI失败 {file_path.name}: {e}")
    return ""

def classify_article(text_content):
    """【AI主题分类器】根据关键词为文章分配主题"""
    scores = {topic: 0 for topic in TOPICS}
    lower_text = text_content.lower()
    for topic, keywords in TOPICS.items():
        scores[topic] = sum(1 for keyword in keywords if keyword in lower_text)
    
    # 如果所有主题得分都低于一个阈值，则归为"General"
    if all(score < 3 for score in scores.values()):
        return "General"
    # 返回得分最高的主题
    return max(scores, key=scores.get)

def discover_and_process_files():
    """【自主探索模块】扫描所有源仓库，处理所有找到的刊物"""
    processed_files = set()
    for repo_path in SOURCE_REPO_PATHS:
        if not repo_path.is_dir(): continue
        logger.info(f"===== 正在扫描仓库: {repo_path} =====")
        
        # 扫描 MOBI 和 EPUB 两种格式
        for file_path in list(repo_path.rglob('*.epub')) + list(repo_path.rglob('*.mobi')):
            if any(ignored in file_path.parts for ignored in IGNORE_DIRS): continue
            
            # 使用文件名作为唯一标识符来避免重复
            if file_path.name in processed_files: continue
            processed_files.add(file_path.name)
            
            logger.info(f"  -> 发现文件: {file_path.name}")
            full_text = extract_text(file_path)
            if not full_text or len(full_text.split()) < 500: continue
            
            # 简单的文章拆分
            articles = re.split(r'\n\s*\n\s*\n+', full_text)
            for i, article_text in enumerate(articles):
                article_text = article_text.strip()
                if len(article_text.split()) > 250:
                    # 【调用AI主题分类器】
                    topic = classify_article(article_text)
                    topic_dir = ARTICLES_DIR / topic
                    topic_dir.mkdir(exist_ok=True)
                    
                    # 使用一个简单的标题
                    title = " ".join(article_text.split()[:10])
                    output_path = topic_dir / f"{file_path.stem}_art_{i+1}.md"
                    
                    with output_path.open("w", encoding="utf-8") as f:
                        f.write(f"---\ntitle: {title}\njournal: {file_path.parent.name}\n---\n\n{article_text}")
                    logger.info(f"已保存: {output_path.name} -> 主题: {topic}")

def generate_website():
    """【动态主题博物馆版】"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --accent-color: #33a0ff; --bg-color: #0d1117; --card-color: #161b22; --text-color: #c9d1d9; --secondary-text: #8b949e; --border-color: rgba(139, 148, 158, 0.2); }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 4rem 2rem; }
        .container { max-width: 1320px; margin: 0 auto; } .header { text-align: center; margin-bottom: 3rem; }
        h1 { font-size: 5rem; font-weight: 700; color: #fff; } .filters { text-align: center; margin-bottom: 4rem; }
        .filter-btn { background: none; border: 1px solid var(--border-color); color: var(--secondary-text); padding: 0.6rem 1.2rem; margin: 0.3rem; border-radius: 99px; cursor: pointer; transition: all 0.2s ease; }
        .filter-btn.active { background-color: var(--accent-color); color: #fff; border-color: var(--accent-color); }
        .grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
        .card { background: var(--card-color); border: 1px solid var(--border-color); border-radius: 16px; transition: opacity 0.3s ease; }
        .card-content { padding: 2rem; } .card-title { font-size: 1.5rem; color: #fff; margin-bottom: 1rem; }
        .card-footer { margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid var(--border-color); }
    </style></head>
    <body><div class="container"><div class="header"><h1>AI Curated Journals</h1></div>
        <div class="filters">
            <button class="filter-btn active" data-filter="all">All Topics</button>
            {% for topic in topics %}
            <button class="filter-btn" data-filter="{{ topic }}">{{ topic }}</button>
            {% endfor %}
        </div>
        <div class="grid">
        {% for article in articles %}
            <div class="card" data-topic="{{ article.topic }}">
                <div class="card-content">
                    <h5 class="card-title">{{ article.title }}...</h5>
                    <div class="card-footer"><span style="color:var(--secondary-text);">{{ article.journal }}</span><a href="{{ article.url }}" style="color:var(--accent-color);">Read More</a></div>
                </div>
            </div>
        {% endfor %}
        </div>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const filterBtns = document.querySelectorAll('.filter-btn');
            const articleCards = document.querySelectorAll('.card');
            filterBtns.forEach(btn => {
                btn.addEventListener('click', function() {
                    filterBtns.forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    const filter = this.getAttribute('data-filter');
                    articleCards.forEach(card => {
                        card.style.display = (filter === 'all' || card.getAttribute('data-topic') === filter) ? 'block' : 'none';
                    });
                });
            });
        });
    </script></body></html>
    """
    article_html_template = """... (文章页模板可以保持不变) ..."""
    
    articles_data = []; all_topics = set()
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        topic_name = topic_dir.name
        all_topics.add(topic_name)
        for md_file in topic_dir.glob("*.md"):
            try:
                with md_file.open('r', encoding='utf-8') as f: content_lines = f.readlines()
                title = content_lines[1].split(': ', 1)[1].strip()
                journal = content_lines[2].split(': ', 1)[1].strip()
                content = "".join(content_lines[4:])
                article_filename = f"{md_file.stem}.html"
                article_path = WEBSITE_DIR / article_filename
                
                # ... (文章页生成逻辑不变)
                
                articles_data.append({"title": title, "url": article_filename, "topic": topic_name, "journal": journal})
            except Exception as e:
                logger.error(f"生成网页时处理文件 {md_file} 失败: {e}")
                continue
    
    articles_data.sort(key=lambda x: x['title'])
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data, topics=sorted(list(all_topics)))
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info(f"网站生成完成，共发现 {len(all_topics)} 个主题，{len(articles_data)} 篇文章。")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    discover_and_process_files()
    generate_website()
