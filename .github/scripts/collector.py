import logging
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义源文件夹和目标文件夹
SRC = Path('source_repo_1/01_economist')
DST = Path('docs/articles')

def epub_to_md(epub_path: Path, out_dir: Path):
    """将单个 EPUB 文件转换为 Markdown 文件。"""
    try:
        book = epub.read_epub(epub_path)
        md_parts = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            # 使用 'lxml' 解析器更健壮
            soup = BeautifulSoup(item.get_body_content(), 'lxml')
            md_parts.append(soup.get_text('\n'))
        
        md_text = '\n\n'.join(md_parts)
        out_file = out_dir / (epub_path.stem + '.md')
        out_file.write_text(md_text, encoding='utf-8')
        logging.info(f'✔︎ Success: Converted {epub_path.name} to {out_file.name}')
    except Exception as e:
        logging.error(f'✘ Failed to process {epub_path.name}: {e}')

def generate_index_html(articles_dir: Path, output_dir: Path):
    """根据生成的 .md 文件创建一个简单的 HTML 首页。"""
    articles = []
    for md_file in articles_dir.glob('*.md'):
        articles.append({
            'title': md_file.stem,
            'url': f"articles/{md_file.name.replace('.md', '.html')}"
        })

    # 创建一个极简的 HTML 模板
    html_content = "<html><head><title>Articles</title></head><body><h1>Article List</h1><ul>"
    for article in sorted(articles, key=lambda x: x['title']):
        html_content += f'<li><a href="{article["url"]}">{article["title"]}</a></li>'
    html_content += "</ul></body></html>"
    
    # 另外，为每篇文章生成一个单独的 HTML 页面
    for md_file in articles_dir.glob('*.md'):
        from markdown2 import markdown
        html_article_path = output_dir / f"articles/{md_file.name.replace('.md', '.html')}"
        html_article_path.parent.mkdir(exist_ok=True)
        html_article_path.write_text(f"<h1>{md_file.stem}</h1>\n{markdown(md_file.read_text())}", encoding='utf-8')

    (output_dir / "index.html").write_text(html_content, encoding='utf-8')
    logging.info(f'✔︎ Generated index.html with {len(articles)} articles.')

def main():
    """主函数"""
    # 确保目标目录存在
    DST.mkdir(parents=True, exist_ok=True)
    
    # 检查源目录是否存在
    if not SRC.is_dir():
        logging.error(f"Source directory not found: {SRC}")
        return

    files = list(SRC.glob('*.epub'))
    logging.info(f'Found {len(files)} EPUB file(s) in {SRC}')
    
    for f in files:
        epub_to_md(f, DST)
    
    if files:
        generate_index_html(DST, Path('docs'))

if __name__ == '__main__':
    main()
