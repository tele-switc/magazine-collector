import logging
import os
import sys
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup
import markdown2

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 【专家方案】通过环境变量获取工作区根目录，绝对可靠
GITHUB_WORKSPACE = os.getenv('GITHUB_WORKSPACE')
if not GITHUB_WORKSPACE:
    # 为本地开发提供回退方案
    logging.warning("GITHUB_WORKSPACE 环境变量未设置，将使用本地相对路径计算。")
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
else:
    BASE_DIR = Path(GITHUB_WORKSPACE)

logging.info(f"[*] 工作区基础目录 (BASE_DIR): {BASE_DIR}")

# 基于绝对路径定义源和目标
SRC = BASE_DIR / "source_repo_1/01_economist"
DST = BASE_DIR / "local_repo/docs/articles"

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

def generate_index_html(articles_dir: Path, output_dir: Path):
    """根据生成的 .md 文件创建一个简单的 HTML 首页和详情页。"""
    articles = [{'title': md_file.stem, 'url': f"articles/{md_file.stem}.html"} for md_file in articles_dir.glob('*.md')]
    
    for md_file in articles_dir.glob('*.md'):
        html_article_path = output_dir / "articles" / f"{md_file.stem}.html"
        html_article_path.parent.mkdir(exist_ok=True)
        html_content = f"<!DOCTYPE html><html><head><title>{md_file.stem}</title></head><body><h1>{md_file.stem}</h1>"
        html_content += markdown2.markdown(md_file.read_text(encoding='utf-8'))
        html_content += '<br/><a href="../index.html">返回列表</a></body></html>'
        html_article_path.write_text(html_content, encoding='utf-8')

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
        sys.exit(1)
        
    DST.mkdir(parents=True, exist_ok=True)

    files = list(SRC.glob('*.epub'))
    logging.info(f'在 {SRC} 中找到 {len(files)} 个 EPUB 文件。')
    
    for f in files:
        epub_to_md(f, DST)
    
    if files:
        generate_index_html(DST, BASE_DIR / "local_repo/docs")
    
    logging.info("✅ 脚本执行完毕。")

if __name__ == '__main__':
    main()
