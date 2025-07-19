import logging
import os
import sys
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup
import markdown2

# 增强日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger()

# 详细启动信息
logger.info("=" * 80)
logger.info("🚀 杂志转换器启动")
logger.info(f"Python版本: {sys.version}")
logger.info(f"当前工作目录: {os.getcwd()}")

# 动态计算基础路径
try:
    BASE_DIR = Path(os.getcwd()).resolve()
    logger.info(f"基础目录: {BASE_DIR}")
    
    # 打印工作区结构
    logger.info("目录结构:")
    for item in os.listdir(BASE_DIR):
        logger.info(f" - {item}")
        
        # 如果是目录则列出其内容
        if Path(BASE_DIR, item).is_dir():
            try:
                subdir = Path(BASE_DIR, item)
                logger.info(f"    {item}/:")
                for subitem in os.listdir(subdir)[:10]:  # 只列出前10项避免太多日志
                    logger.info(f"      - {subitem}")
            except Exception as e:
                logger.error(f"无法列出 {item}: {str(e)}")
                
except Exception as e:
    logger.error(f"初始化失败: {str(e)}")
    sys.exit(1)

logger.info("=" * 80)

# 源和目标路径定义
SRC = BASE_DIR / "source_repo_1/01_economist"
DST = BASE_DIR / "docs/articles"

logger.info(f"源目录路径: {SRC}")
logger.info(f"目标目录路径: {DST}")

# 验证源目录存在性
if not SRC.exists():
    logger.error(f"❌ 源目录不存在: {SRC}")
    logger.info("修复建议:")
    logger.info("1. 确保source_repo_1目录存在")
    logger.info(f"2. 检查目录内容: {os.listdir(BASE_DIR)}")
    sys.exit(1)

def epub_to_md(epub_path: Path, out_dir: Path):
    """将EPUB文件转换为Markdown格式"""
    try:
        # 文件存在性检查
        if not epub_path.exists() or not epub_path.is_file():
            logger.error(f"EPUB文件不存在或无效: {epub_path}")
            return
            
        logger.info(f"开始处理: {epub_path.name}")
        
        # 读取并转换EPUB
        book = epub.read_epub(str(epub_path))
        md_parts = []
        
        # 收集所有文本内容
        for item in book.get_items():
            if item.get_type() == epub.ITEM_DOCUMENT:
                try:
                    # 处理不同的内容类型
                    content = item.get_content()
                    if isinstance(content, bytes):
                        content = content.decode('utf-8', errors='replace')
                    
                    soup = BeautifulSoup(content, 'lxml')
                    md_parts.append(soup.get_text('\n'))
                except Exception as e:
                    logger.warning(f"处理文档项失败: {str(e)}")
        
        # 生成Markdown文件
        md_text = '\n\n'.join(md_parts)
        out_file = out_dir / (epub_path.stem + '.md')
        
        # 创建目标目录（如果不存在）
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        out_file.write_text(md_text, encoding='utf-8')
        logger.info(f"✅ 转换成功: {epub_path.name} → {out_file.name}")
        
    except Exception as e:
        logger.error(f"⚠️ 处理失败: {epub_path.name}")
        logger.exception(f"错误详情: {str(e)}")

