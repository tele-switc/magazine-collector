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

# 在GitHub Actions环境中，NLTK_DATA路径可能需要显式设置
if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

SOURCE_REPO_PATH = Path("source_repo")
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")
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
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

### [COSMOS ENGINE FIX v2]: 经过实战检验的、健壮的文章提取逻辑 ###
def process_epub_file(epub_path):
    """
    深入解析单个EPUB文件，将其中的每个子文档作为潜在文章进行质检。
    此版本修复了过滤条件过于严格导致无法提取任何文章的问题。
    """
    logger.info(f"正在深入解析: {epub_path.name}")
    articles = []
    try:
        book = epub.read_epub(str(epub_path))
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        
        logger.info(f"在 {epub_path.name} 中找到 {len(items)} 个潜在的文档。开始质检...")

        for i, item in enumerate(items):
            # 使用 'lxml' 解析器，速度更快，容错性更强
            soup = BeautifulSoup(item.get_content(), 'lxml')
            
            # 移除所有非文本内容和导航元素
            for tag in soup(['script', 'style', 'a', 'img', 'nav', 'header', 'footer', 'figure', 'figcaption']):
                tag.decompose()
            
            text_content = soup.get_text(separator='\n', strip=True)
            # 使用更强的正则表达式来清理多余的换行符
            text_content = re.sub(r'\n\s*\n+', '\n\n', text_content).strip()

            # --- 文章质检流程 (优化版) ---
            
            # 1. 长度检查 (门槛灵活)
            word_count = len(text_content.split())
            if word_count < 150:
                logger.info(f"  - [跳过] 文档 {i}: 长度不足 ({word_count} words < 150)。")
                continue

            # 2. 关键词过滤 (检查前500个字符，更可靠)
            header_text = text_content[:500].lower()
            matched_keyword = next((kw for kw in NON_ARTICLE_KEYWORDS if kw in header_text), None)
            if matched_keyword:
                logger.info(f"  - [跳过] 文档 {i}: 发现非文章关键词 '{matched_keyword}'。")
                continue

            # 3. 新增检查：内容有效性 (避免只有标题和作者信息的空壳)
            # 检查文本中是否至少有4个段落（由两个换行符分隔）
            if text_content.count('\n\n') < 3:
                logger.info(f"  - [跳过] 文档 {i}: 内容结构过于简单 (段落 < 4)，可能不是完整文章。")
                continue

            logger.info(f"  -> [成功] 从EPUB子文档 {i} 成功提取一篇合格文章 (长度: {word_count} words)。")
            articles.append(text_content)
            
    except Exception as e:
        logger.error(f"解析EPUB文件 {epub_path.name} 时发生严重错误: {e}", exc_info=True)
    
    if not articles:
        logger.warning(f"质检完成，但未能从 {epub_path.name} 中提取任何合格文章。请检查日志中的'[跳过]'信息。")
    else:
        logger.info(f"成功从 {epub_path.name} 中提取了 {len(articles)} 篇合格文章！")

    return articles

