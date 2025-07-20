import logging
import os
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup
import markdown2

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 【专家建议】动态、绝对地计算路径，确保万无一失
# BASE_DIR 指向工作区的根目录 (e.g., /home/runner/work/magazine-collector/magazine-collector)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SRC 指向我们检出的外部仓库
SRC = BASE_DIR / "source_repo_1/01_economist"
# DST 指向我们自己仓库的输出目录
DST = Path("docs/articles") # 脚本在 local_repo 下运行，所以这里的 docs 是相对于 local_repo 的

def epub_to_md(epub_path: Path, out_dir: Path):
    """将单个 EPUB 文件转换为 Markdown 文件。"""
    try:
        book = epub.read_epub(epub_path)
        md_parts = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_body_content(), 'lxml')
            md_parts.append(soup.get_text('\n'))
        
        md_text = '\n\n'.join(md_parts)
        out_file = out_dir / (epub_path.stem + '.md')
        out_file.write_text(md_text, encoding='utf-8')
        logging.info(f'✔︎ Success: Converted {epub_path.name} to {out_file.name}')
    except Exception as e:
        logging.error(f'✘ Failed to process {epub_path.name}: {e}')

def generate_index_html(articles_dir: Path, output_dir: Path):
    """根据生成的 .md 文件创建一个简单的 HTML 首页和详情页。"""
    articles = []
    for md_file in articles_dir.glob('*.md'):
        articles.append({
            'title': md_file.stem,
            'url': f"articles/{md_file.stem}.html" # 修正了详情页链接
        })

    # 为每篇文章生成一个单独的 HTML 页面
    for md_file in articles_dir.glob('*.md'):
        html_article_path = output_dir / "articles" / f"{md_file.stem}.html"
        html_article_path.parent.mkdir(exist_ok=True)
        html_content = f"<!DOCTYPE html><html><head><title>{md_file.stem}</title></head><body>"
        html_content += f"<h1>{md_file.stem}</h1>"
        html_content += markdown2.markdown(md_file.read_text(encoding='utf-8'))
        html_content += '<br/><a href="../index.html">Back to List</a>' # 修正了返回链接
        html_content += "</body></html>"
        html_article_path.write_text(html_content, encoding='utf-8')

    # 生成首页
    index_content = "<html><head><title>Articles</title></head><body><h1>Article List</h1><ul>"
    for article in sorted(articles, key=lambda x: x['title']):
        index_content += f'<li><a href="{article["url"]}">{article["title"]}</a></li>'
    index_content += "</ul></body></html>"
    (output_dir / "index.html").write_text(index_content, encoding='utf-8')
    logging.info(f'✔︎ Generated index.html with {len(articles)} articles.')

def main():
    """主函数"""
    DST.mkdir(parents=True, exist_ok=True)
    
    if not SRC.is_dir():
        logging.error(f"Source directory not found: {SRC}")
        logging.info("Current directory structure:")
        os.system(f"ls -R {BASE_DIR}")
        return

    files = list(SRC.glob('*.epub'))
    logging.info(f'Found {len(files)} EPUB file(s) in {SRC}')
    
    for f in files:
        epub_to_md(f, DST)
    
    if files:
        generate_index_html(DST, Path("docs"))

if __name__ == '__main__':
    main()
