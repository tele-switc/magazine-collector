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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

SOURCE_REPO_PATH = Path("source_repo").resolve() # 使用绝对路径以增强在CI环境中的稳定性
ARTICLES_DIR = Path("articles").resolve()
WEBSITE_DIR = Path("docs").resolve()
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
    logger.info(f"文章目录: {ARTICLES_DIR}")
    logger.info(f"网站目录: {WEBSITE_DIR}")
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def process_epub_file(epub_path):
    """深入解析单个EPUB文件，进行文章质检。"""
    logger.info(f"  正在解析EPUB文件: {epub_path.name}")
    articles = []
    try:
        book = epub.read_epub(str(epub_path))
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        
        for i, item in enumerate(items):
            soup = BeautifulSoup(item.get_content(), 'lxml')
            for tag in soup(['script', 'style', 'a', 'img', 'nav', 'header', 'footer', 'figure', 'figcaption']):
                tag.decompose()
            
            text_content = soup.get_text(separator='\n', strip=True)
            text_content = re.sub(r'\n\s*\n+', '\n\n', text_content).strip()

            word_count = len(text_content.split())
            if word_count < 150:
                continue

            header_text = text_content[:500].lower()
            if any(keyword in header_text for keyword in NON_ARTICLE_KEYWORDS):
                continue

            if text_content.count('\n\n') < 3:
                continue

            articles.append(text_content)
    except Exception as e:
        logger.error(f"  解析EPUB文件 {epub_path.name} 时出错: {e}")
    
    logger.info(f"  从 {epub_path.name} 提取了 {len(articles)} 篇合格文章。")
    return articles

def generate_title_from_content(text_content, all_texts_corpus):
    """使用TF-IDF算法从文章内容中智能生成一个简洁的标题。"""
    try:
        stop_words = list(stopwords.words('english'))
        stop_words.extend(['would', 'could', 'said', 'also', 'like', 'get', 'one', 'two', 'told', 'mr', 'ms', 'mrs', 'year', 'week', 'day'])
        vectorizer = TfidfVectorizer(max_features=20, stop_words=stop_words, ngram_range=(1, 3), token_pattern=r'(?u)\b[a-zA-Z-]{4,}\b')
        vectorizer.fit(all_texts_corpus)
        response = vectorizer.transform([text_content])
        feature_names = vectorizer.get_feature_names_out()
        
        if not feature_names.any(): return nltk.sent_tokenize(text_content)[0].strip()

        scores = response.toarray().flatten()
        top_keyword_indices = scores.argsort()[-8:][::-1]
        
        good_keywords = [feature_names[i] for i in top_keyword_indices if feature_names[i].strip()]
        
        if len(good_keywords) < 3: return nltk.sent_tokenize(text_content)[0].strip()
        title = ' '.join(word.capitalize() for word in good_keywords[:5])
        return title
    except Exception as e:
        logger.error(f"AI生成标题失败: {e}")
        return nltk.sent_tokenize(text_content)[0].strip() if text_content else "Untitled Article"

def save_article(output_path, text_content, title, author):
    """保存文章为带有Frontmatter的Markdown文件。"""
    word_count = len(text_content.split())
    reading_time = f"~{max(1, round(word_count / 230))} min read"
    safe_title = title.replace('"', "'") 
    frontmatter = f"""---
title: "{safe_title}"
author: "{author}"
words: {word_count}
reading_time: "{reading_time}"
---

"""
    with output_path.open("w", encoding="utf-8") as f:
        f.write(frontmatter + text_content)

### [诊断强化] 增强日志和路径检查 ###
def process_all_magazines():
    """主处理流程：遍历所有配置的杂志，提取文章并保存。"""
    logger.info("--- 开始处理所有杂志 ---")
    
    # 诊断：检查源仓库目录是否存在
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"致命错误: 源仓库目录 '{SOURCE_REPO_PATH}' 未找到！")
        logger.info("请检查 'git clone' 步骤是否成功以及路径是否正确。")
        # 诊断：列出当前目录内容帮助调试
        logger.info(f"当前工作目录内容: {list(Path('.').iterdir())}")
        return

    logger.info(f"成功定位源仓库目录: {SOURCE_REPO_PATH}")
    total_articles_extracted = 0
    
    for magazine_name, info in MAGAZINES.items():
        logger.info(f"\n>>> 正在处理杂志: {magazine_name}")
        source_folder = SOURCE_REPO_PATH / info["folder"]
        
        # 诊断：检查特定杂志的目录是否存在
        if not source_folder.is_dir():
            logger.warning(f"  [跳过] 未找到目录: {source_folder}")
            continue
        
        logger.info(f"  检查目录: {source_folder}")
        
        # 诊断：查找并列出所有 EPUB 文件
        epub_files = list(source_folder.glob('*.epub'))
        logger.info(f"  在该目录中找到 {len(epub_files)} 个 .epub 文件。")
        
        if not epub_files:
            logger.warning(f"  [跳过] 在 {source_folder} 中未找到任何 .epub 文件。")
            continue
        
        # 按修改时间排序，处理最新的一期
        latest_file_path = sorted(epub_files, key=os.path.getmtime, reverse=True)[0]
        
        articles_from_epub = process_epub_file(latest_file_path)
        if not articles_from_epub:
            continue

        corpus = articles_from_epub[:]
        topic = info['topic']
        stem = f"{magazine_name.replace(' ', '_')}_{latest_file_path.stem.replace(' ', '_')}"
        
        for i, article_content in enumerate(articles_from_epub):
            title = generate_title_from_content(article_content, corpus)
            author_match = re.search(r'(?:By|by|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z\'-]+){1,3})', article_content[:600])
            author = author_match.group(1).strip() if author_match else "Source"
            
            output_path = ARTICLES_DIR / topic / f"{stem}_art{i+1}.md"
            save_article(output_path, article_content, title, author)
            total_articles_extracted += 1

    logger.info(f"\n--- 所有杂志处理完毕。共提取了 {total_articles_extracted} 篇新文章。 ---")