def generate_title_from_content(text_content, all_texts_corpus):
    """使用TF-IDF算法从文章内容中智能生成一个简洁的标题。"""
    try:
        # 扩展的停用词列表，提高标题质量
        stop_words = list(stopwords.words('english'))
        stop_words.extend(['would', 'could', 'said', 'also', 'like', 'get', 'one', 'two', 'told', 'mr', 'ms', 'mrs', 'year', 'week', 'day'])
        
        # 使用更精准的token模式
        vectorizer = TfidfVectorizer(max_features=20, stop_words=stop_words, ngram_range=(1, 3), token_pattern=r'(?u)\b[a-zA-Z-]{4,}\b')
        vectorizer.fit(all_texts_corpus)
        response = vectorizer.transform([text_content])
        feature_names = vectorizer.get_feature_names_out()
        
        if not feature_names.any():
            return nltk.sent_tokenize(text_content)[0].strip()

        scores = response.toarray().flatten()
        top_keyword_indices = scores.argsort()[-8:][::-1]
        
        good_keywords = []
        for i in top_keyword_indices:
            keyword = feature_names[i]
            if not keyword.strip(): continue
            # 优先选择名词和形容词作为标题关键词
            pos_tag_list = nltk.pos_tag(nltk.word_tokenize(keyword))
            if not pos_tag_list: continue
            is_good = any(tag.startswith('NN') or tag.startswith('JJ') for word, tag in pos_tag_list)
            if is_good: good_keywords.append(keyword)
        
        # 如果关键词太少，则使用文章第一句话作为备用标题
        if len(good_keywords) < 3:
            return nltk.sent_tokenize(text_content)[0].strip()
            
        title = ' '.join(word.capitalize() for word in good_keywords[:5])
        return title
    except Exception as e:
        logger.error(f"AI生成标题失败: {e}")
        # 最终备用方案
        return nltk.sent_tokenize(text_content)[0].strip() if text_content else "Untitled Article"

def save_article(output_path, text_content, title, author):
    """保存文章为带有Frontmatter的Markdown文件。"""
    word_count = len(text_content.split())
    # 阅读时间计算更精确
    reading_time = f"~{max(1, round(word_count / 230))} min read"
    # 确保标题中的双引号被正确处理
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
    """主处理流程：遍历所有配置的杂志，提取文章并保存。"""
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到！脚本将终止。")
        return

    all_extracted_articles = []
    
    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        if not source_folder.is_dir():
            logger.warning(f"未找到杂志目录: {source_folder}")
            continue

        # 仅处理最新的一期杂志
        epub_files = sorted(list(source_folder.glob('*.epub')), key=os.path.getmtime, reverse=True)
        if not epub_files:
            logger.warning(f"在 {source_folder} 中未找到任何 .epub 文件。")
            continue
        
        latest_file_path = epub_files[0]
        
        # 使用修复后的核心函数处理EPUB
        articles_from_epub = process_epub_file(latest_file_path)
        if not articles_from_epub:
            continue

        # 为后续的AI标题生成准备语料库
        corpus = articles_from_epub[:]
        
        # 为每一篇提取出的文章生成文件
        topic = info['topic']
        # 创建更清晰的文件名
        stem = f"{magazine_name.replace(' ', '_')}_{latest_file_path.stem.replace(' ', '_')}"
        
        for i, article_content in enumerate(articles_from_epub):
            title = generate_title_from_content(article_content, corpus)
            # 使用更强大的正则表达式提取作者姓名
            author_match = re.search(r'(?:By|by|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z\'-]+){1,3})', article_content[:600])
            author = author_match.group(1).strip() if author_match else "Source"
            
            output_path = ARTICLES_DIR / topic / f"{stem}_art{i+1}.md"
            save_article(output_path, article_content, title, author)
            all_extracted_articles.append(output_path)
            
    logger.info(f"所有杂志处理完毕。共提取了 {len(all_extracted_articles)} 篇新文章。")

def generate_website():
    """使用Jinja2模板从Markdown文件生成静态HTML网站。"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    
    ### [VISUAL UPGRADE v2]: 全新“神经网络/数字星座”动态背景 ###
    shared_style_and_script = """
<style>
    body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: #0d1117;
        background-image: radial-gradient(ellipse at bottom, #1b2735 0%, #090a0f 100%);
        color: #c9d1d9; margin: 0; padding: 0; overflow-x: hidden;
    }
    #neural-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; }
