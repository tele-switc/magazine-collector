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
from nltk.corpus import stopwords

# ==============================================================================
# 1. 配置和初始化
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

SOURCE_REPO_PATH = Path("source_repo_1") # 我们只使用这个可靠的源
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")
NON_ARTICLE_KEYWORDS = ['contents', 'index', 'editor', 'letter', 'subscription', 'classifieds', 'masthead', 'copyright', 'advertisement', 'the world this week', 'back issues']

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================

def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)

def clean_article_text(text):
    text = re.sub(r'[\w\.-]+@[\w.-]+\.\w+', '', text); text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'subscribe now|for more information|visit our website|follow us on', '', text, flags=re.IGNORECASE)
    return re.sub(r'\n\s*\n', '\n\n', text).strip()

def split_text_into_articles(text):
    ending_punctuations = ('.', '?', '!', '"', '”', '’'); articles = []
    for article_text in re.split(r'\n\s*\n\s*\n+', text):
        article_text = article_text.strip()
        if not article_text or not article_text.endswith(ending_punctuations): continue
        if sum(1 for keyword in NON_ARTICLE_KEYWORDS if keyword in article_text.lower()) > 1: continue
        if len(article_text.split()) < 250: continue
        articles.append(article_text)
    return articles

def extract_metadata(text_content):
    """【智能信息提取器】从文章内容中提取标题和作者。"""
    lines = text_content.strip().split('\n')
    title = "Untitled"
    author = "N/A"

    # 尝试提取标题
    for line in lines[:5]: # 通常标题在文章前5行
        line = line.strip()
        if 2 < len(line.split()) < 20 and not line.endswith('.') and line[0].isupper() and not line.isupper():
            title = line
            break
    if title == "Untitled":
        title = nltk.sent_tokenize(text_content)[0]

    # 尝试提取作者
    author_match = re.search(r'By\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text_content)
    if author_match:
        author = author_match.group(1)
        
    return title.strip(), author.strip()

def discover_and_process_magazines():
    """【最终版】自动发现、处理、并提取所有文章的元数据。"""
    if not SOURCE_REPO_PATH.is_dir(): logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!"); return
    
    # 动态发现所有杂志文件夹
    for source_folder in SOURCE_REPO_PATH.iterdir():
        if source_folder.is_dir() and not source_folder.name.startswith('.'):
            magazine_name_match = re.match(r'\d+_(.+)', source_folder.name)
            if not magazine_name_match: continue
            
            magazine_name = magazine_name_match.group(1).replace('_', ' ').title()
            logger.info(f"=== 发现杂志: {magazine_name} ===")

            topic_dir = ARTICLES_DIR / magazine_name
            topic_dir.mkdir(exist_ok=True)

            for file_path in source_folder.glob('*.epub'):
                check_path = topic_dir / f"{file_path.stem}_art_1.md"
                if check_path.exists(): continue

                logger.info(f"  -> 处理文件: {file_path.name}")
                full_text = extract_text_from_epub(str(file_path))
                if full_text:
                    articles_in_magazine = split_text_into_articles(full_text)
                    for i, article_content in enumerate(articles_in_magazine):
                        cleaned_content = clean_article_text(article_content)
                        if len(cleaned_content.split()) < 200: continue
                        
                        title, author = extract_metadata(cleaned_content)
                        
                        output_path = topic_dir / f"{file_path.stem}_art_{i+1}.md"
                        save_article(output_path, cleaned_content, title, author, magazine_name)

def extract_text_from_epub(epub_path):
    try: book = epub.read_epub(epub_path); return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e: logger.error(f"提取EPUB失败 {epub_path}: {e}"); return ""

def save_article(output_path, text_content, title, author, journal):
    word_count = len(text_content.split()); reading_time = f"~{round(word_count / 200)} min Read"
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nauthor: {author}\njournal: {journal}\nreading_time: {reading_time}\n---\n\n{text_content}")
    logger.info(f"已保存: {output_path.name}")

def generate_website():
    """【最终版】生成信息丰富的动态主题网站。"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --accent-color: #33a0ff; --bg-color: #0d1117; --card-color: #161b22; --text-color: #c9d1d9; --secondary-text: #8b949e; --border-color: rgba(139, 148, 158, 0.2); }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 4rem 2rem; }
        .container { max-width: 1320px; margin: 0 auto; } .header { text-align: center; margin-bottom: 3rem; }
        h1 { font-size: 5rem; font-weight: 700; color: #fff; } .filters { text-align: center; margin-bottom: 4rem; }
        .filter-btn { background: none; border: 1px solid var(--border-color); color: var(--secondary-text); padding: 0.6rem 1.2rem; margin: 0.3rem; border-radius: 99px; cursor: pointer; transition: all 0.2s ease; }
        .filter-btn.active { background-color: var(--accent-color); color: #fff; border-color: var(--accent-color); }
        .grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
        .card { background: var(--card-color); border: 1px solid var(--border-color); border-radius: 16px; transition: all 0.3s ease; display: none; }
        .card.visible { display: flex; flex-direction: column; }
        .card:hover { transform: translateY(-5px); border-color: var(--accent-color); }
        .card-content { padding: 2rem; flex-grow: 1; display: flex; flex-direction: column; }
        .card-title { font-size: 1.5rem; color: #fff; margin: 0 0 1.5rem 0; flex-grow: 1; }
        .card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: auto; padding-top: 1.5rem; border-top: 1px solid var(--border-color); }
    </style></head>
    <body><div class="container"><div class="header"><h1>Curated Journals</h1></div>
        <div class="filters">
            <button class="filter-btn active" data-filter="all">All Journals</button>
            {% for journal in journals %}
            <button class="filter-btn" data-filter="{{ journal }}">{{ journal }}</button>
            {% endfor %}
        </div>
        <div class="grid">
        {% for article in articles %}
            <div class="card visible" data-journal="{{ article.journal }}">
                <div class="card-content">
                    <h5 class="card-title">{{ article.title }}</h5>
                    <div class="card-footer">
                        <span style="font-size:0.85rem;color:var(--secondary-text);">By {{ article.author }} | {{ article.reading_time }}</span>
                        <a href="{{ article.url }}" style="color:var(--accent-color);text-decoration:none;">Read More →</a>
                    </div>
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
                        card.style.display = 'none'; // Reset display
                        if (filter === 'all' || card.getAttribute('data-journal') === filter) {
                            card.style.display = 'flex'; // Use flex for visible cards
                        }
                    });
                });
            });
            // Initially trigger the 'All' filter
            document.querySelector('[data-filter="all"]').click();
        });
    </script></body></html>
    """
    article_html_template = """... (文章页模板可以保持不变) ..."""
    
    articles_data = []; all_journals = set()
    for journal_dir in ARTICLES_DIR.iterdir():
        if not journal_dir.is_dir(): continue
        journal_name = journal_dir.name
        all_journals.add(journal_name)
        for md_file in journal_dir.glob("*.md"):
            try:
                with md_file.open('r', encoding='utf-8') as f: content_lines = f.readlines()
                title = content_lines[1].split(': ', 1)[1].strip()
                author = content_lines[2].split(': ', 1)[1].strip()
                journal = content_lines[3].split(': ', 1)[1].strip()
                reading_time = content_lines[4].split(': ', 1)[1].strip()
                content = "".join(content_lines[6:])
                
                # ... (文章页生成逻辑不变)
                
                articles_data.append({"title": title, "url": f"{md_file.stem}.html", "journal": journal, "author": author, "reading_time": reading_time})
            except Exception as e:
                logger.error(f"生成网页时处理文件 {md_file} 失败: {e}")
                continue
    
    articles_data.sort(key=lambda x: x.get('title', ''))
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data, journals=sorted(list(all_journals)))
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info(f"网站生成完成，共发现 {len(all_journals)} 种杂志，{len(articles_data)} 篇文章。")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    discover_and_process_magazines()
    generate_website()
