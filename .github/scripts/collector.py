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
import glob

# ==============================================================================
# 1. 配置和初始化
# ==============================================================================
# 配置日志记录，使其在GitHub Actions中更易读
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

# 在CI环境中，路径解析需要格外小心
BASE_DIR = Path('.').resolve()
SOURCE_REPO_PATH = BASE_DIR / "source_repo"
ARTICLES_DIR = BASE_DIR / "articles"
WEBSITE_DIR = BASE_DIR / "docs"

NON_ARTICLE_KEYWORDS = [
    'contents', 'index', 'editor', 'letter', 'subscription', 'classifieds', 
    'masthead', 'copyright', 'advertisement', 'the world this week', 
    'back issues', 'contributors', 'about the author'
]

MAGAZINES = {
    "The Economist": {"folder": "The Economist", "topic": "world_affairs"},
    "Wired": {"folder": "Wired", "topic": "technology"},
    "The Atlantic": {"folder": "The Atlantic", "topic": "world_affairs"}
}

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================
def setup_directories():
    """创建所有必需的目录。"""
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    logger.info(f"文章目录已确认: {ARTICLES_DIR}")
    logger.info(f"网站目录已确认: {WEBSITE_DIR}")
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def process_epub_file(epub_path):
    """(逻辑不变) 深入解析单个EPUB文件，进行文章质检。"""
    articles = []
    try:
        book = epub.read_epub(str(epub_path))
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        
        for i, item in enumerate(items):
            soup = BeautifulSoup(item.get_content(), 'lxml')
            for tag in soup(['script', 'style', 'a', 'img', 'nav', 'header', 'footer', 'figure', 'figcaption']):
                tag.decompose()
            text_content = re.sub(r'\n\s*\n+', '\n\n', soup.get_text(separator='\n', strip=True)).strip()
            if len(text_content.split()) < 150: continue
            if any(keyword in text_content[:500].lower() for keyword in NON_ARTICLE_KEYWORDS): continue
            if text_content.count('\n\n') < 3: continue
            articles.append(text_content)
    except Exception as e:
        logger.error(f"  解析EPUB {epub_path.name} 时出错: {e}", exc_info=True)
    return articles

def generate_title_from_content(text_content, all_texts_corpus):
    """(逻辑不变) 使用TF-IDF生成标题。"""
    try:
        stop_words = list(stopwords.words('english'))
        stop_words.extend(['would', 'could', 'said', 'also', 'like', 'get', 'one', 'two', 'told', 'mr', 'ms', 'mrs', 'year'])
        vectorizer = TfidfVectorizer(max_features=20, stop_words=stop_words, ngram_range=(1, 3), token_pattern=r'(?u)\b[a-zA-Z-]{4,}\b')
        vectorizer.fit(all_texts_corpus)
        response = vectorizer.transform([text_content])
        feature_names = vectorizer.get_feature_names_out()
        if not feature_names.any(): return nltk.sent_tokenize(text_content)[0].strip()
        scores = response.toarray().flatten()
        top_keyword_indices = scores.argsort()[-8:][::-1]
        good_keywords = [feature_names[i] for i in top_keyword_indices if feature_names[i].strip()]
        if len(good_keywords) < 3: return nltk.sent_tokenize(text_content)[0].strip()
        return ' '.join(word.capitalize() for word in good_keywords[:5])
    except Exception:
        return nltk.sent_tokenize(text_content)[0].strip() if text_content else "Untitled Article"

def save_article(output_path, text_content, title, author):
    """(逻辑不变) 保存文章为Markdown。"""
    word_count = len(text_content.split())
    reading_time = f"~{max(1, round(word_count / 230))} min read"
    safe_title = title.replace('"', "'") 
    frontmatter = f'---\ntitle: "{safe_title}"\nauthor: "{author}"\nwords: {word_count}\nreading_time: "{reading_time}"\n---\n\n'
    output_path.write_text(frontmatter + text_content, encoding="utf-8")