</style>
<canvas id="neural-canvas"></canvas>
<script>
    document.addEventListener('DOMContentLoaded', () => {
        const canvas = document.getElementById('neural-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        let particles = [];
        const particleCount = window.innerWidth > 768 ? 100 : 40;
        const mouse = { x: null, y: null, radius: 100 };
        const colors = ['#4D4BFF', '#A855F7', '#EC4899', '#F59E0B', '#3B82F6'];

        const resizeCanvas = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        };
        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();

        window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
        window.addEventListener('mouseout', () => { mouse.x = null; mouse.y = null; });

        class Particle {
            constructor() {
                this.x = Math.random() * canvas.width;
                this.y = Math.random() * canvas.height;
                this.size = Math.random() * 2 + 1;
                this.speedX = (Math.random() - 0.5) * 0.8;
                this.speedY = (Math.random() - 0.5) * 0.8;
                this.color = colors[Math.floor(Math.random() * colors.length)];
            }
            update() {
                if (this.x > canvas.width || this.x < 0) this.speedX *= -1;
                if (this.y > canvas.height || this.y < 0) this.speedY *= -1;
                this.x += this.speedX;
                this.y += this.speedY;

                if (mouse.x != null) {
                    const dx = mouse.x - this.x;
                    const dy = mouse.y - this.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    if (distance < mouse.radius) {
                        this.x -= dx / 15;
                        this.y -= dy / 15;
                    }
                }
            }
            draw() {
                ctx.fillStyle = this.color;
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        function init() {
            particles = [];
            for (let i = 0; i < particleCount; i++) {
                particles.push(new Particle());
            }
        }

        function connect() {
            let opacity;
            for (let a = 0; a < particles.length; a++) {
                for (let b = a; b < particles.length; b++) {
                    const distance = Math.sqrt(
                        Math.pow(particles[a].x - particles[b].x, 2) +
                        Math.pow(particles[a].y - particles[b].y, 2)
                    );
                    if (distance < 120) {
                        opacity = 1 - distance / 120;
                        ctx.strokeStyle = `rgba(255, 255, 255, ${opacity * 0.5})`;
                        ctx.lineWidth = 0.8;
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
        init();
        animate();
    });
</script>
"""

    index_template_str = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Curated Journals | Cosmos Engine</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
<style>
    .container { max-width: 1400px; margin: 0 auto; padding: 4rem 2rem; position: relative; z-index: 1; }
    h1 { font-size: clamp(2.5rem, 6vw, 4.5rem); text-align: center; margin-bottom: 5rem; color: #fff; text-shadow: 0 0 15px rgba(77, 75, 255, 0.5), 0 0 30px rgba(168, 85, 247, 0.3); letter-spacing: -0.02em; }
    .grid { display: grid; gap: 2.5rem; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); }
    .card { backdrop-filter: blur(10px) saturate(150%); -webkit-backdrop-filter: blur(10px) saturate(150%); background: rgba(23, 28, 40, 0.6); border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.1); padding: 2rem; transition: all 0.3s ease; display: flex; flex-direction: column; }
    .card:hover { transform: translateY(-8px); box-shadow: 0 15px 30px rgba(0,0,0,0.3); border-color: rgba(77, 75, 255, 0.4); }
    .card-title { font-size: 1.4rem; font-weight: 500; line-height: 1.4; color: #f0f6fc; margin: 0 0 1rem 0; flex-grow: 1; }
    .card-meta { color: #8b949e; font-size: 0.85rem; }
    .card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid rgba(255, 255, 255, 0.08); }
    .read-link { color:#58a6ff; text-decoration:none; font-weight: 500; font-size: 0.9rem; } .read-link:hover { color: #80bfff; }
    .no-articles { text-align:center; padding:5rem 2rem; backdrop-filter: blur(10px); background: rgba(17, 25, 40, 0.7); border-radius:16px; border: 1px solid rgba(255, 255, 255, 0.1); }
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
</div>{% if not articles %}<div class="no-articles"><h2>No Articles Found</h2><p>The Cosmos Engine is running, but no new articles were processed in this cycle. Please check the source repository or the script logs.</p></div>{% endif %}
</div></body></html>"""

    article_html_template = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<style>
    .container { max-width: 720px; margin: 6rem auto; padding: clamp(2rem, 5vw, 4rem); backdrop-filter: blur(12px) saturate(180%); -webkit-backdrop-filter: blur(12px) saturate(180%); background-color: rgba(23, 28, 40, 0.8); border-radius: 16px; border: 1px solid rgba(255,255,255,0.125); position: relative; z-index: 1; }
    .back-link { font-family: 'Inter', sans-serif; display: inline-block; margin-bottom: 3rem; text-decoration: none; color: #8892b0; transition: color 0.3s; } .back-link:hover { color: #58a6ff; }
    h1 { font-family: 'Inter', sans-serif; font-size: clamp(2rem, 6vw, 3.2rem); line-height: 1.2; color: #fff; margin:0; }
    .article-meta { font-family: 'Inter', sans-serif; color: #8892b0; margin: 1.5rem 0 3rem 0; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 2rem; font-size: 0.9rem; }
    .article-body { font-family: 'Lora', serif; font-size: 1.1rem; line-height: 1.9; color: #c9d1d9; }
    .article-body p { margin: 0 0 1.5em 0; } .article-body h2, .article-body h3 { font-family: 'Inter', sans-serif; color: #e6edf3; }
</style></head><body>""" + shared_style_and_script + """<div class="container"><a href="index.html" class="back-link">← Back to Journal List</a><h1>{{ title }}</h1>
<p class="article-meta">By {{ author }} · From {{ magazine }} · {{ reading_time }}</p>
<div class="article-body">{{ content }}</div></div></body></html>"""

    articles_data = []
    # 使用 glob 获取所有 Markdown 文件路径
    md_files = glob.glob(str(ARTICLES_DIR / '**/*.md'), recursive=True)

    for md_file_path in md_files:
        md_file = Path(md_file_path)
        try:
            with md_file.open('r', encoding='utf-8') as f: content_with_frontmatter = f.read()
            
            # 使用更稳健的方式解析 frontmatter
            match = re.match(r'---\s*(.*?)\s*---\s*(.*)', content_with_frontmatter, re.DOTALL)
            if not match: continue
            
            frontmatter, content = match.groups()
            
            def get_meta(key, text):
                m = re.search(fr'{key}:\s*"?(.+?)"?\s*\n', text)
                return m.group(1).strip() if m else "Unknown"

            title = get_meta('title', frontmatter)
            author = get_meta('author', frontmatter)
            reading_time = get_meta('reading_time', frontmatter)

            # 从文件名中提取杂志名称
            magazine_name_raw = md_file.name.split('_')[0]
            magazine = ' '.join(word.capitalize() for word in magazine_name_raw.split('-'))

            article_filename = f"{md_file.stem}.html"
            article_path = WEBSITE_DIR / article_filename
            
            # 渲染文章页面
            article_template = jinja2.Template(article_html_template)
            html_content = markdown2.markdown(content)
            article_html = article_template.render(title=title, content=html_content, author=author, magazine=magazine, reading_time=reading_time)
            article_path.write_text(article_html, encoding='utf-8')
            
            articles_data.append({"title": title, "url": article_filename, "magazine": magazine, "author": author, "reading_time": reading_time})
        
        except Exception as e:
            logger.error(f"生成网页时处理文件 {md_file} 失败: {e}", exc_info=True)
            continue

    # 按杂志名称和标题排序，确保每次生成顺序一致
    articles_data.sort(key=lambda x: (x['magazine'], x['title']))
    
    # 渲染首页
    index_template = jinja2.Template(index_template_str)
    (WEBSITE_DIR / "index.html").write_text(index_template.render(articles=articles_data), encoding='utf-8')
    
    # 添加 .nojekyll 文件，防止 GitHub Pages 忽略以下划线开头的目录
    (WEBSITE_DIR / ".nojekyll").touch()

    if articles_data:
        logger.info(f"网站生成完成，包含 {len(articles_data)} 篇文章。访问 docs/index.html 查看。")
    else:
        logger.warning("网站生成完成，但没有找到任何文章。请检查 articles 目录是否为空。")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
