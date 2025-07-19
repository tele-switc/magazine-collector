import logging
import os  # 明确导入os模块
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup
from markdown2 import markdown  # 导入缺失的markdown2模块

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 动态计算绝对路径 - 关键修复
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SRC = BASE_DIR / "source_repo_1/01_economist"
DST = BASE_DIR / "docs/articles"

def epub_to_md(epub_path: Path, out_dir: Path):
    """将单个 EPUB 文件转换为 Markdown 文件。"""
    try:
        book = epub.read_epub(str(epub_path))  # 确保兼容字符串路径
        md_parts = []
        
        # 修复：使用正确的项目类型常量
        for item in book.get_items_of_type(epub.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), 'lxml')
            md_parts.append(soup.get_text('\n'))
        
        md_text = '\n\n'.join(md_parts)
        out_file = out_dir / (epub_path.stem + '.md')
        out_file.write_text(md_text, encoding='utf-8')
        logging.info(f'✔︎ Success: Converted {epub_path.name} to {out_file.name}')
    except Exception as e:
        logging.error(f'✘ Failed to process {epub_path.name}: {e}')
        logging.exception("详细错误:")  # 添加详细错误跟踪

def generate_index_html(articles_dir: Path, output_dir: Path):
    """创建 HTML 首页和文章页"""
    # 创建必要的目录
    articles_dir.mkdir(parents=True, exist_ok=True)
    
    # 收集所有文章
    articles = []
    for md_file in articles_dir.glob('*.md'):
        articles.append({
            'title': md_file.stem,
            'url': f"articles/{md_file.name.replace('.md', '.html')}"
        })
    
    # 生成主页HTML
    html_content = """
    <html>
    <head>
        <title>电子书集锦</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; line-height: 1.6; }
            .container { max-width: 800px; margin: 0 auto; padding: 20px; }
            h1 { color: #2c3e50; }
            ul { list-style: none; padding: 0; }
            li { margin-bottom: 12px; padding: 8px; background: #f8f9fa; border-radius: 4px; }
            a { color: #1a73e8; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>杂志文章集锦</h1>
            <ul>
    """
    
    for article in sorted(articles, key=lambda x: x['title']):
        html_content += f'<li><a href="{article["url"]}">{article["title"]}</a></li>\n'
    
    html_content += """
            </ul>
        </div>
    </body>
    </html>
    """
    
    # 生成每篇文章的HTML页面
    for md_file in articles_dir.glob('*.md'):
        html_filename = md_file.name.replace('.md', '.html')
        html_file_path = output_dir / "articles" / html_filename
        html_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加基本样式
        md_content = md_file.read_text(encoding='utf-8')
        html_content_single = markdown(md_content, extras=["tables"])
        
        with html_file_path.open('w', encoding='utf-8') as f:
            f.write(f"""
            <html>
            <head>
                <title>{md_file.stem}</title>
                <meta charset="utf-8">
                <style>
                    body {{ max-width: 800px; margin: 0 auto; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; line-height: 1.6; }}
                    h1 {{ color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
                </style>
            </head>
            <body>
                <h1>{md_file.stem}</h1>
                {html_content_single}
            </body>
            </html>
            """)
    
    # 保存主页
    (output_dir / "index.html").write_text(html_content, encoding='utf-8')
    logging.info(f'✔︎ Generated index.html with {len(articles)} articles.')

def main():
    """主函数"""
    # 打印关键路径信息用于调试
    logging.info(f"当前工作目录: {os.getcwd()}")
    logging.info(f"基础目录: {BASE_DIR}")
    logging.info(f"源目录: {SRC}")
    
    # 确认源目录是否存在
    if not SRC.exists():
        logging.error(f"❌ 源目录不存在: {SRC}")
        # 列出可用目录
        logging.info(f"可用目录: {', '.join(os.listdir(BASE_DIR))}")
        return
    
    # 创建目标目录
    DST.mkdir(parents=True, exist_ok=True)
    
    # 处理所有epub文件
    files = list(SRC.glob('*.epub'))
    logging.info(f'找到 {len(files)} 个EPUB文件')
    
    for f in files:
        epub_to_md(f, DST)
    
    # 如果有文件被处理，生成HTML
    if files:
        generate_index_html(DST, BASE_DIR / "docs")

if __name__ == '__main__':
    main()
