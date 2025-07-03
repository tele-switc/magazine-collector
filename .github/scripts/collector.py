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
import glob
from transformers import pipeline, AutoTokenizer

# ==============================================================================
# 1. 配置和初始化
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

def setup_nltk():
    nltk_data_path = Path.cwd() / "nltk_data"
    nltk_data_path.mkdir(exist_ok=True)
    nltk.data.path.append(str(nltk_data_path))
    required_packages = {'tokenizers/punkt': 'punkt'}
    for path, package_id in required_packages.items():
        try: nltk.data.find(path); logger.info(f"[NLTK] '{package_id}' 已存在。")
        except LookupError:
            logger.info(f"[NLTK] '{package_id}' 未找到，开始下载...")
            nltk.download(package_id, download_dir=str(nltk_data_path))
setup_nltk()

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
    "The Economist": {"match_key": "economist"},
    "Wired":         {"match_key": "wired"},
    "The Atlantic":  {"match_key": "atlantic"}
}

logger.info("正在初始化AI模型...")
try:
    SUMMARIZER_MODEL = "sshleifer/distilbart-cnn-6-6"
    CLASSIFIER_MODEL = "facebook/bart-large-mnli"
    summarizer = pipeline("summarization", model=SUMMARIZER_MODEL)
    summarizer_tokenizer = AutoTokenizer.from_pretrained(SUMMARIZER_MODEL)
    classifier = pipeline("zero-shot-classification", model=CLASSIFIER_MODEL)
    classifier_tokenizer = AutoTokenizer.from_pretrained(CLASSIFIER_MODEL)
    logger.info("AI模型和分词器初始化成功！")
except Exception as e:
    logger.error(f"AI模型初始化失败: {e}. 后续AI功能将不可用。")
    summarizer, classifier = None, None

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================
def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    (ARTICLES_DIR / "ai_generated").mkdir(exist_ok=True)

def process_epub_file(epub_path):
    articles = []
    try:
        book = epub.read_epub(str(epub_path))
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        for item in items:
            soup = BeautifulSoup(item.get_content(), 'lxml')
            paragraphs = soup.find_all('p')
            if len(paragraphs) < 8: continue
            text_from_paragraphs = [p.get_text(strip=True) for p in paragraphs]
            text_content = "\n\n".join(p for p in text_from_paragraphs if p)
            if 400 < len(text_content.split()) < 4000:
                articles.append(text_content)
    except Exception as e:
        logger.error(f"  解析EPUB {epub_path.name} 出错: {e}", exc_info=False)
    return articles

def get_ai_metadata(text):
    title, category = "Untitled Article", "General"
    
    def get_safe_snippet(tokenizer, text, max_length=512):
        tokens = tokenizer.encode(text)
        safe_tokens = tokens[:max_length]
        return tokenizer.decode(safe_tokens, skip_special_tokens=True)

    if summarizer:
        try:
            snippet = get_safe_snippet(summarizer_tokenizer, text, max_length=1024)
            summary = summarizer(snippet, max_length=30, min_length=8, do_sample=False)
            title = summary[0]['summary_text'].strip()
        except Exception:
            title = nltk.sent_tokenize(text)[0].strip()
    else:
        title = nltk.sent_tokenize(text)[0].strip()

    if classifier:
        try:
            snippet = get_safe_snippet(classifier_tokenizer, text, max_length=512)
            candidate_labels = ['technology', 'politics', 'business', 'science', 'culture', 'world affairs']
            result = classifier(snippet, candidate_labels)
            category = result['labels'][0].capitalize()
        except Exception as e:
            logger.warning(f"  AI分类失败: {e}")

    # --- 最终加固：确保标题不会过长 ---
    if len(title) > 150:
        title = title[:150] + "..."

    return title, category

