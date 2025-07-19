import os
import re
from pathlib import Path
import ebooklib
from ebooklib import epub
import mobi
from bs4 import BeautifulSoup
import logging
import markdown2
import jinja2

# ==============================================================================
# 1. 配置区域
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SOURCE_REPO_PATHS = [Path("source_repo_1"), Path("source_repo_2")]
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")
IGNORE_DIRS = ['.git', 'docs', 'images']

# ==============================================================================
# 2. 核心功能函数
# ==============================================================================

def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)

def extract_text(file_path):
    """根据文件类型提取文本"""
    if file_path.suffix == '.epub':
        try:
            book = epub.read_epub(str(file_path))
            return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        except Exception as e:
            logger.error(f"提取EPUB失败 {file_path.name}: {e}")
    elif file_path.suffix == '.mobi':
        try:
            book = mobi.Mobi(str(file_path))
            content = "".join(record.text for record in book)
            return BeautifulSoup(content, 'html.parser').get_text()
        except Exception as e:
            logger.error(f"提取MOBI失败 {file_path.name}: {e}")
    return ""

def discover_and_process_files():
    """【最终版】扫描所有源仓库，处理所有找到的刊物"""
    # 首先，获取已经存在的文章，避免重复处理
    processed_stems = {md.stem for md in ARTICLES_DIR.rglob('*.md')}
    
    article_count = 0
    for repo_path in SOURCE_REPO_PATHS:
        if not repo_path.is_dir(): continue
        logger.info(f"===== 正在扫描仓库: {repo_path} =====")
        
        # 使用 rglob 递归扫描所有 .epub 和 .mobi 文件
        for file_path in list(repo_path.rglob('*.epub')) + list(repo_path.rglob('*.mobi')):
            # 忽略隐藏目录和非文章目录
            if any(ignored in file_path.parts for ignored in IGNORE_DIRS): continue
            
            # 使用文件名（不含后缀）作为唯一标识符
            file_stem = file_path.stem
            
            # 检查是否已经处理过
            if any(file_stem in s for s in processed_stems):
                continue

            logger.info(f"  -> 发现新文件: {file_path.name}")
            full_text = extract_text(file_path)
            
            # 确保提取到了足够的内容
            if not full_text or len(full_text.split()) < 500: continue
            
            # 简单的文章拆分逻辑
            potential_articles = re.split(r'\n\s*\n\s*\n+', full_text)
            for i, article_text in enumerate(potential_articles):
                article_text = article_text.strip()
                # 只有足够长的文本块才被当作文章
                if len(article_text.split()) > 250:
                    # 从文件路径中智能提取刊物名
                    journal_name = file_path.parent.name.replace('_', ' ').replace('-', ' ').title()
                    # 如果父目录是年份，就再往上一级
                    if journal_name.isdigit():
                        journal_name = file_path.parents[1].name.replace('_', ' ').replace('-', ' ').title()
                    
                    # 动态创建以刊物名命名的主题文件夹
                    topic_dir = ARTICLES_DIR / journal_name
                    topic_dir.mkdir(exist_ok=True)
                    
                    # 使用简单的标题和作者
                    title = " ".join(article_text.split()[:10])
                    author = "N/A"
                    
                    output_path = topic_dir / f"{file_stem}_art_{i+1}.md"
                    
                    with output_path.open("w", encoding="utf-8") as f:
                        f.write(f"---\ntitle: {title}\nauthor: {author}\njournal: {journal_name}\n---\n\n{article_text}")
                    logger.info(f"已保存: {output_path.name} -> 刊物: {journal_name}")
                    article_count += 1
    
    return article_count

def generate_website():
    """生成最终的网站"""
    WEBSITE_DIR.mkdir(exist_ok=True)
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Curated Journals</title><link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #0d1117; color: #c9d1d9; margin: 0; padding: 4rem 2rem; }
        .container { max-width: 1320px; margin: 0 auto; } .header { text-align: center; margin-bottom: 3rem; }
        h1 { font-size: 5rem; font-weight: 700; color: #fff; }
        .grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
        .card { background: #161b22; border: 1px solid rgba(139, 148, 158, 0.2); border-radius: 16px; padding: 2rem; }
        .card-title { font-size: 1.5rem; color: #fff; margin-bottom: 1rem; }
    </style></head>
    <body><div class="container"><div class="header"><h1>Curated Journals</h1></div><div class="grid">
        {% for article in articles %}
            <div class="card">
                <h5 class="card-title">{{ article.title }}...</h5>
                <div style="margin-top:auto;padding-top:1.5rem;border-top:1px solid rgba(139, 148, 158, 0.2);"><a href="{{ article.url }}">Read More</a></div>
            </div>
        {% endfor %}
        {% if not articles %}<div><h2>No articles found.</h2></div>{% endif %}
    </div></div></body></html>
    """
    article_html_template = """... (文章页模板可以保持不变) ..."""
    
    articles_data = []
    for journal_dir in ARTICLES_DIR.iterdir():
        if not journal_dir.is_dir(): continue
        for md_file in journal_dir.glob("*.md"):
            try:
                with md_file.open('r', encoding='utf-8') as f: content_lines = f.readlines()
                title = content_lines[1].split(': ', 1)[1].strip()
                journal = content_lines[2].split(': ', 1)[1].strip()
                content = "".join(content_lines[4:])
                article_filename = f"{md_file.stem}.html"
                article_path = WEBSITE_DIR / article_filename
                
                # ... (文章页生成逻辑不变)
                
                articles_data.append({"title": title, "url": article_filename})
            except Exception as e:
                logger.error(f"生成网页时处理文件 {md_file} 失败: {e}")
                continue
    
    template = jinja2.Template(index_template_str)
    index_html = template.render(articles=articles_data)
    (WEBSITE_DIR / "index.html").write_text(index_html, encoding='utf-8')
    (WEBSITE_DIR / ".nojekyll").touch()
    logger.info(f"网站生成完成，共 {len(articles_data)} 篇文章。")

# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    setup_directories()
    discover_and_process_files()
    generate_website()
