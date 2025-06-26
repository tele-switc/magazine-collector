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
else:
    logger.warning("NLTK_DATA environment variable not set. Using default NLTK paths.")

SOURCE_REPO_PATH = Path("source_repo")
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")
NON_ARTICLE_KEYWORDS = ['contents', 'index', 'editor', 'letter', 'subscription', 'classifieds', 'masthead', 'copyright', 'advertisement', 'the world this week', 'back issues', 'contributors', 'about the author']

MAGAZINES = {
    "The Economist": {"folder": "The Economist", "topic": "world_affairs"},
    "Wired": {"folder": "Wired", "topic": "technology"},
    "The Atlantic": {"folder": "The Atlantic", "topic": "world_affairs"}
}

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================
def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

### [COSMOS ENGINE FIX]: 全新、健壮的文章提取逻辑 ###
def process_epub_file(epub_path):
    """
    深入解析单个EPUB文件，将其中的每个子文档作为潜在文章进行质检。
    这是解决“无文章”问题的核心。
    """
    logger.info(f"正在深入解析: {epub_path.name}")
    articles = []
    try:
        book = epub.read_epub(str(epub_path))
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        
        for i, item in enumerate(items):
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            # 移除所有非文本元素，获取干净的文本
            for tag in soup(['script', 'style', 'a', 'img']):
                tag.decompose()
            
            text_content = soup.get_text(separator='\n', strip=True)
            text_content = re.sub(r'\n\s*\n', '\n\n', text_content).strip()

            # --- 文章质检流程 ---
            # 1. 长度检查
            if len(text_content.split()) < 250:
                # logger.debug(f"Item {i} failed length check.")
                continue

            # 2. 关键词过滤 (检查前300个字符)
            header_text = text_content[:300].lower()
            if any(keyword in header_text for keyword in NON_ARTICLE_KEYWORDS):
                # logger.debug(f"Item {i} failed keyword check.")
                continue

            # 3. 结构检查 (必须以标点符号结尾)
            if not text_content.endswith(('.', '?', '!', '"', '”', '’')):
                # logger.debug(f"Item {i} failed punctuation check.")
                continue
            
            logger.info(f"  -> 从EPUB子文档 {i} 成功提取一篇合格文章。")
            articles.append(text_content)
            
    except Exception as e:
        logger.error(f"解析EPUB文件 {epub_path.name} 时发生严重错误: {e}")
    
    return articles

def generate_title_from_content(text_content, all_texts_corpus):
    # (此函数逻辑保持不变, 依然强大)
    try:
        stop_words = list(stopwords.words('english'))
        stop_words.extend(['would', 'could', 'said', 'also', 'like', 'get', 'one', 'two', 'told', 'mr', 'ms', 'mrs'])
        vectorizer = TfidfVectorizer(max_features=20, stop_words=stop_words, ngram_range=(1, 3), token_pattern=r'(?u)\b[a-zA-Z-]{3,}\b')
        vectorizer.fit(all_texts_corpus)
        response = vectorizer.transform([text_content])
        feature_names = vectorizer.get_feature_names_out()
        scores = response.toarray().flatten()
        top_keyword_indices = scores.argsort()[-8:][::-1]
        
        good_keywords = []
        for i in top_keyword_indices:
            keyword = feature_names[i]
            if not keyword.strip(): continue
            pos_tag_list = nltk.pos_tag(nltk.word_tokenize(keyword))
            if not pos_tag_list: continue
            is_good = any(tag.startswith('NN') or tag.startswith('JJ') for word, tag in pos_tag_list)
            if is_good: good_keywords.append(keyword)
        
        if len(good_keywords) < 3: return nltk.sent_tokenize(text_content)[0].strip()
        title = ' '.join(word.capitalize() for word in good_keywords[:5])
        return title
    except Exception as e:
        logger.error(f"AI生成标题失败: {e}")
        return nltk.sent_tokenize(text_content)[0].strip()

def save_article(output_path, text_content, title, author):
    word_count = len(text_content.split())
    reading_time = f"~{round(word_count / 200)} min"
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
    logger.info(f"已保存文章: {output_path.name}")

