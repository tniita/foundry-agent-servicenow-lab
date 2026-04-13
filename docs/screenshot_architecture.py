"""HTML → PNG スクリーンショット (Playwright)"""
import sys, os
from playwright.sync_api import sync_playwright

def main():
    html_path = os.path.join(os.path.dirname(__file__), 'images', 'architecture.html')
    png_path  = os.path.join(os.path.dirname(__file__), 'images', 'architecture.png')
    abs_html  = os.path.abspath(html_path)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1400, 'height': 900})
        page.goto(f'file:///{abs_html.replace(os.sep, "/")}')
        page.wait_for_timeout(1500)
        page.screenshot(path=png_path, full_page=True, type='png')
        browser.close()

    size_kb = os.path.getsize(png_path) / 1024
    print(f'Saved: {png_path} ({size_kb:.0f} KB)')

if __name__ == '__main__':
    main()
