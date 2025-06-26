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

# 配置日志，让我们能看懂机器人的工作报告
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 源仓库在本地的路径 (由 .yml 文件中的 git clone 命令创建)
SOURCE_REPO_PATH = Path("source_repo")

# 定义我们要关注的杂志和它们的存放位置
MAGAZINES = {
    "economist": {"folder": "01_economist", "topic": "world_affairs"},
    "wired": {"folder": "05_wired", "topic": "technology"},
    "atlantic": {"folder": "04_atlantic", "topic": "world_affairs"}
}

# 定义我们最终的成品存放目录
ARTICLES_DIR = Path("articles")
WEBSITE_DIR = Path("docs")


# ==============================================================================
# 2. 核心功能函数 (Core Functions)
# ==============================================================================

def setup_directories():
    """在开始工作前，确保所有需要的文件夹都已创建好。"""
    ARTICLES_DIR.mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)
    for info in MAGAZINES.values():
        (ARTICLES_DIR / info['topic']).mkdir(exist_ok=True)

def split_text_into_articles(text):
    """
    【本次升级核心】智能拆分文章的函数。
    它会尝试用多种方法，把一本杂志的全部文字，切分成一篇篇独立的美文。
    """
    # 首先，尝试用连续的多个换行符作为文章的分割标志
    potential_articles = re.split(r'\n\s*\n\s*\n+', text)
    
    articles = []
    for article_text in potential_articles:
        article_text = article_text.strip()
        # 过滤掉太短的、可能是目录或版权声明的文本块
        if len(article_text.split()) > 150: # 文章至少要有150个单词
            articles.append(article_text)
            
    # 如果上面的方法效果不佳 (比如整本杂志都没有明显分割)，就启用备用方案
    if not articles and len(text.split()) > 200:
        logger.info("未识别出清晰的文章边界，将尝试按句子数量切分。")
        # 引入自然语言处理工具包 nltk 来做更精确的句子切分
        try:
            sentences = nltk.sent_tokenize(text)
            # 每 20-40 个句子大约构成一篇中等长度的文章
            chunk_size = 30
            for i in range(0, len(sentences), chunk_size):
                articles.append(" ".join(sentences[i:i+chunk_size]))
        except Exception as e:
            logger.error(f"使用 NLTK 切分句子时出错: {e}")

    return articles

def process_all_magazines():
    """
    这是主要的“生产线”函数。
    它会遍历所有杂志，深入到下载好的文件夹里，找到杂志文件，
    然后交给其他函数去处理。
    """
    if not SOURCE_REPO_PATH.is_dir():
        logger.error(f"源仓库目录 '{SOURCE_REPO_PATH}' 未找到! 机器人无法开工。")
        return

    # 确保我们的“切句子”工具包已经下载好了
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')

    for magazine_name, info in MAGAZINES.items():
        source_folder = SOURCE_REPO_PATH / info["folder"]
        topic = info["topic"]
        logger.info(f"--- 正在扫描文件夹: {source_folder} ---")

        if not source_folder.is_dir():
            logger.warning(f"找不到目录: {source_folder}, 跳过。")
            continue

        # 递归地深入所有子文件夹，寻找 .epub 文件
        for file_path in source_folder.rglob('*.epub'):
            # 使用简单的包含逻辑来匹配文件名
            if magazine_name in file_path.name.lower():
                
                # 用文件名作为唯一ID，避免重复处理
                # 我们先生成这篇文章处理后的 .md 文件应该叫什么名字
                base_md_filename = f"{file_path.stem}_art_1.md"
                check_path = ARTICLES_DIR / topic / base_md_filename
                
                # 如果第一篇文章已经存在了，我们就认为这整本杂志都处理过了，跳过
                if check_path.exists():
                    continue

                logger.info(f"发现并开始处理新杂志文件: {file_path.name}")
                
                try:
                    full_text = extract_text_from_epub(str(file_path))
                    if full_text:
                        # 【调用新功能】把整本杂志的文字拆分成多篇文章
                        articles_in_magazine = split_text_into_articles(full_text)
                        logger.info(f"从《{magazine_name.capitalize()}》中成功识别出 {len(articles_in_magazine)} 篇独立文章。")
                        
                        # 为每一篇识别出的文章保存一个 .md 文件
                        for i, article_content in enumerate(articles_in_magazine):
                            # 尝试从文章内容的第一行提取标题
                            first_line = article_content.strip().split('\n')[0]
                            title = first_line.replace('#', '').strip()
                            if len(title) > 80: # 如果第一行太长，就取前10个词
                                title = " ".join(title.split()[:10])
                            
                            article_md_filename = f"{file_path.stem}_art_{i+1}.md"
                            article_output_path = ARTICLES_DIR / topic / article_md_filename
                            
                            save_article(article_output_path, article_content, title)
                except Exception as e:
                    logger.error(f"处理文件 {file_path.name} 时出错: {e}")

