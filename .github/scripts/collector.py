import os
import re
import requests

on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:
  push:
    branches:
      - main

jobs:
  collect:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pages: write
      id-token: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests beautifulsoup4 ebooklib pdfplumber nltk PyGithub python-dotenv markdown2 jinja2
          python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

      - name: Run magazine collector script
        id: script-run
        env:
          GITHUB_TOKEN: ${{ secrets.GH_TOKEN }}
        run: python ./.github/scripts/collector.py

      - name: DEBUG - List all generated files
        if: always()
        run: ls -R

      - name: Update repository with new content
        run: |
          git config --global user.name "GitHub Action Bot"
          git config --global user.email "action@github.com"
          # 检查 articles 文件夹是否有变化
          if ! git diff --quiet ./articles; then
            git add ./articles
            git commit -m "Update articles $(date +'%Y-%m-%d')"
            git push
          else
            echo "No new articles to commit."
          fi
          
      - name: Deploy to GitHub Pages
        # 只要 docs 文件夹存在就部署
        if: success()
        uses: JamesIves/github-pages-deploy-action@v4
        with:
          branch: gh-pages
          folder: docs
          clean: true # 部署前清空旧文件，确保干净
