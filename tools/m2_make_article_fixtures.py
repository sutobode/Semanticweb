"""Sinh HTML fixture cho test nguồn bài viết (M2-26): tests/unit/test_m2_registry_articles.py.

Dựng lại từ nội dung thật đọc được ngày 2026-09-25 (dsvh.gov.vn/di-tich-quoc-gia-130 và 2 bài
Đình Đạm Xuyên, Đền thờ Khúc Thừa Dụ); cấu trúc DOM là GIẢ ĐỊNH (menu, sidebar, breadcrumb, h1).
Khi có HTML thật (notebook lưu ở article_html/), thay các file này bằng HTML thật.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "registry_articles"
MENU = """<header><ul class="main-menu">
<li><a href="https://dsvh.gov.vn/thong-tin-chung-1727">Thông tin chung</a></li>
<li><a href="https://dsvh.gov.vn/danh-muc-di-tich-quoc-gia-1753">Danh mục Di tích quốc gia</a></li>
<li><a href="https://dsvh.gov.vn/tin-tuc-su-kien-3">Tin tức - sự kiện</a></li></ul></header>"""
SIDEBAR = """<div class="sidebar"><h3>Văn bản pháp luật</h3>
<a href="https://dsvh.gov.vn/van-ban-phap-luat-viet-nam-95">Văn bản pháp luật VIệt Nam</a>
<h3>Thông báo mới</h3>
<a href="https://dsvh.gov.vn/ra-soat-toan-dien-van-ban-22370" title="Rà soát toàn diện văn bản quy phạm pháp luật">Rà soát toàn diện văn bản quy phạm pháp luật: Gỡ 'điểm nghẽn', khơi th...</a>
<a href="https://dsvh.gov.vn/trang-thong-tin-dien-tu-dang-nang-cap-2923">Trang Thông tin điện tử đang trong quá trình nâng cấp</a>
</div>"""


def page(body: str, title: str) -> str:
    return f"<html><head><title>{title}</title></head><body>{MENU}<div class='main'>{body}</div>{SIDEBAR}</body></html>"


LISTS = {
    1: [("dinh-dam-xuyen-thanh-pho-ha-noi-22364", "Đình Đạm Xuyên, Thành phố Hà Nội"),
        ("dinh-tri-le-thanh-pho-ha-noi-22366", "Đình Tri Lễ, Thành phố Hà Nội"),
        ("den-tho-khuc-thua-du-22340", "Đền thờ Khúc Thừa Dụ")],
    2: [("den-thuong-dac-biet-tinh-phu-tho-22300", "Đền Thượng, tỉnh Phú Thọ"),
        ("mieu-khong-quyet-dinh-tinh-nam-dinh-22301", "Miếu Không Quyết Định, tỉnh Nam Định"),
        ("den-goi-vi-tinh-tuyen-quang-22302", "Đền Gôi Vị, tỉnh Tuyên Quang")],
    3: [("phu-phu-chinh-thanh-pho-hue-22354", "Phủ Phụ Chính, thành phố Huế")],
}
ARTICLES = {
    "22364": ("Đình Đạm Xuyên, Thành phố Hà Nội",
              "<p>Đình Đạm Xuyên (xã Mê Linh, Thành phố Hà Nội) được Bộ trưởng Bộ Văn hoá, Thông tin (nay là Bộ Văn hoá, "
              "Thể thao và Du lịch) xếp hạng di tích kiến trúc nghệ thuật quốc gia (tại Quyết định số 15/2003/QĐ-BVHTT "
              "ngày 14/4/2003), là nơi thờ phụng ba vị Thần.</p><p>Đình Đạm Xuyên là công trình kiến trúc thời Nguyễn, "
              "được dựng trên nền cao. Mái đình lợp ngói mũi hài, các góc mái có đầu đao cong.</p>"),
    "22366": ("Đình Tri Lễ, Thành phố Hà Nội",
              "<p>Đình Tri Lễ nằm ở thôn Tri Lễ, xã Tri Trung, là nơi thờ Thành hoàng làng. Đình có kiến trúc chữ Đinh, "
              "được trùng tu nhiều lần qua các thời kỳ lịch sử khác nhau của làng xã.</p><p>Với những giá trị trên, đình "
              "Tri Lễ được xếp hạng Di tích lịch sử và kiến trúc nghệ thuật quốc gia theo Quyết định số 3013/QĐ-BVHTTDL "
              "ngày 20/10/2015.</p>"),
    "22340": ("Đền thờ Khúc Thừa Dụ",
              "<p>Đền thờ Khúc Thừa Dụ thuộc xã Kiến Quốc, huyện Ninh Giang, tỉnh Hải Dương (nay là xã Khúc Thừa Dụ, "
              "Thành phố Hải Phòng). Đền thờ những người thuộc dòng họ Khúc, có công chống lại ách độ hộ nhà Đường.</p>"
              "<p>Vào đầu thế kỷ X, ở Trung Quốc, triều đình nhà Đường bước vào thời kỳ mạt vận.</p>"
              "<p><strong>Với những giá trị tiêu biểu trên, đền thờ Khúc Thừa Dụ đã được Bộ trưởng Bộ Văn hoá, Thể thao và "
              "Du lịch xếp hạng Di tích lịch sử quốc gia theo Quyết định số 2103/QĐ-BVHTTDL ngày 08 tháng 7 năm 2014./.</strong></p>"),
    "22300": ("Đền Thượng, tỉnh Phú Thọ",
              "<p>Đền Thượng thuộc xã Hy Cương, tỉnh Phú Thọ. Năm 2009, di tích được Thủ tướng Chính phủ xếp hạng di tích "
              "quốc gia đặc biệt theo Quyết định số 1272/QĐ-TTg ngày 12/8/2009. Đây là nơi thờ các vua Hùng.</p>"),
    "22301": ("Miếu Không Quyết Định, tỉnh Nam Định",
              "<p>Miếu Không Quyết Định thuộc xã Hải Hậu, tỉnh Nam Định, được xếp hạng di tích lịch sử quốc gia từ lâu. "
              "Miếu có kiến trúc đơn giản, gồm ba gian thờ chính và hai gian phụ ở hai bên.</p>"),
    "22302": ("Đền Gôi Vị, tỉnh Tuyên Quang",
              "<p>Đền Gôi Vị thuộc xã Hợp Thành, huyện Sơn Dương, tỉnh Tuyên Quang, được xếp hạng di tích lịch sử quốc gia "
              "theo Quyết định số 618/QĐ-BVHTTDL ngày 10/3/2017. Đền thờ Quốc mẫu Âu Cơ và các vị thần.</p>"),
    "22354": ("Phủ Phụ Chính, thành phố Huế",
              "<p>Phủ Phụ Chính tọa lạc tại phường Kim Long, thành phố Huế, là dinh thự của một vị quan triều Nguyễn. "
              "Di tích được xếp hạng di tích lịch sử quốc gia theo Quyết định số 99/QĐ-BVHTTDL ngày 5/1/2024.</p>"),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for n, items in LISTS.items():
        links = "".join(f'<div class="item"><a href="https://dsvh.gov.vn/{slug}" title="{title}">{title}</a></div>'
                        for slug, title in items)
        pager = "".join(f'<li><a href="https://dsvh.gov.vn/di-tich-quoc-gia-130?_pageIndex={i}">{i}</a></li>' for i in LISTS)
        body = (f'<div class="breadcrumb"><a href="https://dsvh.gov.vn/di-tich-1746">Di tích</a></div>{links}'
                f'<p class="pager"><b>Trang {n}/{len(LISTS)}</b></p><ul class="pagination">{pager}</ul>')
        (OUT / f"list-p{n:03d}.html").write_text(page(body, "Di tích quốc gia"), encoding="utf-8")
    for article_id, (title, text) in ARTICLES.items():
        body = (f'<div class="breadcrumb"><a href="https://dsvh.gov.vn/di-tich-quoc-gia-130">Di tích quốc gia</a></div>'
                f'<div class="detail"><h1>{title}</h1>{text}<p><em>Theo hồ sơ tư liệu Cục Di sản văn hóa</em></p></div>')
        (OUT / f"article-{article_id}.html").write_text(page(body, title), encoding="utf-8")
    notice = page('<div class="breadcrumb"><a href="https://dsvh.gov.vn/thong-bao-moi">Thông báo mới</a></div>'
                  '<div class="detail"><h1>Rà soát toàn diện văn bản quy phạm pháp luật</h1><p>Nội dung thông báo.</p></div>',
                  "Thông báo")
    (OUT / "article-22370.html").write_text(notice, encoding="utf-8")
    (OUT / "article-2923.html").write_text(notice, encoding="utf-8")


if __name__ == "__main__":
    main()
