import logging
import os
import sys
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup
import markdown2  # 确保导入markdown2

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout  # 直接输出到控制台
)

# 动态计算基础路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SRC = BASE_DIR / "source_repo_1/01_economist"
DST = BASE_DIR / "docs/articles"

def epub_to_md(epub_path: Path, out_dir: Path):
    """将单个 EPUB 文件转换为 Markdown 文件"""
    try:
        # 打印调试信息
        logging.info(f"正在处理文件: {epub_path.name}")
        if not epub_path.exists():
            logging.error(f"文件不存在: {epub_path}")
            return
            
        book = epub.read_epub(str(epub_path))
        md_parts = []
        
        # 收集所有文本内容
        for item in book.get_items():
            if item.get_type() == epub.ITEM_DOCUMENT:
                content = item.get_content().decode('utf-8', errors='replace')
                soup = BeautifulSoup(content, 'lxml')
                md_parts.append(soup.get_text('\n'))
        
        md_text = '\n\n'.join(md_parts)
        out_file = out_dir / (epub_path.stem + '.md')
        out_file.write_text(md_text, encoding='utf-8')
        logging.info(f'成功转换: {epub_path.name} → {out_file.name}')
    except Exception as e:
        logging.error(f'处理失败: {epub_path.name} - {str(e)}')

def generate_index_html(articles_dir: Path, output_dir: Path):
    """创建包含所有文章的HTML索引"""
    # 确保输出目录存在
    articles_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    articles = []
    # 只处理存在的Markdown文件
    for md_file in list(articles_dir.glob('*.md')):
        if not md_file.is_file():
            continue
        articles.append({
            'title': md_file.stem,
            'url': f"articles/{md_file.name.replace('.md', '.html')}"
        })

    if not articles:
        logging.warning("没有找到可处理的文章")
        return

    # 生成首页
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>杂志文章归档</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-5">
            <h1 class="mb-4">经济学人文章归档</h1>
            <div class="list-group">
    """
    
    for article in sorted(articles, key=lambda x: x['title']):
        html_content += f"""
                <a href="{article["url"]}" class="list-group-item list-group-item-action">
                    {article["title"]}
                </a>
        """
    
    html_content += """
            </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    
    # 生成每篇文章的HTML页面
    for md_file in articles_dir.glob('*.md'):
        html_filename = md_file.name.replace('.md', '.html')
        html_file = output_dir / "articles" / html_filename
        html_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取Markdown内容并转换
        md_content = md_file.read_text(encoding='utf-8')
        html_content_single = markdown2.markdown(
            md_content, extras=["tables", "fenced-code-blocks"]
        )
        
        # 创建带样式的完整页面
        article_html = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{md_file.stem}</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{ background-color: #f8f9fa; }}
                .article-container {{ max-width: 800px; margin: 2rem auto; padding: 2rem; background: white; border-radius: 10px; box-shadow: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.075); }}
                .article-title {{ border-bottom: 2px solid #0d6efd; padding-bottom: 0.5rem; }}
            </style>
        </head>
        <body>
            <div class="article-container">
                <h1 class="article-title mb-4">{md_file.stem}</h1>
                <div class="article-content">
                    {html_content_single}
                </div>
            </div>
        </body>
        </html>
        """
        
        html_file.write_text(article_html, encoding='utf-8')
    
    # 保存主页
    (output_dir / "index.html").write_text(html_content, encoding='utf-8')
    logging.info(f'生成索引页面，包含 {len(articles)} 篇文章')

def main():
    # 调试信息
    logging.info("=" * 80)
    logging.info(f"项目根目录: {BASE_DIR}")
    logging.info(f"源文件路径: {SRC}")
    logging.info(f"目标路径: {DST}")
    logging.info("=" * 80)
    
    # 列出当前目录内容
    logging.info(f"当前目录内容: {os.listdir(BASE_DIR)}")
    
    # 确保源目录存在
    if not SRC.exists():
        logging.error(f"源目录不存在: {SRC}")
        logging.info(f"源目录存在检查: {SRC.exists()}")
        logging.info(f"目录内容: {os.listdir(BASE_DIR / 'source_repo_1')}")
        return
    
    # 确保目标目录存在
    DST.mkdir(parents=True, exist_ok=True)
    
    # 只处理实际存在的EPUB文件
    epub_files = [f for f in SRC.glob('*.epub') if f.is_file()]
    logging.info(f"找到 {len(epub_files)} 个EPUB文件")
    
    # 转换文件
    for epub_file in epub_files:
        epub_to_md(epub_file, DST)
    
    # 生成网站
    if epub_files:
        generate_index_html(DST, BASE_DIR / "docs")
    else:
        logging.info("没有文件需要处理")

if __name__ == '__main__':
    try:
        main()
        logging.info("✅ 处理完成！")
    except Exception as e:
        logging.error(f"❌ 严重错误: {str(e)}")
        logging.exception("完整错误堆栈:")
        sys.exit(1)
