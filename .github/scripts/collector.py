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

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 配置
SOURCE_REPO_PATH = Path("source_repo")
MAGAZINES = {
    "economist": {"folder": "01_economist", "topic": "world_affairs"},
    "wired": {"folder": "05_wired", "topic": "technology"},
    "atlantic": {"folder": "04_atlantic", "topic": "world_affairs"}
}
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")

def setup_directories():
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def split_text_into_articles(text):
    potential_articles = re.split(r'\n\s*\n\s*\n+', text)
    articles = []
    for article_text in potential_articles:
        article_text = article_text.strip()
        if len(article_text.split()) > 150:
            articles.append(article_text)
    if not articles and len(text.split()) > 200:
        logger.info("未识别出文章边界，将尝试按句子数量切分。")
        try:
            sentences = nltk.sent_tokenize(text)
            chunk_size = 30
            for i in range(0, len(sentences), chunk_size):
                articles.append(" ".join(sentences[i:i+chunk_size]))
        except Exception as e:
            logger.error(f"使用 NLTK 切分句子时出错: {e}")
    return articles

def process_all_magazines():
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到!")
        return

    try: nltk.data.find('tokenizers/punkt')
    except LookupError: nltk.download('punkt')

    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        topic = info["topic"]
        logger.info(f"--- 正在扫描: {source_folder} ---")

        if not source_folder.is_dir():
            logger.warning(f"找不到目录: {source_folder}")
            continue

        for file_path in source_folder.rglob('*.epub'):
            if magazine_name in file_path.name.lower():
                base_md_filename = f"{file_path.stem}_art_1.md"
                check_path = ARTICLES_DIR / topic / base_md_filename
                if check_path.exists(): continue

                logger.info(f"发现并处理新杂志文件: {file_path.name}")
                try:
                    full_text = extract_text_from_epub(str(file_path))
                    if full_text:
                        articles_in_magazine = split_text_into_articles(full_text)
                        logger.info(f"从《{magazine_name.capitalize()}》中成功识别出 {len(articles_in_magazine)} 篇独立文章。")
                        for i, article_content in enumerate(articles_in_magazine):
                            first_line = article_content.strip().split('\n')[0]
                            title = first_line.replace('#', '').strip()
                            if len(title) > 80: title = " ".join(title.split()[:10])
                            article_md_filename = f"{file_path.stem}_art_{i+1}.md"
                            article_output_path = ARTICLES_DIR / topic / article_md_filename
                            save_article(article_output_path, article_content, title)
                except Exception as e:
                    logger.error(f"处理文件 {file_path.name} 时出错: {e}")

def extract_text_from_epub(epub_path):
    try:
        book = epub.read_epub(epub_path)
        return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e:
        logger.error(f"提取 EPUB 失败 {epub_path}: {e}")
        return ""

def save_article(output_path, text_content, title):
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\n---\n\n{text_content}")
    logger.info(f"已保存文章到: {output_path}")

def generate_website():
    WEBSITE_DIR.mkdir(exist_ok=True)
    # ↓↓↓ 这是修正后的 HTML 模板 ↓↓↓
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN" data-theme="light"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>外刊精读 | Article Collector</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
    <style>
      :root { --font-size: 18px; --card-background-color: #ffffff; --card-border-color: #e1e4e8;}
      main.container { padding: 1rem; max-width: 1200px; }
      h1 { text-align: center; margin-bottom: 2rem; }
      .grid { display: grid; grid-gap: 2rem; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
      article { border-radius: var(--border-radius); border: 1px solid var(--card-border-color);
                box-shadow: var(--card-box-shadow); display: flex; flex-direction: column; height: 100%; }
      article header { padding: 1rem 1.5rem; border-bottom: 1px solid var(--card-border-color); }
      article p { padding: 0 1.5rem; color: var(--secondary); flex-grow: 1; }
      article footer { padding: 1rem 1.5rem; border-top: 1px solid var(--card-border-color); display: flex; justify-content: space-between; align-items: center; }
    </style></head>
    <body><main class="container"><h1>外刊精读</h1><div class="grid">
    {% for article in articles %}
        <article>
          <header><h5>{{ article.title }}</h5></header>
          <p>{{ article.preview }}...</p>
          <footer>
            <small>来源: {{ article.magazine|capitalize }} | 主题: {{ article.topic.capitalize() }}</small>
            <a href="{{ article.url }}" role="button" class="contrast outline">阅读全文</a>
          </footer>
        </article>
    {% endfor %}
    {% if not articles %}<div class="container-fluid"><article><h4>暂无文章</h4><p>系统将自动在下个周期更新，或请检查上游仓库是否有新内容。</p></article></div>{% endif %}
    </div></main></body></html>
    """
    
    articles_data = []
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            try:
                with md_file.open('r', encoding='utf-8') as f: content_lines = f.readlines()
                title = content_lines[1].replace('title: ', '').strip()
                content = "".join(content_lines[3:])
                magazine_match = re.match(r'([a-zA-Z]+)', md_file.name)
                magazine = magazine_match.group(1) if magazine_match else "Unknown"
                article_filename = f"{md_file.stem}.html"
                article_path = WEBSITE_DIR / article_filename
                
                article_html = f'''
                <!DOCTYPE html><html lang="zh-CN" data-theme="light"><head><meta charset="UTF-8"><title>{title}</title>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
                <style>main.container{{max-width:800px;padding:2rem 1rem;}}article header{{text-align:center;margin-bottom:2rem;}}.article-body p{{line-height:1.8;font-size:1.1rem;}}nav{{margin-bottom:2rem;}}</style></head>
                <body><main class="container"><nav><a href="index.html">‹ 返回列表</a></nav><article><header><h2>{title}</h2></header>
                <div class="article-body">{markdown2.markdown(content)}</div></article></main></body></html>
                '''
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

if __name__ == "__main__":
    setup_directories()
    process_all_magazines()
    generate_website()
