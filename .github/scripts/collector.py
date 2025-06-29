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
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

if 'NLTK_DATA' in os.environ:
    nltk.data.path.append(os.environ['NLTK_DATA'])

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
    "The Economist": {"match_key": "economist", "topic": "world_affairs"},
    "Wired":         {"match_key": "wired", "topic": "technology"},
    "The Atlantic":  {"match_key": "atlantic", "topic": "world_affairs"}
}

# ==============================================================================
# 2. 核心功能函数 (已稳定)
# ==============================================================================
def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def process_epub_file(epub_path):
    articles = []
    try:
        book = epub.read_epub(str(epub_path))
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        for item in items:
            soup = BeautifulSoup(item.get_content(), 'lxml')
            for tag in soup(['script', 'style', 'a', 'img', 'nav', 'header', 'footer', 'figure', 'figcaption']):
                tag.decompose()
            text_content = re.sub(r'\n\s*\n+', '\n\n', soup.get_text(separator='\n', strip=True)).strip()
            if len(text_content.split()) > 150 and not any(kw in text_content[:500].lower() for kw in NON_ARTICLE_KEYWORDS) and text_content.count('\n\n') > 3:
                articles.append(text_content)
    except Exception as e:
        logger.error(f"  解析EPUB {epub_path.name} 出错: {e}", exc_info=True)
    return articles

def generate_title_from_content(text, corpus):
    try:
        stop_words = list(stopwords.words('english')) + ['would', 'could', 'said', 'also', 'like', 'one', 'two', 'mr', 'ms']
        vectorizer = TfidfVectorizer(max_features=20, stop_words=stop_words, ngram_range=(1, 3), token_pattern=r'(?u)\b[a-zA-Z-]{4,}\b')
        vectorizer.fit(corpus)
        response = vectorizer.transform([text])
        feature_names = vectorizer.get_feature_names_out()
        if not feature_names.any(): return nltk.sent_tokenize(text)[0].strip()
        scores = response.toarray().flatten()
        top_keywords = [feature_names[i] for i in scores.argsort()[-8:][::-1] if feature_names[i].strip()]
        if len(top_keywords) < 3: return nltk.sent_tokenize(text)[0].strip()
        return ' '.join(word.capitalize() for word in top_keywords[:5])
    except:
        return nltk.sent_tokenize(text)[0].strip() if text else "Untitled Article"

def save_article(output_path, text_content, title, author):
    word_count = len(text_content.split())
    reading_time = f"~{max(1, round(word_count / 230))} min read"
    safe_title = title.replace('"', "'")
    frontmatter = f'---\ntitle: "{safe_title}"\nauthor: "{author}"\nwords: {word_count}\nreading_time: "{reading_time}"\n---\n\n'
    output_path.write_text(frontmatter + text_content, encoding="utf-8")

### [胜利最终版] 引入智能过滤和排序，并保留容错回退机制 ###
def process_all_magazines():
    logger.info("--- 开始文章提取流程 (最终版 v2) ---")
    
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
        if not epub_paths:
            logger.info(f"杂志 '{magazine_name}' 没有找到可处理的EPUB文件，跳过。")
            continue
        
        logger.info(f"\n>>> 处理杂志: {magazine_name}")
        
        # --- 智能过滤与排序 ---
        # 1. 优先选择文件名中包含下划线的标准格式文件
        standard_files = [p for p in epub_paths if '_' in p.name]
        # 2. 如果没有标准文件，才使用所有文件
        files_to_process = standard_files if standard_files else epub_paths
        
        # 3. 对筛选后的文件列表进行排序
        sorted_epub_paths = sorted(files_to_process, key=lambda p: p.name, reverse=True)
        
        if not sorted_epub_paths:
            logger.warning(f"  杂志 '{magazine_name}' 没有找到符合格式的文件可供处理。")
            continue

        # --- 容错回退机制 ---
        articles_processed_for_this_magazine = False
        for epub_path in sorted_epub_paths:
            logger.info(f"  尝试处理文件: {epub_path.name}")
            articles = process_epub_file(epub_path)
            
            if articles:
                logger.info(f"  [成功] 在文件 {epub_path.name} 中找到 {len(articles)} 篇有效文章。")
                
                for i, article_content in enumerate(articles):
                    corpus = articles[:]
                    title = generate_title_from_content(article_content, corpus)
                    author_match = re.search(r'(?:By|by|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z\'-]+){1,3})', article_content[:600])
                    author = author_match.group(1).strip() if author_match else "Source"
                    stem = f"{magazine_name.replace(' ', '_')}_{epub_path.stem.replace(' ', '_')}"
                    output_path = ARTICLES_DIR / MAGAZINES[magazine_name]['topic'] / f"{stem}_art{i+1}.md"
                    save_article(output_path, article_content, title, author)
                    total_articles_extracted += 1
                    logger.info(f"    -> 已保存: {output_path.name}")
                
                articles_processed_for_this_magazine = True
                break # 成功处理了一个文件，就跳出循环
            else:
                logger.warning(f"  [跳过] 文件 {epub_path.name} 未提取到有效文章，尝试下一个...")

        if not articles_processed_for_this_magazine:
            logger.error(f"  [错误] 遍历完所有文件后，仍未能为《{magazine_name}》提取任何文章。")
                
    logger.info(f"\n--- 文章提取流程结束。共提取了 {total_articles_extracted} 篇新文章。 ---")


