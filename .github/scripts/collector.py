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

# ==============================================================================
# 1. 配置区域 (Configuration)
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SOURCE_REPO_PATH = Path("source_repo")
MAGAZINES = {
    "economist": {"folder": "01_economist", "topic": "world_affairs"},
    "wired": {"folder": "05_wired", "topic": "technology"},
    "atlantic": {"folder": "04_atlantic", "topic": "world_affairs"}
}
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")

# ==============================================================================
# 2. 核心功能函数 (Core Functions)
# ==============================================================================

def setup_directories():
    """准备好工作需要的所有文件夹。"""
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def split_text_into_articles(text):
    """【智能切分】将大段文字切分成独立文章。"""
    potential_articles = re.split(r'\n\s*\n\s*\n+', text)
    articles = [p.strip() for p in potential_articles if len(p.split()) > 150]
    if not articles and len(text.split()) > 200:
        logger.info("未识别出文章边界，尝试按句子数量切分。")
        try:
            sentences = nltk.sent_tokenize(text)
            chunk_size = 30
            for i in range(0, len(sentences), chunk_size):
                articles.append(" ".join(sentences[i:i+chunk_size]))
        except Exception as e:
            logger.error(f"NLTK切分句子出错: {e}")
    return articles

def process_all_magazines():
    """主生产线：遍历、下载、处理所有杂志文件。"""
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!")
        return

    try: nltk.data.find('tokenizers/punkt')
    except LookupError: nltk.download('punkt')
    
    # 【新增】用来存储已处理文章的“指纹”，防止重复
    processed_articles_fingerprints = set()

    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        topic = info["topic"]
        logger.info(f"--- 正在扫描: {source_folder} ---")
        if not source_folder.is_dir(): continue

        for file_path in source_folder.rglob('*.epub'):
            if magazine_name in file_path.name.lower():
                base_md_filename = f"{file_path.stem}_art_1.md"
                check_path = ARTICLES_DIR / topic / base_md_filename
                if check_path.exists(): continue

                logger.info(f"发现并处理新杂志: {file_path.name}")
                try:
                    full_text = extract_text_from_epub(str(file_path))
                    if full_text:
                        articles_in_magazine = split_text_into_articles(full_text)
                        logger.info(f"从《{magazine_name.capitalize()}》中识别出 {len(articles_in_magazine)} 篇独立文章。")
                        
                        for i, article_content in enumerate(articles_in_magazine):
                            # 【新增去重逻辑】
                            fingerprint = article_content.strip()[:60]
                            if fingerprint in processed_articles_fingerprints: continue
                            processed_articles_fingerprints.add(fingerprint)

                            first_line = article_content.strip().split('\n')[0]
                            title = first_line.replace('#', '').strip()
                            if len(title) > 90 or len(title) < 5: title = " ".join(article_content.split()[:12])
                            
                            article_md_filename = f"{file_path.stem}_art_{i+1}.md"
                            article_output_path = ARTICLES_DIR / topic / article_md_filename
                            save_article(article_output_path, article_content, title)
                except Exception as e:
                    logger.error(f"处理文件 {file_path.name} 时出错: {e}")

def extract_text_from_epub(epub_path):
    """从EPUB文件中提取纯文本。"""
    try:
        book = epub.read_epub(epub_path)
        return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e: logger.error(f"提取EPUB失败 {epub_path}: {e}"); return ""

def save_article(output_path, text_content, title):
    """保存单篇文章为 .md 文件。"""
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\n---\n\n{text_content}")
    logger.info(f"已保存: {output_path.name}")