def save_article(output_path, text_content, title, author, magazine, category):
    word_count = len(text_content.split())
    reading_time = f"~{max(1, round(word_count / 230))} min read"
    safe_title = title.replace('"', "'")
    frontmatter = f'---\ntitle: "{safe_title}"\nauthor: "{author}"\nmagazine: "{magazine}"\ncategory: "{category}"\nwords: {word_count}\nreading_time: "{reading_time}"\n---\n\n'
    output_path.write_text(frontmatter + text_content, encoding="utf-8")

def extract_date_from_path(path):
    match = re.search(r'(\d{4}[-.]\d{2}[-.]\d{2})', path.name)
    if match: return match.group(1).replace('-', '.')
    return "1970.01.01"

def process_all_magazines():
    logger.info("--- 开始文章提取流程 (终极完美版) ---")
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"致命错误: 源仓库目录 '{SOURCE_REPO_PATH}' 不存在！")
        return
    found_epubs = [Path(root) / file for root, _, files in os.walk(SOURCE_REPO_PATH) for file in files if file.endswith('.epub')]
    if not found_epubs:
        logger.warning("在源仓库中未找到任何 .epub 文件。")
        return
    magazine_epubs = {name: [] for name in MAGAZINES}
    for path in found_epubs:
        path_str_lower = str(path).lower()
        for name, info in MAGAZINES.items():
            if info["match_key"] in path_str_lower:
                magazine_epubs[name].append(path)
                break
    total_articles_extracted = 0
    for magazine_name, epub_paths in magazine_epubs.items():
        if not epub_paths: continue
        logger.info(f"\n>>> 处理杂志: {magazine_name}")
        sorted_epub_paths = sorted(epub_paths, key=extract_date_from_path, reverse=True)
        for epub_path in sorted_epub_paths:
            logger.info(f"  尝试处理文件: {epub_path.name}")
            articles = process_epub_file(epub_path)
            if articles:
                logger.info(f"  [成功] 在文件 {epub_path.name} 中找到 {len(articles)} 篇有效文章。")
                for i, article_content in enumerate(articles):
                    title, category = get_ai_metadata(article_content)
                    author_match = re.search(r'(?:By|by|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z\'-]+){1,3})', article_content[:800])
                    author = author_match.group(1).strip() if author_match else "N/A"
                    stem = f"{magazine_name.replace(' ', '_')}_{epub_path.stem.replace(' ', '_')}"
                    output_path = ARTICLES_DIR / "ai_generated" / f"{stem}_art{i+1}.md"
                    save_article(output_path, article_content, title, author, magazine_name, category)
                    total_articles_extracted += 1
                    logger.info(f"    -> 已保存: {output_path.name} (分类: {category}, 作者: {author})")
                break 
            else:
                logger.warning(f"  [跳过] 文件 {epub_path.name} 未提取到有效文章，尝试下一个...")
    logger.info(f"\n--- 文章提取流程结束。共提取了 {total_articles_extracted} 篇新文章。 ---")