def process_all_magazines():
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到！")
        return

    all_article_contents = []
    
    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        if not source_folder.is_dir():
            logger.warning(f"未找到杂志目录: {source_folder}")
            continue

        epub_files = sorted(list(source_folder.glob('*.epub')), key=os.path.getmtime, reverse=True)
        if not epub_files:
            logger.warning(f"在 {source_folder} 中未找到任何 .epub 文件。")
            continue
        
        latest_file_path = epub_files[0]
        
        # 使用新的核心函数来处理EPUB
        articles_from_epub = process_epub_file(latest_file_path)
        if not articles_from_epub:
            logger.warning(f"未能从 {latest_file_path.name} 中提取任何合格文章。")
            continue

        # 为后续的AI标题生成准备语料库
        all_article_contents.extend(articles_from_epub)

        # 为每一篇提取出的文章生成文件
        topic = info['topic']
        stem = f"{magazine_name.replace(' ', '_')}_{latest_file_path.stem}"
        for i, article_content in enumerate(articles_from_epub):
            # AI标题生成
            title = generate_title_from_content(article_content, articles_from_epub)
            # 作者提取
            author_match = re.search(r'(?:By|by|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z\'-]+)+)', article_content[:500])
            author = author_match.group(1).strip() if author_match else "N/A"
            
            output_path = ARTICLES_DIR / topic / f"{stem}_art{i+1}.md"
            save_article(output_path, article_content, title, author)

def generate_website():
    WEBSITE_DIR.mkdir(exist_ok=True)
    
    ### [COSMOS ENGINE UPGRADE]: 注入全新、带鼠标交互的粒子宇宙特效 ###
    shared_style_and_script = """
<style>
    @keyframes gradient-animation { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
    body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background: linear-gradient(-45deg, #02040a, #0d1117, #0b1021, #0d1117);
        background-size: 400% 400%; animation: gradient-animation 30s ease infinite;
        color: #c9d1d9; margin: 0; padding: 0; overflow-x: hidden;
    }
    #cosmos-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; pointer-events: none; }
</style>
<canvas id="cosmos-canvas"></canvas>
<script>
    const canvas = document.getElementById('cosmos-canvas'), ctx = canvas.getContext('2d');
    let particles = [];
    const numParticles = window.innerWidth > 768 ? 120 : 50;
    const mouse = { x: null, y: null, radius: 150 };

    window.addEventListener('mousemove', e => { mouse.x = e.x; mouse.y = e.y; });
    window.addEventListener('mouseout', () => { mouse.x = null; mouse.y = null; });

    function resizeCanvas() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    class Particle {
        constructor() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.baseX = this.x;
            this.baseY = this.y;
            this.density = (Math.random() * 30) + 1;
            this.size = Math.random() * 2 + 1;
            this.vx = (Math.random() - 0.5) * 0.5;
            this.vy = (Math.random() - 0.5) * 0.5;
        }
        update() {
            let dx = mouse.x - this.x;
            let dy = mouse.y - this.y;
            let distance = Math.sqrt(dx * dx + dy * dy);
            let forceDirectionX = dx / distance;
            let forceDirectionY = dy / distance;
            let maxDistance = mouse.radius;
            let force = (maxDistance - distance) / maxDistance;
            let directionX = 0, directionY = 0;

            if (distance < mouse.radius) {
                directionX = -forceDirectionX * force * this.density;
                directionY = -forceDirectionY * force * this.density;
            }
            this.x += this.vx + directionX;
            this.y += this.vy + directionY;

            if (this.x < 0 || this.x > canvas.width) { this.vx *= -1; }
            if (this.y < 0 || this.y > canvas.height) { this.vy *= -1; }
        }
        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(0, 191, 255, 0.7)';
            ctx.fill();
        }
    }
    function init() { for (let i = 0; i < numParticles; i++) particles.push(new Particle()); }
    function connect() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i; j < particles.length; j++) {
                const dist = Math.hypot(particles[i].x - particles[j].x, particles[i].y - particles[j].y);
                if (dist < 100) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(0, 191, 255, ${0.8 - dist / 100})`;
                    ctx.lineWidth = 0.4;
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
</script>
"""

    index_template_str = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Curated Journals | Cosmos Engine</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
