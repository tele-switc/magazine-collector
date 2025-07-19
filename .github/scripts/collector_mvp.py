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

# 打印详细的启动信息
logger.info("=" * 80)
logger.info("🎬 脚本启动 - 杂志转换器")
logger.info(f"Python版本: {sys.version}")
logger.info(f"当前工作目录: {os.getcwd()}")
logger.info(f"脚本路径: {os.path.abspath(__file__)}")
logger.info("目录结构:")
try:
    for entry in os.listdir(os.getcwd()):
        logger.info(f" - {entry}")
except Exception as e:
    logger.error(f"目录列表失败: {e}")

# 动态计算基础路径（核心修复）
BASE_DIR = Path(os.getcwd()).resolve()
logger.info(f"基础目录: {BASE_DIR}")

# 源和目标路径定义
SRC = BASE_DIR / "source_repo_1/01_economist"
DST = BASE_DIR / "docs/articles"

logger.info(f"源目录路径: {SRC}")
logger.info(f"目标目录路径: {DST}")
logger.info("=" * 80)

def epub_to_md(epub_path: Path, out_dir: Path):
    """将EPUB文件转换为Markdown"""
    try:
        # 文件存在性检查
        if not epub_path.exists() or not epub_path.is_file():
            logger.error(f"EPUB文件不存在或无效: {epub_path}")
            return
            
        logger.info(f"处理文件: {epub_path.name}")
        
        # 读取并转换EPUB
        book = epub.read_epub(str(epub_path))
        md_parts = []
        
        for item in book.get_items():
            if item.get_type() == epub.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text = soup.get_text('\n')
                md_parts.append(text)
        
        # 合并并保存Markdown
        md_text = '\n\n'.join(md_parts)
        out_file = out_dir / (epub_path.stem + '.md')
        
        # 创建目标目录（如果不存在）
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        out_file.write_text(md_text, encoding='utf-8')
        logger.info(f"成功转换: {epub_path.name} → {out_file.name}")
        
    except Exception as e:
        logger.error(f"处理失败: {epub_path.name}")
        logger.exception(f"错误详情: {str(e)}")

def generate_index_html(articles_dir: Path, output_dir: Path):
    """生成索引页面和文章页面"""
    try:
        # 创建必要的目录
        articles_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "articles").mkdir(parents=True, exist_ok=True)
        
        # 收集所有文章
        articles = []
        for md_file in articles_dir.glob('*.md'):
            if md_file.is_file():
                articles.append({
                    'title': md_file.stem,
                    'filename': md_file.name,
                    'url': f"articles/{md_file.stem}.html"
                })
        
        if not articles:
            logger.warning("没有找到可处理的文章")
            return
        
        logger.info(f"发现 {len(articles)} 篇待处理的文章")
        
        # 生成首页HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>杂志文章集合</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{ background-color: #f8f9fa; }}
                .container {{ max-width: 1000px; margin: 3rem auto; }}
                .article-card {{ 
                    background-color: white; 
                    border-radius: 8px; 
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1); 
                    margin-bottom: 1.5rem;
                    padding: 1.5rem;
                    transition: transform 0.2s;
                }}
                .article-card:hover {{ 
                    transform: translateY(-3px); 
                    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
                }}
                .article-title {{ 
                    font-size: 1.4rem; 
                    font-weight: 600; 
                    color: #1a0dab; 
                    margin-bottom: 0.5rem;
                }}
                .article-excerpt {{ 
                    color: #555; 
                    font-size: 1rem;
                    line-height: 1.5;
                }}
                .header {{ 
                    background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
                    color: white;
                    padding: 3rem 0;
                    margin-bottom: 2rem;
                    border-radius: 0 0 20px 20px;
                }}
            </style>
        </head>
        <body>
            <div class="header text-center">
                <div class="container">
                    <h1 class="display-4">经济学人文章精选</h1>
                    <p class="lead">最新更新的优质杂志内容</p>
                </div>
            </div>
            
            <div class="container">
                <div class="row">
                    <div class="col-md-8 offset-md-2">
                        <h2 class="mb-4">最新文章</h2>
                        <div class="articles-list">
        """
        
        # 按标题排序文章
        for article in sorted(articles, key=lambda x: x['title'], reverse=True):
            with open(articles_dir / article['filename'], 'r', encoding='utf-8') as f:
                content = f.read()
                excerpt = content[:150] + ('...' if len(content) > 150 else '')
            
            html_content += f"""
                            <div class="article-card">
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
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        """
        
        # 保存主页
        (output_dir / "index.html").write_text(html_content, encoding='utf-8')
        logger.info("主页生成完成: index.html")
        
        # 为每篇文章生成HTML页面
        for article in articles:
            md_file = articles_dir / article['filename']
            html_file = output_dir / "articles" / article['url'].split('/')[-1]
            
            # 读取Markdown内容
            with open(md_file, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            # 转换为HTML
            html_content_article = markdown2.markdown(
                md_content, 
                extras=["tables", "fenced-code-blocks", "smarty-pants"]
            )
            
            # 创建完整文章页面
            article_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{article['title']}</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
                <style>
                    body {{ background-color: #f5f7fb; }}
                    .article-container {{ 
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
                        display: inline-block;
                        margin-bottom: 1rem;
                        color: #6c757d;
                    }}
                </style>
            </head>
            <body>
                <div class="article-container">
                    <div class="article-header">
                        <a href="../index.html" class="back-link">← 返回文章列表</a>
                        <h1 class="article-title">{article['title']}</h1>
                    </div>
                    <div class="article-content">
                        {html_content_article}
                    </div>
                </div>
            </body>
            </html>
            """
            
            # 保存文章页面
            html_file.parent.mkdir(parents=True, exist_ok=True)
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(article_html)
                
            logger.info(f"生成文章: {html_file.name}")
            
    except Exception as e:
        logger.error("HTML生成失败")
        logger.exception(f"错误详情: {str(e)}")

def main():
    """主处理函数"""
    try:
        # 确保源目录存在
        if not SRC.exists():
            logger.error(f"源目录不存在: {SRC}")
            logger.info(f"源目录存在状态: {SRC.exists()}")
            logger.info(f"目录内容: {os.listdir(BASE_DIR)}")
            return
        
        # 创建目标目录
        DST.mkdir(parents=True, exist_ok=True)
        
        # 查找所有EPUB文件
        epub_files = []
        for file_path in SRC.glob('**/*.epub'):
            if file_path.is_file():
                epub_files.append(file_path)
                
        if not epub_files:
            logger.warning(f"在 {SRC} 中未找到EPUB文件")
            return
            
        logger.info(f"找到 {len(epub_files)} 个EPUB文件")
        
        # 转换所有EPUB文件
        for epub_file in epub_files:
            epub_to_md(epub_file, DST)
        
        # 生成HTML网站
        generate_index_html(DST, BASE_DIR / "docs")
        
        logger.info("✅ 处理完成！")
        
    except Exception as e:
        logger.critical("脚本执行失败", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