### [DIAGNOSTIC OVERHAUL] 使用 os.walk 进行终极文件查找和诊断 ###
def process_all_magazines():
    """主处理流程，包含强大的诊断功能。"""
    logger.info("--- 开始文章提取流程 (诊断模式) ---")
    logger.info(f"当前工作目录: {Path.cwd()}")
    logger.info(f"期望的源仓库路径: {SOURCE_REPO_PATH}")

    # 终极诊断：使用os.walk遍历整个source_repo目录，打印所有找到的文件
    found_epubs = []
    if SOURCE_REPO_PATH.is_dir():
        logger.info(f"成功进入 '{SOURCE_REPO_PATH}'。开始扫描EPUB文件...")
        for root, dirs, files in os.walk(SOURCE_REPO_PATH):
            for file in files:
                if file.endswith('.epub'):
                    full_path = Path(root) / file
                    found_epubs.append(full_path)
                    logger.info(f"  [发现EPUB] {full_path.relative_to(SOURCE_REPO_PATH)}")
    else:
        logger.error(f"致命错误: 目录 '{SOURCE_REPO_PATH}' 不存在！")
        logger.info("将扫描整个工作区以查找 'source_repo'...")
        for root, dirs, files in os.walk(BASE_DIR):
            logger.info(f"扫描中... 目录: {root}, 包含子目录: {dirs}")
        return

    if not found_epubs:
        logger.warning("扫描完成，但在源仓库中未找到任何 .epub 文件。流程终止。")
        return

    # 按杂志对EPUB进行分组
    magazine_epubs = {name: [] for name in MAGAZINES}
    for path in found_epubs:
        for name, info in MAGAZINES.items():
            if info["folder"] in path.parts:
                magazine_epubs[name].append(path)
                break
    
    total_articles_extracted = 0
    for magazine_name, epub_paths in magazine_epubs.items():
        if not epub_paths:
            logger.info(f"杂志 '{magazine_name}' 没有找到对应的EPUB文件，跳过。")
            continue
        
        logger.info(f"\n>>> 处理杂志: {magazine_name} (找到 {len(epub_paths)} 个EPUB)")
        # 只处理最新的一个文件（基于文件名中的日期或修改时间）
        latest_file_path = sorted(epub_paths, reverse=True)[0]
        logger.info(f"  选择最新文件进行处理: {latest_file_path.name}")
        
        articles_from_epub = process_epub_file(latest_file_path)
        if not articles_from_epub:
            logger.warning(f"  未能从 {latest_file_path.name} 提取任何合格文章。")
            continue

        corpus = articles_from_epub[:]
        topic = MAGAZINES[magazine_name]['topic']
        stem = f"{magazine_name.replace(' ', '_')}_{latest_file_path.stem.replace(' ', '_')}"
        
        for i, article_content in enumerate(articles_from_epub):
            title = generate_title_from_content(article_content, corpus)
            author_match = re.search(r'(?:By|by|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z\'-]+){1,3})', article_content[:600])
            author = author_match.group(1).strip() if author_match else "Source"
            output_path = ARTICLES_DIR / topic / f"{stem}_art{i+1}.md"
            save_article(output_path, article_content, title, author)
            total_articles_extracted += 1
            logger.info(f"  已保存文章: {output_path.name}")

    logger.info(f"\n--- 文章提取流程结束。共提取了 {total_articles_extracted} 篇新文章。 ---")