def generate_website():
    """【Gemini美学界面】生成全新风格的网站。"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Foreign Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #f7f7f7; color: #1a1a1a; margin: 0; padding: 4rem 2rem; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { font-size: 3.5rem; font-weight: 700; text-align: center; margin-bottom: 4rem;
             background: -webkit-linear-gradient(45deg, #4f4f4f, #1a1a1a); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); }
        .card { background-color: #ffffff; border-radius: 16px; overflow: hidden;
                box-shadow: 0 8px 30px rgba(0,0,0,0.08); transition: transform 0.3s ease, box-shadow 0.3s ease; display: flex; flex-direction: column; }
        .card:hover { transform: translateY(-5px); box-shadow: 0 12px 40px rgba(0,0,0,0.12); }
        .card-content { padding: 1.5rem; flex-grow: 1; display: flex; flex-direction: column; }
        .card-title { font-size: 1.25rem; font-weight: 500; margin: 0 0 0.75rem 0; color: #333; }
        .card-preview { font-size: 1rem; line-height: 1.6; color: #555; margin-bottom: 1.5rem; flex-grow: 1; }
        .card-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 1rem; border-top: 1px solid #eee; }
        .meta-info { font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
        .read-more-btn { font-size: 0.9rem; font-weight: 500; color: #fff; background-color: #333;
                         padding: 0.6rem 1.2rem; border-radius: 8px; text-decoration: none; transition: background-color 0.3s ease; }
        .read-more-btn:hover { background-color: #000; }
        .no-articles { text-align: center; padding: 4rem; background-color: #fff; border-radius: 16px; }
    </style></head>
    <body><div class="container"><h1>Foreign Journals</h1><div class="grid">
    {% for article in articles %}
        <div class="card">
            <div class="card-content">
                <h5 class="card-title">{{ article.title }}</h5>
                <p class="card-preview">{{ article.preview }}...</p>
                <div class="card-footer">
                    <span class="meta-info">{{ article.magazine }} | {{ article.topic }}</span>
                    <a href="{{ article.url }}" class="read-more-btn">Read Article</a>
                </div>
            </div>
        </div>
    {% endfor %}
    </div>{% if not articles %}<div class="no-articles"><h2>暂无文章</h2><p>系统将自动在下个周期更新，或请检查上游仓库是否有新内容。</p></div>{% endif %}
    </div></body></html>
    """
    article_html_template = '''
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{{ title }}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Lora:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Lora', serif; background-color: #fdfdfd; color: #1a1a1a; margin: 0; }
        .container { max-width: 720px; margin: 5rem auto; padding: 0 2rem; }
        .back-link { font-family: 'Inter', sans-serif; display: inline-block; margin-bottom: 3rem; text-decoration: none; color: #555; }
        .back-link:hover { text-decoration: underline; }
        h1 { font-family: 'Inter', sans-serif; font-size: 2.8rem; font-weight: 700; line-height: 1.2; margin-bottom: 1rem; }
        .article-meta { font-family: 'Inter', sans-serif; color: #888; margin-bottom: 3rem; }
        .article-body { font-size: 1.2rem; line-height: 2; }
        .article-body p { margin-bottom: 1.5rem; }
    </style></head>
    <body><div class="container">
        <a href="index.html" class="back-link">← Back to List</a>
        <h1>{{ title }}</h1>
        <p class="article-meta">From {{ magazine }} | Topic: {{ topic }}</p>
        <div class="article-body">{{ content }}</div>
    </div></body></html>
    '''
    
    articles_data = []
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            try:
                with md_file.open('r', encoding='utf-8') as f: content_lines = f.readlines()
                title = content_lines[1].replace('title: ', '').strip()
                content = "".join(content_lines[3:])
                magazine_match = re.match(r'([a-zA-Z]+)', md_file.name)
                magazine = magazine_match.group(1).capitalize() if magazine_match else "Unknown"
                article_filename = f"{md_file.stem}.html"
                article_path = WEBSITE_DIR / article_filename
                
                article_template = jinja2.Template(article_html_template)
                article_html = article_template.render(title=title, content=markdown2.markdown(content), magazine=magazine, topic=topic_dir.name.capitalize())
                article_path.write_text(article_html, encoding='utf-8')
                
                articles_data.append({"title": title, "preview": re.sub(r'\s+', ' ', content[:200]), "url": article_filename, "topic": topic_dir.name, "magazine": magazine})
            except Exception as e:
                logger.error(f"生成网页时处理文件 {md_file} 失败: {e}")
                continue

    articles_data.sort(key=lambda x: x['title'])
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data)
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()

    if articles_data: logger.info(f"网站生成完成，总共包含 {len(articles_data)} 篇文章。")
    else: logger.info("网站生成完成，但没有找到任何文章。")

# ==============================================================================
# 3. 主程序入口 (Main Execution)
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
