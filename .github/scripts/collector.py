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

# ==============================================================================
# 1. 配置和初始化
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

def setup_nltk():
    nltk_data_path = Path.cwd() / "nltk_data"
    nltk_data_path.mkdir(exist_ok=True)
    nltk.data.path.append(str(nltk_data_path))
    required_packages = ['punkt']
    for package_id in required_packages:
        try:
            nltk.data.find(f'tokenizers/{package_id}')
        except LookupError:
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

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================
def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    (ARTICLES_DIR / "processed").mkdir(exist_ok=True)

### [最终优化] 提取原始标题 ###
def process_epub_file(epub_path):
    """
    从EPUB中提取文章，每篇文章包含其原始标题和正文。
    返回一个字典列表: [{'title': '...', 'author': '...', 'content': '...'}]
    """
    articles_data = []
    try:
        book = epub.read_epub(str(epub_path))
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        for item in items:
            soup = BeautifulSoup(item.get_content(), 'lxml')
            
            # 1. 提取原始标题 (按 h1, h2, h3 优先级)
            title_tag = soup.find('h1') or soup.find('h2') or soup.find('h3')
            title = title_tag.get_text(strip=True) if title_tag else None
            
            # 如果没有标题，或者标题是“非文章”关键词，则跳过
            if not title or any(kw in title.lower() for kw in NON_ARTICLE_KEYWORDS):
                continue

            # 2. 提取段落作为正文
            paragraphs = soup.find_all('p')
            if len(paragraphs) < 5: continue
            
            text_from_paragraphs = [p.get_text(strip=True) for p in paragraphs]
            content = "\n\n".join(p for p in text_from_paragraphs if p)

            if not (200 < len(content.split()) < 5000):
                 continue
            
            # 3. 提取作者
            # 从正文开头搜索，因为作者信息通常在标题之后
            author_match = re.search(r'(?:By|by|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z\'-]+){1,3})', content[:500])
            author = author_match.group(1).strip() if author_match else "N/A"
            
            articles_data.append({
                "title": title,
                "author": author,
                "content": content
            })

    except Exception as e:
        logger.error(f"  解析EPUB {epub_path.name} 出错: {e}", exc_info=False)
    return articles_data


def save_article(output_path, article_data, magazine):
    word_count = len(article_data['content'].split())
    reading_time = f"~{max(1, round(word_count / 230))} min read"
    safe_title = article_data['title'].replace('"', "'")
    frontmatter = (
        f'---\n'
        f'title: "{safe_title}"\n'
        f'author: "{article_data["author"]}"\n'
        f'magazine: "{magazine}"\n'
        f'words: {word_count}\n'
        f'reading_time: "{reading_time}"\n'
        f'---\n\n'
    )
    output_path.write_text(frontmatter + article_data['content'], encoding="utf-8")

def extract_date_from_path(path):
    match = re.search(r'(\d{4}[-.]\d{2}[-.]\d{2})', path.name)
    if match: return match.group(1).replace('-', '.')
    return "1970.01.01"

def process_all_magazines():
    logger.info("--- 开始文章提取流程 (最终完美版) ---")
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
            articles_data = process_epub_file(epub_path)
            
            if articles_data:
                logger.info(f"  [成功] 在文件 {epub_path.name} 中找到 {len(articles_data)} 篇有效文章。")
                for i, article in enumerate(articles_data):
                    stem = f"{magazine_name.replace(' ', '_')}_{epub_path.stem.replace(' ', '_')}"
                    output_path = ARTICLES_DIR / "processed" / f"{stem}_art{i+1}.md"
                    save_article(output_path, article, magazine_name)
                    total_articles_extracted += 1
                    logger.info(f"    -> 已保存: {article['title']} (作者: {article['author']})")
                break 
            else:
                logger.warning(f"  [跳过] 文件 {epub_path.name} 未提取到有效文章，尝试下一个...")
                
    logger.info(f"\n--- 文章提取流程结束。共提取了 {total_articles_extracted} 篇新文章。 ---")