def generate_website():
    """生成带有全新视觉效果的静态网站。"""
    logger.info("--- 开始生成网站 (视觉 v2.0) ---")
    WEBSITE_DIR.mkdir(exist_ok=True)
    
    ### [VISUAL OVERHAUL 2.0]: 蓝色粒子星云 + 动态闪电 ###
    shared_style_and_script = """
<style>
    body { font-family: 'Inter', sans-serif; background-color: #02040a; color: #e6edf3; margin: 0; padding: 0; overflow-x: hidden; }
    #dynamic-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; }
</style>
<canvas id="dynamic-canvas"></canvas>
<script>
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('dynamic-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let particles = [], meteors = [];
    const particleCount = window.innerWidth > 768 ? 120 : 50;
    const mouse = { x: null, y: null, radius: 100 };

    const resizeCanvas = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
    window.addEventListener('mouseout', () => { mouse.x = null; mouse.y = null; });

    class Particle {
        constructor() { this.x = Math.random() * canvas.width; this.y = Math.random() * canvas.height; this.size = Math.random() * 1.5 + 0.5; this.speedX = (Math.random() - 0.5) * 0.4; this.speedY = (Math.random() - 0.5) * 0.4; this.opacity = Math.random() * 0.5 + 0.2; }
        update() { if (this.x < 0 || this.x > canvas.width) this.speedX *= -1; if (this.y < 0 || this.y > canvas.height) this.speedY *= -1; this.x += this.speedX; this.y += this.speedY; if (mouse.x) { const dx = mouse.x - this.x; const dy = mouse.y - this.y; const dist = Math.hypot(dx, dy); if (dist < mouse.radius) { const force = (mouse.radius - dist) / mouse.radius; this.x -= dx / dist * force; this.y -= dy / dist * force; } } }
        draw() { ctx.fillStyle = `rgba(0, 191, 255, ${this.opacity})`; ctx.beginPath(); ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2); ctx.fill(); }
    }

    class Meteor {
        constructor() { this.reset(); }
        reset() { this.x = Math.random() * canvas.width + 100; this.y = -10; this.len = Math.random() * 80 + 10; this.speed = Math.random() * 8 + 6; this.size = Math.random() * 1 + 0.5; this.active = true; }
        update() { if (this.active) { this.x -= this.speed; this.y += this.speed; if (this.x < -this.len || this.y > canvas.height + this.len) this.active = false; } }
        draw() { if (this.active) { ctx.strokeStyle = '#00BFFF'; ctx.lineWidth = this.size; ctx.beginPath(); ctx.moveTo(this.x, this.y); ctx.lineTo(this.x - this.len, this.y + this.len); ctx.stroke(); } }
    }

    function init() { for (let i = 0; i < particleCount; i++) particles.push(new Particle()); }
    function handleMeteors() { if (meteors.length < 3 && Math.random() > 0.99) meteors.push(new Meteor()); meteors = meteors.filter(m => m.active); }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(p => { p.update(); p.draw(); });
        handleMeteors();
        meteors.forEach(m => { m.update(); m.draw(); });
        requestAnimationFrame(animate);
    }
    init(); animate();
});
</script>
"""

    ### [VISUAL OVERHAUL 2.0]: 液态玻璃 (Glassmorphism) 风格 ###
    index_template_str = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Curated Journals | Cosmos Engine</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
