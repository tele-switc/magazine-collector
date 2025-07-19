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
# 1. 配置区域
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

SOURCE_REPO_PATH = Path("source_repo")
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")
NON_ARTICLE_KEYWORDS = ['contents', 'index', 'editor', 'letter', 'subscription', 'classifieds', 'masthead', 'copyright', 'advertisement', 'the world this week', 'back issues']
# 我们不再需要写死的 MAGAZINES 列表了！

# ==============================================================================
# 2. 核心功能函数 (这部分逻辑已完善，无需修改)
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

def generate_title_from_content(text_content, all_texts_corpus):
    try:
        stop_words = list(stopwords.words('english')); stop_words.extend(['would', 'could', 'said', 'also', 'like', 'get', 'one', 'two', 'told', 'mr', 'ms'])
        vectorizer = TfidfVectorizer(max_features=20, stop_words=stop_words, ngram_range=(1, 2), token_pattern=r'(?u)\b[a-zA-Z-]{3,}\b')
        vectorizer.fit(all_texts_corpus)
        response = vectorizer.transform([text_content]); feature_names = vectorizer.get_feature_names_out()
        scores = response.toarray().flatten(); top_keyword_indices = scores.argsort()[-7:][::-1]
        good_keywords = []
        for i in top_keyword_indices:
            keyword = feature_names[i]
            if not keyword.strip(): continue
            pos_tag_list = nltk.pos_tag(nltk.word_tokenize(keyword))
            if not pos_tag_list: continue
            pos_tag = pos_tag_list[0][1]
            if pos_tag.startswith('NN') or pos_tag.startswith('JJ'): good_keywords.append(keyword)
        if len(good_keywords) < 3: return nltk.sent_tokenize(text_content)[0]
        title = ' '.join(word.capitalize() for word in good_keywords[:4]); return title
    except Exception as e: logger.error(f"AI生成标题失败: {e}"); return nltk.sent_tokenize(text_content)[0]

def discover_and_process_magazines():
    """【自主探索模块】不再依赖固定列表，而是自动发现所有杂志文件夹。"""
    if not SOURCE_REPO_PATH.is_dir(): logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!"); return
    
    all_article_contents = []; magazine_contents = {}
    
    # 步骤1: 侦察兵出动，扫描所有文件夹
    for source_folder in SOURCE_REPO_PATH.iterdir():
        if source_folder.is_dir() and not source_folder.name.startswith('.'): # 忽略隐藏文件夹
            magazine_name_match = re.match(r'\d+_(.+)', source_folder.name) # 从 "01_economist" 提取 "economist"
            if not magazine_name_match: continue
            
            magazine_name = magazine_name_match.group(1).replace('_', ' ')
            logger.info(f"=== 发现杂志文件夹: {source_folder.name}, 解析为: {magazine_name} ===")

            # 步骤2: 为发现的每个杂志，收集所有文章内容
            for file_path in source_folder.glob('*.epub'):
                if file_path.stem not in magazine_contents:
                    logger.info(f"  -> 读取: {file_path.name}")
                    full_text = extract_text_from_epub(str(file_path))
                    if full_text:
                        magazine_contents[file_path.stem] = split_text_into_articles(full_text)
                        all_article_contents.extend(magazine_contents.get(file_path.stem, []))

    # 步骤3: 使用全局语料库，处理并保存所有文章
    processed_fingerprints = set()
    for stem, articles_in_magazine in magazine_contents.items():
        magazine_name_match = re.match(r'\d+_(.+)', stem)
        if not magazine_name_match:
            # 兼容没有编号的旧文件名
            magazine_name_match = re.match(r'([a-zA-Z]+)', stem)
        
        magazine_name = magazine_name_match.group(1).replace('_', ' ') if magazine_name_match else "unknown"

        # 动态创建主题文件夹
        topic_dir = ARTICLES_DIR / magazine_name
        topic_dir.mkdir(exist_ok=True)
        
        for i, article_content in enumerate(articles_in_magazine):
            fingerprint = article_content.strip()[:60]
            if fingerprint in processed_fingerprints: continue
            processed_fingerprints.add(fingerprint)
            cleaned_content = clean_article_text(article_content)
            if len(cleaned_content.split()) < 200: continue
            
            title = generate_title_from_content(cleaned_content, all_article_contents)
            author_match = re.search(r'By\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', cleaned_content)
            author = author_match.group(1) if author_match else "N/A"
            
            output_path = topic_dir / f"{stem}_art_{i+1}.md"
            save_article(output_path, cleaned_content, title, author)