def generate_website():
    logger.info("--- 开始生成网站 (最终完美版) ---")
    WEBSITE_DIR.mkdir(exist_ok=True)
    shared_style_and_script = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=ZCOOL+XiaoWei&family=Noto+Serif+SC:wght@400;700&display=swap');
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
    body, h1, h2, h3, p, span, a, div { font-family: 'ZCOOL XiaoWei', 'Noto Serif SC', serif; }
    .container { max-width: 1400px; margin: 0 auto; padding: 5rem 2rem; position: relative; z-index: 1; }
    h1 { font-size: clamp(3.5rem, 8vw, 6rem); text-align: center; margin-bottom: 6rem; color: #fff; font-weight: 400; text-shadow: 0 0 30px rgba(0, 191, 255, 0.5); }
    .grid { display: grid; gap: 3rem; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); }
    .card {
        background: rgba(13, 22, 38, 0.3); backdrop-filter: blur(50px); -webkit-backdrop-filter: blur(50px);
        border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 20px; padding: 2.5rem;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); transition: all 0.4s ease; display: flex; flex-direction: column;
    }
    .card:hover { transform: translateY(-15px); background: rgba(20, 35, 58, 0.5); box-shadow: 0 20px 50px rgba(0, 127, 255, 0.2); border-color: rgba(255, 255, 255, 0.15); }
    .card-title { font-size: 1.6rem; font-weight: 400; line-height: 1.4; color: #f0f6fc; margin: 0 0 1rem 0; flex-grow: 1; }
    .card-meta { font-family: 'Noto Serif SC', serif; color: #b0c4de; font-size: 0.9rem; }
    .card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(255, 255, 255, 0.1); }
    .read-link { color:#87ceeb; text-decoration:none; font-weight: 700; font-size: 0.9rem; }
    .no-articles { background: rgba(13, 22, 38, 0.3); backdrop-filter: blur(50px); border-radius: 20px; text-align:center; padding:5rem 2rem; }
</style></head><body><div class="container"><h1>外刊阅读</h1><div class="grid">
{% for article in articles %}<div class="card"><h3 class="card-title">{{ article.title }}</h3><p class="card-meta">{{ article.magazine }} · {{ article.reading_time }}</p><div class="card-footer"><span class="card-meta">By {{ article.author }}</span><a href="{{ article.url }}" class="read-link">阅读 →</a></div></div>{% endfor %}
</div>{% if not articles %}<div class="no-articles"><h2>未发现文章</h2><p>引擎已运行，但本次未处理新的文章。</p></div>{% endif %}</div></body></html>"""
    article_html_template = """
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }} | 外刊阅读</title>""" + shared_style_and_script + """
<style>
    .article-container {
        max-width: 760px; margin: 6rem auto; padding: clamp(3rem, 6vw, 5rem);
        background: rgba(13, 22, 38, 0.5); backdrop-filter: blur(50px); -webkit-backdrop-filter: blur(50px);
        border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.1); position: relative; z-index: 1; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
    }
    .back-link, h1 { font-family: 'ZCOOL XiaoWei', sans-serif; }
    .article-meta, .article-body { font-family: 'Noto Serif SC', serif; }
    .back-link { display: inline-block; margin-bottom: 3rem; text-decoration: none; color: #b0c4de; transition: color 0.3s; font-size: 1.2rem; } .back-link:hover { color: #87ceeb; }
    h1 { font-size: clamp(2.5rem, 7vw, 3.8rem); line-height: 1.3; color: #fff; margin:0; font-weight: 400; }
    .article-meta { color: #b0c4de; margin: 2rem 0 3rem 0; border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 2rem; font-size: 1rem; }
    .article-body { font-size: 1.15rem; line-height: 2.1; color: #dce3ec; }
    .article-body p { margin: 0 0 1.75em 0; }
</style></head><body><div class="article-container"><a href="index.html" class="back-link">← 返回列表</a><h1>{{ title }}</h1><p class="article-meta">By {{ author }} · From {{ magazine }} · {{ reading_time }}</p><div class="article-body">{{ content }}</div></div></body></html>"""
    
    articles_data = []
    md_files = glob.glob(str(ARTICLES_DIR / 'processed' / '*.md'), recursive=True)
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
            title, author, magazine, reading_time = [get_meta(k, frontmatter) for k in ['title', 'author', 'magazine', 'reading_time']]
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