def generate_index_html(articles_dir: Path, output_dir: Path):
    """生成索引页面和文章页面"""
    try:
        # 创建必要的目录
        articles_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 收集所有文章
        articles = []
        logger.info(f"扫描文章: {articles_dir}")
        for md_file in articles_dir.glob('*.md'):
            if md_file.is_file():
                articles.append({
                    'title': md_file.stem,
                    'filename': md_file.name,
                    'url': f"articles/{md_file.stem}.html"
                })
        
        if not articles:
            logger.warning("⚠️ 没有找到可处理的文章")
            return
        
        logger.info(f"📚 找到 {len(articles)} 篇文章")
        
        # 生成文章列表页面
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>经济学人文章集合</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{
                    background-color: #f8f9fa;
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                }}
                .header {{
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                    color: white;
                    padding: 4rem 0;
                    margin-bottom: 3rem;
                    text-align: center;
                }}
                .article-container {{
                    max-width: 800px;
                    margin: 2rem auto;
                }}
                .article-card {{
                    background-color: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                    margin-bottom: 1.5rem;
                    padding: 1.5rem;
                    transition: transform 0.3s, box-shadow 0.3s;
                }}
                .article-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.15);
                }}
                .article-title {{
                    font-size: 1.4rem;
                    font-weight: 600;
                    color: #1a0dab;
                    margin-bottom: 0.5rem;
                }}
                .article-excerpt {{
                    color: #4d4d4d;
                    font-size: 1rem;
                    line-height: 1.5;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="container">
                    <h1>经济学人精选文章</h1>
                    <p class="lead">最新更新的高质量阅读内容</p>
                </div>
            </div>
            
            <div class="container">
                <div class="article-container">
                    <div class="d-flex justify-content-between align-items-center mb-4">
                        <h2>最新文章</h2>
                        <div class="form-group">
                            <input type="text" class="form-control" id="searchInput" placeholder="搜索文章...">
                        </div>
                    </div>
        """
        
        # 按标题排序文章
        for article in sorted(articles, key=lambda x: x['title'], reverse=True):
            # 读取文章前200字符作为预览
            with open(articles_dir / article['filename'], 'r', encoding='utf-8') as f:
                content = f.read()
                excerpt = content[:200] + ('...' if len(content) > 200 else '')
            
            html_content += f"""
                    <div class="article-card" data-title="{article['title']}">
                        <div class="article-title">
                            <a href="{article['url']}">{article['title']}</a>
                        </div>
                        <div class="article-excerpt">
                            {excerpt}
                        </div>
                    </div>
            """
        
        html_content += """
                </div>
            </div>
            
            <script>
                // 文章搜索功能
                document.getElementById('searchInput').addEventListener('input', function(e) {
                    const searchTerm = e.target.value.toLowerCase();
                    const cards = document.querySelectorAll('.article-card');
                    
                    cards.forEach(card => {
                        const title = card.dataset.title.toLowerCase();
                        if (title.includes(searchTerm)) {
                            card.style.display = '';
                        } else {
                            card.style.display = 'none';
                        }
                    });
                });
            </script>
        </body>
        </html>
        """
        
        # 保存主页
        (output_dir / "index.html").write_text(html_content, encoding='utf-8')
        logger.info("✅ 主页生成完成: index.html")
        
        # 创建文章存储目录
        articles_output_dir = output_dir / "articles"
        articles_output_dir.mkdir(parents=True, exist_ok=True)
        
        # 为每篇文章生成HTML页面
        for article in articles:
            md_file = articles_dir / article['filename']
            html_file = articles_output_dir / (article['title'] + '.html')
            
            # 读取Markdown内容
            with open(md_file, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            # 转换为HTML
            html_body = markdown2.markdown(
                md_content, 
                extras=["tables", "fenced-code-blocks", "smarty-pants"]
            )
            
            # 创建完整文章页面
            article_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{article['title']}</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
                <style>
                    body {{
                        background-color: #f5f7fb;
                        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    }}
                    .container {{
                        max-width: 900px;
                        margin: 3rem auto;
                        padding: 2rem;
                        background: white;
                        border-radius: 12px;
                        box-shadow: 0 5px 20px rgba(0,0,0,0.08);
                    }}
                    .article-header {{
                        margin-bottom: 2rem;
                        border-bottom: 2px solid #eaeaea;
                        padding-bottom: 1.5rem;
                    }}
                    .article-title {{
                        font-size: 2.2rem;
                        font-weight: 700;
                        color: #1a0dab;
                        line-height: 1.2;
                    }}
                    .back-link {{
                        display: inline-flex;
                        align-items: center;
                        margin-bottom: 1rem;
                        color: #4a6fa5;
                        font-weight: 500;
                    }}
                    .article-content {{
                        font-size: 1.1rem;
                        line-height: 1.7;
                        color: #333;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="article-header">
                        <a href="../index.html" class="back-link">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-arrow-left me-2" viewBox="0 0 16 16">
                                <path fill-rule="evenodd" d="M15 8a.5.5 0 0 0-.5-.5H2.707l3.147-3.146a.5.5 0 1 0-.708-.708l-4 4a.5.5 0 0 0 0 .708l4 4a.5.5 0 0 0 .708-.708L2.707 8.5H14.5A.5.5 0 0 0 15 8z"/>
                            </svg>
                            返回文章列表
                        </a>
                        <h1 class="article-title">{article['title']}</h1>
                    </div>
                    <div class="article-content">
                        {html_body}
                    </div>
                </div>
            </body>
            </html>
            """
            
            # 保存文章页面
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(article_html)
                
            logger.info(f"✅ 生成文章: {html_file.name}")
            
    except Exception as e:
        logger.error("⛔ HTML生成失败")
        logger.exception(f"错误详情: {str(e)}")

def main():
    """主处理函数"""
    try:
        logger.info("=" * 80)
        logger.info("🛠️ 开始处理流程")
        logger.info("=" * 80)
        
        # 确保目标目录存在
        DST.mkdir(parents=True, exist_ok=True)
        
        # 查找所有EPUB文件
        epub_files = []
        logger.info(f"扫描EPUB文件: {SRC}")
        for file_path in SRC.glob('*.epub'):
            if file_path.is_file():
                epub_files.append(file_path)
                
        if not epub_files:
            logger.warning(f"⚠️ 在 {SRC} 中未找到EPUB文件")
            return
            
        logger.info(f"📁 找到 {len(epub_files)} 个EPUB文件")
        
        # 转换所有EPUB文件
        for epub_file in epub_files:
            epub_to_md(epub_file, DST)
        
        # 生成HTML网站
        generate_index_html(DST, BASE_DIR / "docs")
        
        logger.info("=" * 80)
        logger.info("✅ 处理完成！")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.critical("💥 脚本执行失败", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