<style>
    .container { max-width: 1400px; margin: 0 auto; padding: 4rem 2rem; position: relative; z-index: 1; }
    h1 { font-size: clamp(2.5rem, 8vw, 5rem); text-align: center; margin-bottom: 5rem; color: #fff; text-shadow: 0 0 25px rgba(0, 191, 255, 0.5), 0 0 50px rgba(0, 191, 255, 0.3); }
    .grid { display: grid; gap: 2.5rem; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); }
    .card { backdrop-filter: blur(16px) saturate(180%); -webkit-backdrop-filter: blur(16px) saturate(180%); background: rgba(17, 25, 40, 0.75); border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.125); padding: 2rem; transition: all 0.4s ease; display: flex; flex-direction: column; }
    .card:hover { transform: translateY(-10px) scale(1.02); box-shadow: 0 20px 40px rgba(0,0,0,0.4); border-color: rgba(0, 191, 255, 0.5); }
    .card-title { font-size: 1.5rem; font-weight: 500; line-height: 1.4; color: #fff; margin: 0 0 1.5rem 0; flex-grow: 1; }
    .card-meta { color: #8b949e; font-size: 0.9rem; }
    .card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(255, 255, 255, 0.1); }
    .read-link { color:#58a6ff; text-decoration:none; font-weight: 500; } .read-link:hover { color: #fff; text-decoration: underline; }
    .no-articles { text-align:center; padding:5rem; background-color:rgba(17, 25, 40, 0.8); border-radius:16px; }
</style></head><body>""" + shared_style_and_script + """<div class="container"><h1>AI Curated Journals</h1><div class="grid">
{% for article in articles %}
<div class="card">
    <h3 class="card-title">{{ article.title }}</h3>
    <p class="card-meta">{{ article.magazine }} · {{ article.reading_time }}</p>
    <div class="card-footer"><span style="color:#8b949e;">By {{ article.author }}</span><a href="{{ article.url }}" class="read-link">Read Article →</a></div>
</div>
{% endfor %}
</div>{% if not articles %}<div class="no-articles"><h2>No Articles Found</h2><p>The Cosmos Engine is running, but no new articles were processed in this cycle.</p></div>{% endif %}
</div></body></html>"""

    article_html_template = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<style>
    .container { max-width: 720px; margin: 6rem auto; padding: clamp(2rem, 5vw, 4rem); backdrop-filter: blur(16px) saturate(180%); -webkit-backdrop-filter: blur(16px) saturate(180%); background-color: rgba(17, 25, 40, 0.85); border-radius: 16px; border: 1px solid rgba(255,255,255,0.125); position: relative; z-index: 1; }
    .back-link { font-family: 'Inter', sans-serif; display: inline-block; margin-bottom: 3rem; text-decoration: none; color: #8892b0; transition: color 0.3s; } .back-link:hover { color: #58a6ff; }
    h1 { font-family: 'Inter', sans-serif; font-size: clamp(2rem, 6vw, 3.2rem); line-height: 1.2; color: #fff; margin:0; }
    .article-meta { font-family: 'Inter', sans-serif; color: #8892b0; margin: 1.5rem 0 3rem 0; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 2rem; font-size: 0.9rem; }
    .article-body { font-family: 'Lora', serif; font-size: 1.15rem; line-height: 2; color: #c9d1d9; }
    .article-body p { margin: 0 0 1.5em 0; } .article-body h2, .article-body h3 { font-family: 'Inter', sans-serif; color: #fff; }
</style></head><body>""" + shared_style_and_script + """<div class="container"><a href="index.html" class="back-link">← Back to Journal List</a><h1>{{ title }}</h1>
<p class="article-meta">By {{ author }} · From {{ magazine }} · {{ reading_time }}</p>
<div class="article-body">{{ content }}</div></div></body></html>"""

    articles_data = []
    md_files = glob.glob(str(ARTICLES_DIR / '**/*.md'), recursive=True)

    for md_file_path in md_files:
        md_file = Path(md_file_path)
        try:
            with md_file.open('r', encoding='utf-8') as f: content_with_frontmatter = f.read()
            parts = content_with_frontmatter.split('---', 2)
            if len(parts) < 3: continue
            frontmatter, content = parts[1], parts[2]
            title = re.search(r'title: "?(.*?)"?\n', frontmatter).group(1)
            author = re.search(r'author: "?(.*?)"?\n', frontmatter).group(1)
            reading_time = re.search(r'reading_time: "?(.*?)"?\n', frontmatter).group(1)
            magazine_match = re.match(r'([a-zA-Z_]+)', md_file.name)
            magazine = magazine_match.group(1).split('_')[0].replace('_', ' ').title() if magazine_match else "Unknown"
            
            article_filename, article_path = f"{md_file.stem}.html", WEBSITE_DIR / f"{md_file.stem}.html"
            article_template = jinja2.Template(article_html_template)
            article_html = article_template.render(title=title, content=markdown2.markdown(content), author=author, magazine=magazine, reading_time=reading_time)
            article_path.write_text(article_html, encoding='utf-8')
            
            articles_data.append({"title": title, "url": article_filename, "magazine": magazine, "author": author, "reading_time": reading_time})
        except Exception as e:
            logger.error(f"生成网页时处理文件 {md_file} 失败: {e}")
            continue

    articles_data.sort(key=lambda x: (x['magazine'], x['title']))
    template = jinja2.Template(index_template_str)
    (WEBSITE_DIR / "index.html").write_text(template.render(articles=articles_data), encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()

    if articles_data:
        logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。")
    else:
        logger.warning("网站生成完成，但没有找到任何文章。")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