def generate_website():
    """使用Jinja2模板从Markdown文件生成静态HTML网站。"""
    logger.info("--- 开始生成网站 ---")
    WEBSITE_DIR.mkdir(exist_ok=True)
    
    ### [视觉升级] 全新“蓝色粒子星云”动态背景 ###
    shared_style_and_script = """
<style>
    body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: #02040a; /* 更深邃的背景 */
        color: #c9d1d9; margin: 0; padding: 0; overflow-x: hidden;
    }
    #particle-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; }
</style>
<canvas id="particle-canvas"></canvas>
<script>
    document.addEventListener('DOMContentLoaded', () => {
        const canvas = document.getElementById('particle-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        let particles = [];
        const particleCount = window.innerWidth > 768 ? 150 : 60; // 更多粒子
        const mouse = { x: null, y: null, radius: 120 };

        const resizeCanvas = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();

        window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
        window.addEventListener('mouseout', () => { mouse.x = null; mouse.y = null; });

        class Particle {
            constructor() {
                this.x = Math.random() * canvas.width;
                this.y = Math.random() * canvas.height;
                this.size = Math.random() * 1.5 + 0.5; // 更小的粒子
                this.speedX = (Math.random() - 0.5) * 0.5;
                this.speedY = (Math.random() - 0.5) * 0.5;
                this.opacity = Math.random() * 0.5 + 0.3; // 随机透明度
            }
            update() {
                if (this.x > canvas.width || this.x < 0) this.speedX *= -1;
                if (this.y > canvas.height || this.y < 0) this.speedY *= -1;
                this.x += this.speedX;
                this.y += this.speedY;

                if (mouse.x != null) {
                    const dx = mouse.x - this.x;
                    const dy = mouse.y - this.y;
                    const distance = Math.hypot(dx, dy);
                    if (distance < mouse.radius) {
                        const force = (mouse.radius - distance) / mouse.radius;
                        this.x -= (dx / distance) * force * 2;
                        this.y -= (dy / distance) * force * 2;
                    }
                }
            }
            draw() {
                ctx.fillStyle = `rgba(0, 191, 255, ${this.opacity})`; // 纯科技蓝
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        function init() {
            particles = [];
            for (let i = 0; i < particleCount; i++) particles.push(new Particle());
        }

        function connect() {
            for (let a = 0; a < particles.length; a++) {
                for (let b = a; b < particles.length; b++) {
                    const distance = Math.hypot(particles[a].x - particles[b].x, particles[a].y - particles[b].y);
                    if (distance < 100) {
                        const opacity = 1 - distance / 100;
                        ctx.strokeStyle = `rgba(0, 191, 255, ${opacity * 0.2})`; // 更透明的连接线
                        ctx.lineWidth = 0.5;
                        ctx.beginPath();
                        ctx.moveTo(particles[a].x, particles[a].y);
                        ctx.lineTo(particles[b].x, particles[b].y);
                        ctx.stroke();
                    }
                }
            }
        }
        function animate() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            particles.forEach(p => { p.update(); p.draw(); });
            connect();
            requestAnimationFrame(animate);
        }
        init(); animate();
    });
</script>
"""

    index_template_str = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Curated Journals | Cosmos Engine</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
