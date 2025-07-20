import logging
import os
import sys
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup
import markdown2

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)

# 【专家方案】通过环境变量获取工作区根目录，这是最可靠的方法
GITHUB_WORKSPACE = os.getenv('GITHUB_WORKSPACE')
if not GITHUB_WORKSPACE:
    logging.error("错误: GITHUB_WORKSPACE 环境变量未设置。无法继续。")
    sys.exit(1)

BASE_DIR = Path(GITHUB_WORKSPACE)
logging.info(f"[*] 工作区基础目录 (BASE_DIR): {BASE_DIR}")

# 基于绝对路径定义源和目标
SRC = BASE_DIR / "source_repo_1/01_economist"
# 输出路径也使用绝对路径
DST_ARTICLES = BASE_DIR / "local_repo/docs/articles"
DST_SITE = BASE_DIR / "local_repo/docs"


def epub_to_md(epub_path: Path, out_dir: Path):
    """将单个 EPUB 文件转换为 Markdown 文件。"""
    try:
        book = epub.read_epub(epub_path)
        md_parts = [BeautifulSoup(item.get_body_content(), 'lxml').get_text('\n') for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)]
        md_text = '\n\n'.join(md_parts)
        out_file = out_dir / (epub_path.stem + '.md')
        out_file.write_text(md_text, encoding='utf-8')
        logging.info(f'✔︎ 转换成功: {epub_path.name}')
    except Exception as e:
        logging.error(f'✘ 处理失败 {epub_path.name}: {e}')

def generate_website(articles_dir: Path, output_dir: Path):
    """根据生成的 .md 文件创建一个简单的 HTML 网站。"""
    if not articles_dir.is_dir():
        logging.warning(f"文章目录 {articles_dir} 不存在，无法生成网站。")
        # 【最终保险】即使没有文章，也创建一个空的 index.html
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "index.html").write_text("<h1>暂无文章</h1>", encoding='utf-8')
        return

    articles = [{'title': md_file.stem, 'url': f"articles/{md_file.stem}.html"} for md_file in articles_dir.glob('*.md')]
    
    # 为每篇文章生成一个单独的 HTML 页面
    for md_file in articles_dir.glob('*.md'):
        html_article_path = output_dir / "articles" / f"{md_file.stem}.html"
        html_article_path.parent.mkdir(exist_ok=True)
        html_content = f"<!DOCTYPE html><html><head><title>{md_file.stem}</title></head><body><h1>{md_file.stem}</h1>"
        html_content += markdown2.markdown(md_file.read_text(encoding='utf-8'))
        html_content += '<br/><a href="../index.html">返回列表</a></body></html>'
        html_article_path.write_text(html_content, encoding='utf-8')

    # 生成首页
    index_content = "<html><head><title>Articles</title></head><body><h1>文章列表</h1><ul>"
    for article in sorted(articles, key=lambda x: x['title']):
        index_content += f'<li><a href="{article["url"]}">{article["title"]}</a></li>'
    index_content += "</ul></body></html>"
    (output_dir / "index.html").write_text(index_content, encoding='utf-8')
    logging.info(f'✔︎ 生成 index.html, 包含 {len(articles)} 篇文章。')

def main():
    """主函数"""
    # 【防御性编程】在操作前验证路径
    if not SRC.is_dir():
        logging.error(f"❌ 源目录不存在: {SRC}")
        logging.info("列出工作区根目录内容以供调试:")
        for item in BASE_DIR.iterdir():
            logging.info(f"  - {item.name}")
        # 即使源目录不存在，也继续执行以生成一个空的网站，避免 Upload artifact 失败
        generate_website(DST_ARTICLES, DST_SITE)
        sys.exit(0) # 正常退出
        
    DST_ARTICLES.mkdir(parents=True, exist_ok=True)

    files = list(SRC.glob('*.epub'))
    logging.info(f'在 {SRC} 中找到 {len(files)} 个 EPUB 文件。')
    
    if not files:
        logging.warning("在源目录中未找到 .epub 文件。")

    for f in files:
        epub_to_md(f, DST_ARTICLES)
    
    generate_website(DST_ARTICLES, DST_SITE)
    
    logging.info("✅ 脚本执行完毕。")

if __name__ == '__main__':
    main()