def generate_website():
    logger.info("--- 开始生成网站 (终极完美版) ---")
    WEBSITE_DIR.mkdir(exist_ok=True)
    shared_style_and_script = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;700&family=Noto+Serif+SC:wght@400;700&display=swap');
    body { background-color: #010409; color: #e6edf3; margin: 0; }
    #dynamic-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; }
</style>
<canvas id="dynamic-canvas"></canvas>
<script>
document.addEventListener('DOMContentLoaded',()=>{const e=document.getElementById("dynamic-canvas");if(!e)return;const t=e.getContext("2d");let n=[],o=[];const s=window.innerWidth>768?120:50,i={x:null,y:null,radius:100};const l=()=>{e.width=window.innerWidth,e.height=window.innerHeight};window.addEventListener("resize",l),l(),window.addEventListener("mousemove",e=>{i.x=e.clientX,i.y=e.clientY}),window.addEventListener("mouseout",()=>{i.x=null,i.y=null});class a{constructor(){this.x=Math.random()*e.width,this.y=Math.random()*e.height,this.size=Math.random()*1.5+.5,this.speedX=.4*(Math.random()-.5),this.speedY=.4*(Math.random()-.5),this.opacity=.2+Math.random()*.5}update(){(this.x<0||this.x>e.width)&&(this.speedX*=-1),(this.y<0||this.y>e.height)&&(this.speedY*=-1),this.x+=this.speedX,this.y+=this.speedY,i.x&&(()=>{const e=i.x-this.x,t=i.y-this.y,n=Math.hypot(e,t);if(n<i.radius){const o=(i.radius-n)/i.radius;this.x-=e/n*o,this.y-=t/n*o}})()}draw(){t.fillStyle=`rgba(0, 191, 255, ${this.opacity})`,t.beginPath(),t.arc(this.x,this.y,this.size,0,2*Math.PI),t.fill()}}class r{constructor(){this.reset()}reset(){this.x=Math.random()*e.width+100,this.y=-10,this.len=10+80*Math.random(),this.speed=6+8*Math.random(),this.size=.5+1*Math.random(),this.active=!0}update(){this.active&&(this.x-=this.speed,this.y+=this.speed,(this.x<-this.len||this.y>e.height+this.len)&&(this.active=!1))}draw(){this.active&&(t.strokeStyle="#00BFFF",t.lineWidth=this.size,t.beginPath(),t.moveTo(this.x,this.y),t.lineTo(this.x-this.len,this.y+this.len),t.stroke())}}function c(){for(let e=0;e<s;e++)n.push(new a())}function h(){o.length<3&&Math.random()>.99&&o.push(new r),o=o.filter(e=>e.active)}!function d(){t.clearRect(0,0,e.width,e.height),n.forEach(e=>{e.update(),e.draw()}),h(),o.forEach(e=>{e.update(),e.draw()}),requestAnimationFrame(d)}(),c()});
</script>"""
    index_template_str = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>外刊阅读</title>""" + shared_style_and_script + """
<style>
    body, h1, h2, h3, p, span, a, div { font-family: 'Cormorant Garamond', 'Noto Serif SC', serif; }
    .container { max-width: 1400px; margin: 0 auto; padding: 5rem 2rem; position: relative; z-index: 1; }
    h1 { font-size: clamp(3.5rem, 8vw, 6rem); text-align: center; margin-bottom: 6rem; color: #fff; font-weight: 700; text-shadow: 0 0 30px rgba(0, 191, 255, 0.4); }
    .grid { display: grid; gap: 3rem; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); }
    .card {
        background: rgba(13, 22, 38, 0.4); backdrop-filter: blur(50px); -webkit-backdrop-filter: blur(50px);
        border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 20px; padding: 2.5rem;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); transition: all 0.4s ease;
        display: flex; flex-direction: column;
    }
    .card:hover { transform: translateY(-15px); background: rgba(20, 35, 58, 0.5); box-shadow: 0 20px 50px rgba(0, 127, 255, 0.2); border-color: rgba(255, 255, 255, 0.15); }
    .card-title { font-size: 1.5rem; font-weight: 700; line-height: 1.4; color: #f0f6fc; margin: 0 0 1rem 0; flex-grow: 1; }
    .card-meta { color: #b0c4de; font-size: 0.9rem; margin-bottom: 1rem; }
    .card-category { display: inline-block; background-color: rgba(0, 191, 255, 0.1); color: #87ceeb; padding: 0.25rem 0.75rem; border-radius: 1rem; font-size: 0.8rem; font-weight: 700; margin-top: auto; }
    .card-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 1.5rem; border-top: 1px solid rgba(255, 255, 255, 0.1); }
    .read-link { color:#87ceeb; text-decoration:none; font-weight: 700; font-size: 0.9rem; }
    .no-articles { background: rgba(13, 22, 38, 0.4); backdrop-filter: blur(50px); border-radius: 20px; text-align:center; padding:5rem 2rem; }
</style></head><body><div class="container"><h1>外刊阅读</h1><div class="grid">
{% for article in articles %}<div class="card">
    <div>
        <h3 class="card-title">{{ article.title }}</h3>
        <p class="card-meta">{{ article.magazine }} · {{ article.reading_time }}</p>
    </div>
    <div style="flex-grow: 1;"></div>
    <div class="card-footer">
        <span class="card-category">{{ article.category }}</span>
        <a href="{{ article.url }}" class="read-link">阅读 →</a>
    </div>
</div>{% endfor %}
</div>{% if not articles %}<div class="no-articles"><h2>未发现文章</h2><p>引擎已运行，但本次未处理新的文章。</p></div>{% endif %}</div></body></html>"""
    article_html_template = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }} | 外刊阅读</title>""" + shared_style_and_script + """