<style>
    .container { max-width: 1400px; margin: 0 auto; padding: 4rem 2rem; position: relative; z-index: 1; }
    h1 { font-size: clamp(2.5rem, 6vw, 4.5rem); text-align: center; margin-bottom: 5rem; color: #fff; text-shadow: 0 0 25px rgba(0, 191, 255, 0.5); }
    .grid { display: grid; gap: 2.5rem; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); }
    .card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
        border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 2rem; transition: all 0.3s ease; display: flex; flex-direction: column;
        box-shadow: 0 8px 32px 0 rgba(2, 4, 10, 0.2);
    }
    .card:hover { transform: translateY(-10px) scale(1.02); border-color: rgba(0, 191, 255, 0.5); box-shadow: 0 12px 40px 0 rgba(0, 127, 255, 0.2); }
    .card-title { font-size: 1.3rem; font-weight: 500; line-height: 1.4; color: #f0f6fc; margin: 0 0 1rem 0; flex-grow: 1; }
    .card-meta, .card-footer-author { color: #a3b3c6; font-size: 0.85rem; }
    .card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid rgba(255, 255, 255, 0.1); }
    .read-link { color:#58a6ff; text-decoration:none; font-weight: 500; font-size: 0.9rem; } .read-link:hover { color: #80bfff; }
    .no-articles { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.1); text-align:center; padding:5rem 2rem; }
</style></head><body>""" + shared_style_and_script + """<div class="container"><h1>AI Curated Journals</h1><div class="grid">
{% for article in articles %}
<div class="card">
    <div>
        <h3 class="card-title">{{ article.title }}</h3>
        <p class="card-meta">{{ article.magazine }} · {{ article.reading_time }}</p>
    </div>
    <div class="card-footer"><span class="card-footer-author">By {{ article.author }}</span><a href="{{ article.url }}" class="read-link">Read Article →</a></div>
</div>
{% endfor %}
</div>{% if not articles %}<div class="no-articles"><h2>No Articles Found</h2><p>The Cosmos Engine ran successfully, but no EPUB files were processed in this cycle. Please check the source repository.</p></div>{% endif %}
</div></body></html>"""

    article_html_template = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<style>
    .article-container {
        max-width: 720px; margin: 6rem auto; padding: clamp(2rem, 5vw, 4rem);
        background: rgba(255, 255, 255, 0.08); backdrop-filter: blur(25px); -webkit-backdrop-filter: blur(25px);
        border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.12);
        position: relative; z-index: 1; box-shadow: 0 8px 32px 0 rgba(2, 4, 10, 0.25);
    }
    .back-link { font-family: 'Inter', sans-serif; display: inline-block; margin-bottom: 3rem; text-decoration: none; color: #a3b3c6; transition: color 0.3s; } .back-link:hover { color: #58a6ff; }
    h1 { font-family: 'Inter', sans-serif; font-size: clamp(2rem, 6vw, 3.2rem); line-height: 1.2; color: #fff; margin:0; }
    .article-meta { font-family: 'Inter', sans-serif; color: #a3b3c6; margin: 1.5rem 0 3rem 0; border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 2rem; font-size: 0.9rem; }
    .article-body { font-family: 'Lora', serif; font-size: 1.1rem; line-height: 1.9; color: #d1d9e0; }
    .article-body p { margin: 0 0 1.5em 0; } .article-body h2, .article-body h3 { font-family: 'Inter', sans-serif; color: #e6edf3; }
</style></head><body>""" + shared_style_and_script + """<div class="article-container"><a href="index.html" class="back-link">← Back to Journal List</a><h1>{{ title }}</h1>
<p class="article-meta">By {{ author }} · From {{ magazine }} · {{ reading_time }}</p>
<div class="article-body">{{ content }}</div></div></body></html>"""

    # ... (模板渲染逻辑保持不变)
    articles_data = []
    md_files = glob.glob(str(ARTICLES_DIR / '**/*.md'), recursive=True)
    logger.info(f"找到 {len(md_files)} 个 Markdown 文件用于生成网页。")
    for md_file_path in md_files:
        md_file = Path(md_file_path)
        try:
            content_with_frontmatter = md_file.read_text(encoding='utf-8')
            match = re.match(r'---\s*(.*?)\s*---\s*(.*)', content_with_frontmatter, re.DOTALL)
            if not match: continue
            frontmatter, content = match.groups()
            def get_meta(key, text):
                m = re.search(fr'{key}:\s*"?(.+?)"?\s*\n', text)
                return m.group(1).strip() if m else "Unknown"
            title, author, reading_time = get_meta('title', frontmatter), get_meta('author', frontmatter), get_meta('reading_time', frontmatter)
            magazine = md_file.name.split('_')[0].replace('-', ' ').title()
            article_filename, article_path = f"{md_file.stem}.html", WEBSITE_DIR / f"{md_file.stem}.html"
            article_html = jinja2.Template(article_html_template).render(title=title, content=markdown2.markdown(content), author=author, magazine=magazine, reading_time=reading_time)
            article_path.write_text(article_html, encoding='utf-8')
            articles_data.append({"title": title, "url": article_filename, "magazine": magazine, "author": author, "reading_time": reading_time})
        except Exception as e:
            logger.error(f"生成网页 {md_file} 失败: {e}", exc_info=True)
    
    articles_data.sort(key=lambda x: (x['magazine'], x['title']))
    (WEBSITE_DIR / "index.html").write_text(jinja2.Template(index_template_str).render(articles=articles_data), encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info("--- 网站生成结束 ---")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