def extract_text_from_epub(epub_path):
    """从电子书(EPUB)文件中提取纯文本的函数。"""
    try:
        book = epub.read_epub(epub_path)
        # 遍历书中的每一个章节(document)，用BeautifulSoup去掉HTML标签，最后拼接成一大段文字
        return "\n".join(BeautifulSoup(item.get_content(), 'html.parser').get_text() for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    except Exception as e:
        logger.error(f"提取 EPUB 文件内容失败 {epub_path}: {e}")
        return ""

def save_article(output_path, text_content, title):
    """将处理好的单篇文章内容，连同标题，保存为 .md 文件。"""
    with output_path.open("w", encoding="utf-8") as f:
        # 我们在文件开头加上一个YAML Front Matter，方便未来扩展
        f.write(f"---\n")
        f.write(f"title: {title}\n")
        f.write(f"---\n\n")
        f.write(text_content)
    logger.info(f"已保存文章到: {output_path}")

def generate_website():
    """
    【本次升级核心】生成全新“外刊风格”网站的函数。
    它会扫描所有已保存的 .md 文章，然后用一个更漂亮的模板来创建网站页面。
    """
    WEBSITE_DIR.mkdir(exist_ok=True)
    # 使用了 Pico.css 框架，界面更简洁、现代
    index_template_str = """
    <!DOCTYPE html><html lang="zh-CN" data-theme="light"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>外刊精读 | Article Collector</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
    <style>
      :root { --font-size: 18px; }
      main.container { padding: 1rem; }
      h1 { text-align: center; margin-bottom: 2rem; }
      article { border-radius: var(--border-radius); border: 1px solid var(--card-border-color);
                box-shadow: var(--card-box-shadow); margin-bottom: 2rem; }
      article header { padding: 1rem 1.5rem; background-color: var(--card-background-color); border-bottom: 1px solid var(--card-border-color); }
      article p { padding: 0 1.5rem; color: var(--secondary); }
      article footer { padding: 1rem 1.5rem; background-color: var(--card-background-color); border-top: 1px solid var(--card-border-color); display: flex; justify-content: space-between; align-items: center;}
      .grid > .card { display: flex; flex-direction: column; }
    </style></head>
    <body><main class="container"><h1>外刊精读</h1><div class="grid">
    {% for article in articles %}<div class="card"><article>
      <header><h5>{{ article.title }}</h5></header>
      <p>{{ article.preview }}...</p>
      <footer>
        <small>来源: {{ article.magazine|capitalize }} | 主题: {{ article.topic.capitalize() }}</small>
        <a href="{{ article.url }}" role="button" class="contrast outline">阅读全文</a>
      </footer>
    </article></div>{% endfor %}
    {% if not articles %}<div class="container-fluid"><article><p>暂无文章。系统将自动在下个周期更新。</p></article></div>{% endif %}
    </div></main></body></html>
    """
    
    articles_data = []
    for topic_dir in ARTICLES_DIR.iterdir():
        if not topic_dir.is_dir(): continue
        for md_file in topic_dir.glob("*.md"):
            try:
                with md_file.open('r', encoding='utf-8') as f:
                    content_lines = f.readlines()
                
                # 从 .md 文件的 front matter 中读取标题
                title = content_lines[1].replace('title: ', '').strip()
                content = "".join(content_lines[3:])
                
                magazine_match = re.match(r'([a-zA-Z]+)', md_file.name)
                magazine = magazine_match.group(1) if magazine_match else "Unknown"

                article_filename = f"{md_file.stem}.html"
                article_path = WEBSITE_DIR / article_filename
                
                # 使用新的、更适合阅读的文章页面模板
                article_html = f'''
                <!DOCTYPE html><html lang="zh-CN" data-theme="light"><head><meta charset="UTF-8"><title>{title}</title>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
                <style>main.container{{max-width:800px;padding:2rem 1rem;}}article header{{text-align:center;margin-bottom:2rem;}}.article-body p{{line-height:1.8;font-size:1.1rem;}}nav{{margin-bottom:2rem;}}</style></head>
                <body><main class="container"><nav><a href="index.html">‹ 返回列表</a></nav><article><header><h2>{title}</h2></header>
                <div class="article-body">{markdown2.markdown(content)}</div></article></main></body></html>
                '''
                article_path.write_text(article_html, encoding='utf-8')
                
                articles_data.append({
                    "title": title, "preview": re.sub(r'\s+', ' ', content[:250]), "url": article_filename,
                    "topic": topic_dir.name, "magazine": magazine,
                })
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
    # 这是程序的起点，它会按顺序调用上面的函数来完成整个工作
    setup_directories()        # 1. 准备好文件夹
    process_all_magazines()    # 2. 去生产线上加工原料（拆分文章）
    generate_website()         # 3. 把成品打包成漂亮的网站
