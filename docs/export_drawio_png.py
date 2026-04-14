"""drawio XML → PNG エクスポート (Playwright + draw.io viewer)"""
import os, sys, base64, zlib, urllib.parse
from playwright.sync_api import sync_playwright

def deflate_and_encode(xml: str) -> str:
    compressed = zlib.compress(xml.encode("utf-8"), 9)
    # draw.io uses raw deflate (strip zlib header 2B + checksum 4B)
    raw = compressed[2:-4]
    b64 = base64.b64encode(raw).decode("ascii")
    return urllib.parse.quote(b64, safe="")

def main():
    drawio_path = os.path.join(os.path.dirname(__file__), "images", "architecture.drawio")
    png_path = os.path.join(os.path.dirname(__file__), "images", "architecture.png")

    with open(drawio_path, "r", encoding="utf-8") as f:
        xml = f.read()

    # Build the draw.io viewer URL with embedded diagram
    encoded = deflate_and_encode(xml)
    viewer_url = (
        f"https://viewer.diagrams.net/?border=20&highlight=0000ff"
        f"&nav=1&title=architecture#R{encoded}"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.goto(viewer_url, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # Hide toolbar / UI chrome if present
        page.evaluate("""() => {
            const tb = document.querySelector('.geToolbar, .geDiagramContainer + div');
            if (tb) tb.style.display = 'none';
        }""")

        # Find the SVG diagram container and screenshot it
        container = page.query_selector(".geDiagramContainer") or page.query_selector("svg")
        if container:
            container.screenshot(path=png_path, type="png")
        else:
            page.screenshot(path=png_path, full_page=True, type="png")

        browser.close()

    size_kb = os.path.getsize(png_path) / 1024
    print(f"Saved: {png_path} ({size_kb:.0f} KB)")

if __name__ == "__main__":
    main()