<style>
    body, h1, h2, h3, p, span, a, div { font-family: 'Cormorant Garamond', 'Noto Serif SC', serif; }
    .article-container {
        max-width: 760px; margin: 6rem auto; padding: clamp(3rem, 6vw, 5rem);
        background: rgba(13, 22, 38, 0.6); backdrop-filter: blur(50px); -webkit-backdrop-filter: blur(50px);
        border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.1);
        position: relative; z-index: 1; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
    }
    .back-link { display: inline-block; margin-bottom: 3rem; text-decoration: none; color: #b0c4de; transition: color 0.3s; font-size: 1.1rem; } .back-link:hover { color: #87ceeb; }
    h1 { font-size: clamp(2.2rem, 6vw, 3.2rem); line-height: 1.3; color: #fff; margin:0; font-weight: 700; }
    .article-meta { color: #b0c4de; margin: 2rem 0 3rem 0; border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 2rem; font-size: 1rem; }
    .article-body { font-size: 1.15rem; line-height: 2.1; color: #dce3ec; }
    .article-body p { margin: 0 0 1.75em 0; }
</style></head><body><div class="article-container"><a href="index.html" class="back-link">← 返回列表</a><h1>{{ title }}</h1><p class="article-meta">By {{ author }} · From {{ magazine }} · {{ reading_time }}</p><div class="article-body">{{ content }}</div></div></body></html>"""
    articles_data = []
    md_files = glob.glob(str(ARTICLES_DIR / 'ai_generated' / '*.md'), recursive=True)
    logger.info(f"找到 {len(md_files)} 个 Markdown 文件用于生成网页。")
    for md_file_path in md_files:
        try:
            md_file = Path(md_file_path)
            content_with_frontmatter = md_file.read_text(encoding='utf-8')
            match = re.match(r'---\s*(.*?)\s*---\s*(.*)', content_with_frontmatter, re.DOTALL)
            if not match: continue
            frontmatter, content = match.groups()
            def get_meta(key, text):
                m = re.search(fr'^{key}:\s*"?(.+?)"?\s*$', text, re.MULTILINE)
                return m.group(1).strip() if m else "N/A"
            title, author, magazine, category, reading_time = [get_meta(k, frontmatter) for k in ['title', 'author', 'magazine', 'category', 'reading_time']]
            article_filename, article_path = f"{md_file.stem}.html", WEBSITE_DIR / f"{md_file.stem}.html"
            article_html = jinja2.Template(article_html_template).render(title=title, content=markdown2.markdown(content), author=author, magazine=magazine, reading_time=reading_time)
            article_path.write_text(article_html, encoding='utf-8')
            articles_data.append({"title": title, "url": article_filename, "magazine": magazine, "author": author, "category": category, "reading_time": reading_time})
        except Exception as e:
            logger.error(f"生成网页 {md_file_path} 失败: {e}")
    articles_data.sort(key=lambda x: (x['magazine'], x['title']))
    (WEBSITE_DIR / "index.html").write_text(jinja2.Template(index_template_str).render(articles=articles_data), encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info("--- 网站生成结束 ---")

if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