def extract_text_from_epub(epub_path):
    try: book = epub.read_epub(epub_path); return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e: logger.error(f"提取EPUB失败 {epub_path}: {e}"); return ""

def save_article(output_path, text_content, title, author):
    word_count = len(text_content.split()); reading_time = f"~{round(word_count / 200)} min"
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nauthor: {author}\nwords: {word_count}\nreading_time: {reading_time}\n---\n\n{text_content}")
    logger.info(f"已保存: {output_path.name}")

def generate_website():
    """【动态主题博物馆版】"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --accent-color: #33a0ff; --bg-color: #0d1117; --card-color: #161b22; --text-color: #c9d1d9; --secondary-text: #8b949e; --border-color: rgba(139, 148, 158, 0.2); }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 4rem 2rem; }
        .container { max-width: 1320px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 3rem; }
        .header h1 { font-size: 5rem; font-weight: 700; color: #fff; margin: 0; }
        .filters { text-align: center; margin-bottom: 4rem; }
        .filter-btn { background: none; border: 1px solid var(--border-color); color: var(--secondary-text); padding: 0.6rem 1.2rem; margin: 0.3rem; border-radius: 99px; cursor: pointer; transition: all 0.2s ease; }
        .filter-btn.active { background-color: var(--accent-color); color: #fff; border-color: var(--accent-color); }
        .grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
        .card { background: var(--card-color); border: 1px solid var(--border-color); border-radius: 16px; transition: all 0.3s ease; display: none; /* Default hidden */ }
        .card.visible { display: flex; flex-direction: column; }
    </style></head>
    <body><div class="container">
        <div class="header"><h1>AI Curated Journals</h1></div>
        <div class="filters">
            <button class="filter-btn active" data-filter="all">All Journals</button>
            {% for journal in journals %}
            <button class="filter-btn" data-filter="{{ journal }}">{{ journal | replace('_', ' ') | title }}</button>
            {% endfor %}
        </div>
        <div class="grid">
        {% for article in articles %}
            <div class="card visible" data-journal="{{ article.journal }}">
                <div style="padding:2rem;flex-grow:1;display:flex;flex-direction:column;">
                    <h5 style="font-size:1.5rem;color:#fff;">{{ article.title }}</h5>
                    <div style="margin-top:auto;padding-top:1.5rem;border-top:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:0.85rem;color:var(--secondary-text);">By {{ article.author }}</span>
                        <a href="{{ article.url }}" style="color:var(--accent-color);text-decoration:none;">Read →</a>
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
                        if (filter === 'all' || card.getAttribute('data-journal') === filter) {
                            card.classList.add('visible');
                        } else {
                            card.classList.remove('visible');
                        }
                    });
                });
            });
        });
    </script></body></html>
    """
    article_html_template = """... (文章页模板保持不变) ..."""
    
    articles_data = []; all_journals = set()
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        journal_name = topic_dir.name
        all_journals.add(journal_name)
        for md_file in topic_dir.glob("*.md"):
            try:
                # ... (读取 md 文件的逻辑保持不变)
                articles_data.append({
                    "title": title, "preview": preview, "url": article_filename,
                    "journal": journal_name, # 【新增】为每篇文章打上“杂志”标签
                    "author": author
                })
            except Exception as e: logger.error(f"生成网页时处理文件 {md_file} 失败: {e}"); continue
    
    articles_data.sort(key=lambda x: x['title'])
    template = jinja2.Template(index_template_str)
    # 把发现的所有杂志列表也传递给模板
    index_html = template.render(articles=articles_data, journals=sorted(list(all_journals)))
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info(f"网站生成完成，共发现 {len(all_journals)} 种杂志，{len(articles_data)} 篇文章。")

# ... (主程序入口保持不变)
