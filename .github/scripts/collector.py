import logging
import os
import sys
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup
import markdown2

# 设置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)

# --- 路径管理：从环境变量中获取 ---
SOURCE_REPO_PATH_STR = os.getenv('SOURCE_REPO_PATH')
OUTPUT_PATH_STR = os.getenv('OUTPUT_PATH')

if not SOURCE_REPO_PATH_STR or not OUTPUT_PATH_STR:
    logging.error("环境变量 'SOURCE_REPO_PATH' 或 'OUTPUT_PATH' 未设置。")
    sys.exit(1)

SRC_BASE = Path(SOURCE_REPO_PATH_STR)
DST_BASE = Path(OUTPUT_PATH_STR)
SRC = SRC_BASE / "01_economist"
DST_ARTICLES = DST_BASE / "articles"

logging.info(f"源文件目录: {SRC}")
logging.info(f"文章输出目录: {DST_ARTICLES}")
logging.info(f"静态网站根目录: {DST_BASE}")

def epub_to_md(epub_path: Path, out_dir: Path):
    """将单个 EPUB 文件转换为多个 Markdown 文章"""
    try:
        if not epub_path.is_file(): return
        book = epub.read_epub(epub_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        for item in book.get_items_of_type(epub.EpubHtml):
            content = item.get_content()
            soup = BeautifulSoup(content, 'html.parser')
            title_tag = soup.find('h1') or soup.find('h2')
            file_name_base = "".join(x for x in (title_tag.text if title_tag else Path(item.get_name()).stem) if x.isalnum() or x in " _-").strip()
            md_content = markdown2.markdown(str(soup), extras=["metadata", "fenced-code-blocks"])
            md_file_path = out_dir / f"{file_name_base}.md"
            md_file_path.write_text(md_content, encoding='utf-8')
            logging.info(f"已转换 '{epub_path.name}' 中的 '{item.get_name()}'")
    except Exception as e:
        logging.error(f"处理 EPUB 文件 '{epub_path.name}' 时发生错误: {e}")

def generate_website(articles_dir: Path, output_dir: Path):
    """根据 Markdown 文章生成一个简单的静态网站"""
    if not articles_dir.exists():
        logging.warning("文章目录不存在，跳过网站生成。")
        (output_dir / "index.html").write_text("<h1>暂无文章</h1>", encoding='utf-8')
        return

    index_html_path = output_dir / "index.html"
    html_content = "<html><body><h1>文章列表</h1><ul>"
    article_files = sorted(list(articles_dir.rglob("*.md")))
    if not article_files:
        html_content += "<li>No articles found.</li>"
    else:
        for md_file in article_files:
            relative_path = md_file.relative_to(output_dir)
            html_content += f'<li><a href="{relative_path}">{md_file.stem}</a></li>\n'
    html_content += "</ul></body></html>"
    index_html_path.write_text(html_content, encoding='utf-8')
    logging.info(f"网站索引页已生成: {index_html_path}")

def main():
    """主执行函数"""
    logging.info("--- 开始执行收集器脚本 ---")
    DST_ARTICLES.mkdir(parents=True, exist_ok=True)
    if not SRC.exists() or not SRC.is_dir():
        logging.error(f"源目录 '{SRC}' 不存在或不是一个目录。")
        sys.exit(1)

    epub_files = list(SRC.glob("*.epub"))
    if not epub_files:
        logging.warning(f"在 '{SRC}' 中未找到 EPUB 文件。")
    else:
        for epub_file in epub_files:
            magazine_name = epub_file.stem
            article_output_dir = DST_ARTICLES / magazine_name
            epub_to_md(epub_file, article_output_dir)
    generate_website(DST_ARTICLES, DST_BASE)
    logging.info("--- 收集器脚本执行完毕 ---")

if __name__ == '__main__':
    main()