<style>
    .container { max-width: 1400px; margin: 0 auto; padding: 4rem 2rem; position: relative; z-index: 1; }
    h1 { font-size: clamp(2.5rem, 6vw, 4.5rem); text-align: center; margin-bottom: 5rem; color: #fff; text-shadow: 0 0 25px rgba(0, 191, 255, 0.5); letter-spacing: -0.02em; }
    .grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); }
    .card { backdrop-filter: blur(12px) saturate(150%); -webkit-backdrop-filter: blur(12px) saturate(150%); background: rgba(17, 25, 40, 0.7); border-radius: 16px; border: 1px solid rgba(0, 191, 255, 0.15); padding: 1.5rem 2rem; transition: all 0.3s ease; display: flex; flex-direction: column; }
    .card:hover { transform: translateY(-8px); box-shadow: 0 10px 30px rgba(0,0,0,0.25); border-color: rgba(0, 191, 255, 0.4); }
    .card-title { font-size: 1.3rem; font-weight: 500; line-height: 1.4; color: #f0f6fc; margin: 0 0 1rem 0; flex-grow: 1; }
    .card-meta { color: #8b949e; font-size: 0.85rem; }
    .card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid rgba(0, 191, 255, 0.1); }
    .read-link { color:#58a6ff; text-decoration:none; font-weight: 500; font-size: 0.9rem; } .read-link:hover { color: #80bfff; }
    .no-articles { text-align:center; padding:5rem 2rem; backdrop-filter: blur(10px); background: rgba(17, 25, 40, 0.7); border-radius:16px; border: 1px solid rgba(0, 191, 255, 0.15); }
</style></head><body>""" + shared_style_and_script + """<div class="container"><h1>AI Curated Journals</h1><div class="grid">
{% for article in articles %}
<div class="card">
    <div>
        <h3 class="card-title">{{ article.title }}</h3>
        <p class="card-meta">{{ article.magazine }} · {{ article.reading_time }}</p>
    </div>
    <div class="card-footer"><span class="card-meta">By {{ article.author }}</span><a href="{{ article.url }}" class="read-link">Read Article →</a></div>
</div>
{% endfor %}
</div>{% if not articles %}<div class="no-articles"><h2>No Articles Found</h2><p>The Cosmos Engine ran successfully, but no new article files were found in the source repository during this cycle.</p></div>{% endif %}
</div></body></html>"""

    article_html_template = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<style>
    .container { max-width: 720px; margin: 6rem auto; padding: clamp(2rem, 5vw, 4rem); backdrop-filter: blur(12px) saturate(180%); -webkit-backdrop-filter: blur(12px) saturate(180%); background-color: rgba(17, 25, 40, 0.8); border-radius: 16px; border: 1px solid rgba(0, 191, 255, 0.15); position: relative; z-index: 1; }
    .back-link { font-family: 'Inter', sans-serif; display: inline-block; margin-bottom: 3rem; text-decoration: none; color: #8892b0; transition: color 0.3s; } .back-link:hover { color: #58a6ff; }
    h1 { font-family: 'Inter', sans-serif; font-size: clamp(2rem, 6vw, 3.2rem); line-height: 1.2; color: #fff; margin:0; }
    .article-meta { font-family: 'Inter', sans-serif; color: #8892b0; margin: 1.5rem 0 3rem 0; border-bottom: 1px solid rgba(0, 191, 255, 0.1); padding-bottom: 2rem; font-size: 0.9rem; }
    .article-body { font-family: 'Lora', serif; font-size: 1.1rem; line-height: 1.9; color: #c9d1d9; }
    .article-body p { margin: 0 0 1.5em 0; } .article-body h2, .article-body h3 { font-family: 'Inter', sans-serif; color: #e6edf3; }
</style></head><body>""" + shared_style_and_script + """<div class="container"><a href="index.html" class="back-link">← Back to Journal List</a><h1>{{ title }}</h1>
<p class="article-meta">By {{ author }} · From {{ magazine }} · {{ reading_time }}</p>
<div class="article-body">{{ content }}</div></div></body></html>"""

    articles_data = []
    md_files = glob.glob(str(ARTICLES_DIR / '**/*.md'), recursive=True)
    logger.info(f"找到 {len(md_files)} 个已处理的 Markdown 文件用于生成网页。")

    for md_file_path in md_files:
        md_file = Path(md_file_path)
        try:
            with md_file.open('r', encoding='utf-8') as f: content_with_frontmatter = f.read()
            match = re.match(r'---\s*(.*?)\s*---\s*(.*)', content_with_frontmatter, re.DOTALL)
            if not match: continue
            frontmatter, content = match.groups()
            
            def get_meta(key, text):
                m = re.search(fr'{key}:\s*"?(.+?)"?\s*\n', text)
                return m.group(1).strip() if m else "Unknown"

            title = get_meta('title', frontmatter)
            author = get_meta('author', frontmatter)
            reading_time = get_meta('reading_time', frontmatter)
            magazine_name_raw = md_file.name.split('_')[0]
            magazine = ' '.join(word.capitalize() for word in magazine_name_raw.split('-'))

            article_filename, article_path = f"{md_file.stem}.html", WEBSITE_DIR / f"{md_file.stem}.html"
            article_template = jinja2.Template(article_html_template)
            article_html = article_template.render(title=title, content=markdown2.markdown(content), author=author, magazine=magazine, reading_time=reading_time)
            article_path.write_text(article_html, encoding='utf-8')
            
            articles_data.append({"title": title, "url": article_filename, "magazine": magazine, "author": author, "reading_time": reading_time})
        except Exception as e:
            logger.error(f"生成网页时处理文件 {md_file} 失败: {e}")

    articles_data.sort(key=lambda x: (x['magazine'], x['title']))
    index_template = jinja2.Template(index_template_str)
    (WEBSITE_DIR / "index.html").write_text(index_template.render(articles=articles_data), encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()

    if articles_data:
        logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。")
    else:
        logger.warning("网站生成完成，但没有找到任何文章。请检查上游的文章提取日志。")
    logger.info("--- 网站生成结束 ---")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