def generate_website():
    logger.info("--- 开始生成网站 (毛笔字体版) ---")
    WEBSITE_DIR.mkdir(exist_ok=True)
    
    ### [毛笔字体版] 霸气书法字体 + 极致透明 ###
    shared_style_and_script = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=ZCOOL+KuaiLe&family=Source+Serif+Pro:wght@400;700&display=swap');
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
    .container { max-width: 1400px; margin: 0 auto; padding: 5rem 2rem; position: relative; z-index: 1; }
    h1, .card-title { font-family: 'ZCOOL KuaiLe', cursive; }
    .card-meta, .card-footer, .read-link, .no-articles p { font-family: 'Source Serif Pro', serif; }
    .no-articles h2 { font-family: 'ZCOOL KuaiLe', cursive; }
    h1 { font-size: clamp(3.5rem, 8vw, 6rem); text-align: center; margin-bottom: 6rem; color: #fff; font-weight: 400; text-shadow: 0 0 30px rgba(0, 191, 255, 0.5); }
    .grid { display: grid; gap: 3rem; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); }
    .card {
        background: rgba(255, 255, 255, 0.02); backdrop-filter: blur(50px); -webkit-backdrop-filter: blur(50px);
        border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 20px; padding: 2.5rem;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); transition: all 0.4s ease;
        display: flex; flex-direction: column;
    }
    .card:hover {
        transform: translateY(-15px); background: rgba(255, 255, 255, 0.05);
        box-shadow: 0 20px 50px rgba(0, 127, 255, 0.2); border-color: rgba(255, 255, 255, 0.2);
    }
    .card-title { font-size: 1.8rem; font-weight: 400; line-height: 1.3; color: #f0f6fc; margin: 0 0 1rem 0; flex-grow: 1; }
    .card-meta { color: #b0c4de; font-size: 0.9rem; }
    .card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(255, 255, 255, 0.1); }
    .read-link { color:#87ceeb; text-decoration:none; font-weight: 700; font-size: 0.9rem; }
    .no-articles { background: rgba(255, 255, 255, 0.02); backdrop-filter: blur(50px); border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.1); text-align:center; padding:5rem 2rem; color: #b0c4de;}
</style></head><body><div class="container"><h1>外刊阅读</h1><div class="grid">
{% for article in articles %}<div class="card"><h3 class="card-title">{{ article.title }}</h3><p class="card-meta">{{ article.magazine }} · {{ article.reading_time }}</p><div class="card-footer"><span class="card-meta">By {{ article.author }}</span><a href="{{ article.url }}" class="read-link">阅读 →</a></div></div>{% endfor %}
</div>{% if not articles %}<div class="no-articles"><h2>未发现文章</h2><p>引擎已运行，但本次未处理新的文章。</p></div>{% endif %}</div></body></html>"""

    article_html_template = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }} | 外刊阅读</title>""" + shared_style_and_script + """
<style>
    .article-container {
        max-width: 720px; margin: 6rem auto; padding: clamp(3rem, 6vw, 5rem);
        background: rgba(255, 255, 255, 0.03); backdrop-filter: blur(50px); -webkit-backdrop-filter: blur(50px);
        border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.1);
        position: relative; z-index: 1; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
    }
    .back-link, .article-meta, h1 { font-family: 'ZCOOL KuaiLe', cursive; }
    .article-body { font-family: 'Source Serif Pro', serif; }
    .back-link { display: inline-block; margin-bottom: 3rem; text-decoration: none; color: #b0c4de; transition: color 0.3s; font-size: 1.2rem; } .back-link:hover { color: #87ceeb; }
    h1 { font-size: clamp(2.5rem, 7vw, 4rem); line-height: 1.2; color: #fff; margin:0; font-weight: 400; }
    .article-meta { color: #b0c4de; margin: 2rem 0 3rem 0; border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 2rem; font-size: 1rem; }
    .article-body { font-size: 1.15rem; line-height: 2; color: #d1d9e0; }
    .article-body p { margin: 0 0 1.75em 0; }
</style></head><body><div class="article-container"><a href="index.html" class="back-link">← 返回列表</a><h1>{{ title }}</h1><p class="article-meta">By {{ author }} · From {{ magazine }} · {{ reading_time }}</p><div class="article-body">{{ content }}</div></div></body></html>"""

    articles_data = []
    md_files = glob.glob(str(ARTICLES_DIR / '**/*.md'), recursive=True)
    logger.info(f"找到 {len(md_files)} 个 Markdown 文件用于生成网页。")
    for md_file_path in md_files:
        try:
            md_file = Path(md_file_path)
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
            logger.error(f"生成网页 {md_file_path} 失败: {e}")
    
    articles_data.sort(key=lambda x: (x['magazine'], x['title']))
    (WEBSITE_DIR / "index.html").write_text(jinja2.Template(index_template_str).render(articles=articles_data), encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info("--- 网站生成结束 ---")

if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
