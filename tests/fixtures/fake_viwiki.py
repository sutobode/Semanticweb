"""MediaWiki API giả lập cho test engine khớp Wikipedia (không gọi mạng).

Chứa các bài/bẫy rút ra từ review thủ công 2026-09-24 (m2_wiki_unmatched.json).
Hỗ trợ: action=query&titles (redirect, trang thiếu, pageprops định hướng, categories,
extract, links), list=prefixsearch (không phân biệt hoa/thường), wbgetentities (rỗng).
"""
from __future__ import annotations

import unicodedata

PAGES: dict[str, dict] = {}
REDIRECTS: dict[str, str] = {}
_next_id = [1000]


def page(title: str, categories: list[str], extract: str, qid: str | None = None,
         disambiguation: bool = False, links: list[str] | None = None) -> None:
    _next_id[0] += 1
    props = {}
    if qid:
        props["wikibase_item"] = qid
    if disambiguation:
        props["disambiguation"] = ""
    PAGES[title] = {"pageid": _next_id[0], "title": title, "extract": extract, "pageprops": props,
                    "categories": [{"title": "Thể loại:" + c} for c in categories],
                    "links": [{"ns": 0, "title": t} for t in (links or [])]}


def redirect(source: str, target: str) -> None:
    REDIRECTS[source] = target


# --- Di tích -------------------------------------------------------------------
page("Thánh địa Mỹ Sơn", ["Di sản thế giới tại Việt Nam", "Di tích tại Quảng Nam"], "Thánh địa Mỹ Sơn thuộc tỉnh Quảng Nam.", "Q1")
page("Khu bảo tồn thiên nhiên Na Hang – Lâm Bình", ["Khu bảo tồn thiên nhiên Việt Nam"], "Khu bảo tồn ở tỉnh Tuyên Quang.")
page("Quần đảo Cát Bà", ["Quần đảo Việt Nam", "Du lịch Hải Phòng"], "Quần đảo thuộc thành phố Hải Phòng.")
page("Hang Con Moong", ["Di tích quốc gia đặc biệt", "Hang động Thanh Hóa"], "Hang ở huyện Thạch Thành, Thanh Hóa.")
page("Thánh địa Cát Tiên", ["Di tích tại Lâm Đồng"], "Thánh địa ở tỉnh Lâm Đồng.")
page("Mộ cự thạch Hàng Gòn", ["Di tích tại Đồng Nai"], "Mộ cự thạch ở tỉnh Đồng Nai.")
page("Tháp Po Klong Garai", ["Tháp Chăm"], "Tháp ở Phan Rang, nay thuộc tỉnh Khánh Hòa.")   # sau sáp nhập: Ninh Thuận -> Khánh Hòa
page("An toàn khu Định Hóa", ["Di tích tại Thái Nguyên"], "ATK ở huyện Định Hóa, tỉnh Thái Nguyên.")
page("Khu di tích lịch sử Bạch Đằng", ["Di tích quốc gia đặc biệt"], "Khu di tích ở thị xã Quảng Yên, tỉnh Quảng Ninh.")
page("Sông Bạch Đằng", ["Sông của Việt Nam", "Sông tại Quảng Ninh"], "Sông ở Quảng Ninh và Hải Phòng.")
redirect("Bạch Đằng", "Sông Bạch Đằng")
page("Khu di tích chiến trường Điện Biên Phủ", ["Di tích quốc gia đặc biệt"], "Khu di tích ở tỉnh Điện Biên.")
page("Khu di tích nhà Trần tại Đông Triều", ["Di tích tại Quảng Ninh"], "Khu di tích ở Đông Triều, Quảng Ninh.")
page("Khu lưu niệm Chủ tịch Tôn Đức Thắng", ["Di tích tại An Giang"], "Ở cù lao Ông Hổ, tỉnh An Giang.")
page("Nhà đày Buôn Ma Thuột", ["Nhà tù Việt Nam"], "Nhà đày ở tỉnh Đắk Lắk.")
page("Khu di tích khởi nghĩa Yên Thế", ["Di tích quốc gia đặc biệt"], "Khu di tích ở huyện Yên Thế, nay thuộc tỉnh Bắc Ninh.")  # Bắc Giang -> Bắc Ninh
page("Khởi nghĩa Yên Thế", ["Khởi nghĩa Việt Nam"], "Cuộc khởi nghĩa ở Bắc Giang.")
page("Thành cổ Quảng Trị", ["Thành cổ Việt Nam", "Di tích quốc gia đặc biệt"], "Thành cổ ở tỉnh Quảng Trị.")
page("Nhà tù Phú Quốc", ["Nhà tù Việt Nam"], "Nhà tù ở Phú Quốc, nay thuộc tỉnh An Giang.")   # Kiên Giang -> An Giang
page("Hồ Hoàn Kiếm", ["Hồ tại Hà Nội"], "Hồ ở trung tâm Hà Nội.", "Q2")
page("Đền Ngọc Sơn", ["Đền tại Hà Nội"], "Đền trên hồ Hoàn Kiếm, Hà Nội.", "Q3")
page("Chùa Thầy", ["Chùa tại Hà Nội"], "Chùa ở xã Sài Sơn, Hà Nội.")
page("Hoàng Xá", ["Xã, phường, thị trấn thuộc Hà Nội"], "Xã thuộc Hà Nội.")
page("Chùa Vĩnh Nghiêm", [], "Có thể là:", disambiguation=True,
     links=["Chùa Vĩnh Nghiêm (Bắc Ninh)", "Chùa Vĩnh Nghiêm (Thành phố Hồ Chí Minh)"])
page("Chùa Vĩnh Nghiêm (Bắc Ninh)", ["Chùa tại Bắc Ninh"], "Chùa ở Yên Dũng, Bắc Giang cũ, nay thuộc Bắc Ninh.")
page("Chùa Vĩnh Nghiêm (Thành phố Hồ Chí Minh)", ["Chùa tại Thành phố Hồ Chí Minh"], "Chùa ở Thành phố Hồ Chí Minh.")
page("Khu di tích Côn Sơn – Kiếp Bạc", ["Di tích quốc gia đặc biệt"], "Ở Chí Linh, Hải Dương.")
page("Côn Sơn", ["Núi Việt Nam"], "Núi ở Hải Dương.")
page("Kiếp Bạc", ["Đền tại Hải Dương"], "Đền ở Hải Dương.")
page("Đền Trần", [], "Có thể là:", disambiguation=True, links=["Đền Trần (Nam Định)", "Đền Trần (Long Hưng)"])
page("Đền Trần (Nam Định)", ["Đền tại Nam Định"], "Đền ở thành phố Nam Định.")
page("Đền Trần (Long Hưng)", ["Đền tại Thái Bình"], "Đền ở Hưng Hà, Thái Bình.")
page("Chùa Phổ Minh", [], "Có thể là:", disambiguation=True, links=["Chùa Phổ Minh (Nam Định)"])
page("Chùa Phổ Minh (Nam Định)", ["Chùa tại Nam Định"], "Chùa ở Nam Định.")
page("Đền Xưa", ["Đền tại Hải Dương"], "Đền ở Hải Dương.")
page("Chùa Giám", ["Chùa tại Hải Dương"], "Chùa ở Hải Dương.")
page("Đền Bia", ["Đền tại Hải Dương"], "Đền ở Hải Dương.")
page("Địa đạo Vịnh Mốc", ["Địa đạo Việt Nam", "Di tích tại Quảng Trị"], "Địa đạo ở Vĩnh Linh, Quảng Trị.")
page("Hoàng thành Thăng Long", ["Di sản thế giới tại Việt Nam"], "Di tích ở Hà Nội.", "Q4")
page("Quần thể di tích Cố đô Huế", ["Di sản thế giới tại Việt Nam"], "Ở thành phố Huế.", "Q5")
page("Chùa Keo", [], "Có thể là:", disambiguation=True, links=["Chùa Keo (Thái Bình)", "Chùa Keo Hành Thiện"])
page("Chùa Keo (Thái Bình)", ["Chùa tại Thái Bình"], "Chùa ở Vũ Thư, Thái Bình.")
page("Chùa Keo Hành Thiện", ["Chùa tại Nam Định"], "Chùa ở Xuân Trường, Nam Định.")
# --- Override ------------------------------------------------------------------
for title, cat, text in [("Chiến khu Tân Trào", "Di tích tại Tuyên Quang", "Tuyên Quang"),
                         ("Đền Bà Triệu", "Đền tại Thanh Hóa", "Thanh Hóa"),
                         ("Đường Trường Sơn", "Chiến tranh Việt Nam", "Trường Sơn"),
                         ("Đền Cao An Phụ", "Đền tại Hải Dương", "Hải Dương"),
                         ("Động Kính Chủ", "Hang động Hải Dương", "Hải Dương"),
                         ("Chùa Hương", "Chùa tại Hà Nội", "Hà Nội")]:
    page(title, [cat], f"Ở {text}.")
page("Bà Triệu", ["Mất năm 248", "Khởi nghĩa Việt Nam"], "Nữ anh hùng ở Thanh Hóa.")
# --- Phi vật thể ---------------------------------------------------------------
page("Hát xoan", ["Di sản văn hóa phi vật thể"], "Loại hình dân ca ở Phú Thọ.")
page("Xoan", ["Cây"], "Một loài cây.")
page("Quan họ", ["Dân ca Việt Nam"], "Dân ca vùng Kinh Bắc, Bắc Ninh và Bắc Giang.")
page("Ca trù", ["Di sản văn hóa phi vật thể"], "Loại hình ở Hà Nội, Hải Dương, Nghệ An.")
page("Lễ hội đua bò Bảy Núi", ["Lễ hội Việt Nam"], "Lễ hội ở tỉnh An Giang.")
page("Lễ hội chọi trâu Đồ Sơn", ["Lễ hội Việt Nam"], "Lễ hội ở Đồ Sơn, Hải Phòng.")
page("Chữ Nôm Dao", ["Chữ viết"], "Chữ của người Dao ở Bắc Kạn, Lào Cai.")
page("Chữ Nôm Tày", ["Chữ viết"], "Chữ của người Tày ở Bắc Kạn.")
page("Tín ngưỡng thờ cúng Hùng Vương", ["Tín ngưỡng Việt Nam"], "Tín ngưỡng ở Phú Thọ.")
page("Nghi lễ Then", ["Tín ngưỡng Việt Nam"], "Nghi lễ của người Tày, Nùng.")
# --- Phi vật thể: chính sách bằng chứng intangible_evidence (review Kaggle 2026-09-24) ----
page("Xòe Thái", ["Múa Việt Nam"], "Điệu múa truyền thống của người Thái ở Tây Bắc.")
page("Bài chòi", ["Di sản văn hóa phi vật thể"], "Loại hình nghệ thuật dân gian miền Trung.")
page("Múa rối nước", ["Sân khấu Việt Nam"], "Loại hình sân khấu dân gian của người Việt.")
page("Đờn ca tài tử Nam Bộ", ["Di sản văn hóa phi vật thể"],
     "Bắt nguồn từ nhạc lễ và ca Huế, được các nhạc sĩ gốc Quảng Nam đưa vào Nam.")      # >= 2 nhóm tỉnh khác
redirect("Đờn ca tài tử", "Đờn ca tài tử Nam Bộ")
page("Lễ hội nghinh Ông", ["Lễ hội Việt Nam"], "Lễ hội cầu ngư của ngư dân ở Bình Thuận và Khánh Hòa.")
page("Hát sli", ["Dân ca Việt Nam"], "Lối hát giao duyên của người Nùng.")
page("Lễ cấp sắc", ["Tín ngưỡng Việt Nam"], "Nghi lễ trưởng thành của người Dao, người Tày và người Sán Dìu.")
page("Mo Mường", ["Sử thi Việt Nam", "Người Mường"], "Sử thi và nghi lễ của người Mường ở Hòa Bình, Phú Thọ, Thanh Hóa.")
page("Sình ca", ["Dân ca Việt Nam"], "Lối hát của người Cao Lan.")
redirect("Dân ca Cao Lan", "Sình ca")
redirect("Dân ca Sán Chí", "Sình ca")
redirect("Hát nhà tơ", "Ca trù")
page("Dân ca", ["Âm nhạc"], "Thể loại âm nhạc truyền thống của nhân dân.")                      # bẫy
page("Rèn", ["Nghề thủ công"], "Nghề gia công kim loại.")                                           # bẫy
redirect("Nghề rèn", "Rèn")
page("Lễ hội Cầu mùa (người Dao)", ["Lễ hội Việt Nam"], "Lễ hội của người Dao.")                    # bẫy cho Sán Chay
redirect("Lễ hội Cầu mùa", "Lễ hội Cầu mùa (người Dao)")
page("Cao Lan", ["Các dân tộc Việt Nam"], "Một nhóm người Sán Chay.")                              # bẫy bài dân tộc


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("_", " ").strip()


def _lookup(title: str) -> str | None:
    title = _norm(title)
    for candidate in (title, title[:1].upper() + title[1:]):   # MediaWiki: chỉ chữ cái đầu không phân biệt hoa/thường
        if candidate in PAGES or candidate in REDIRECTS:
            return candidate
    return None


class FakeWiki:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, url: str, params: dict, request_cfg: dict) -> dict:
        self.calls.append(dict(params))
        if params.get("action") == "wbgetentities":
            return {"entities": {}}
        if params.get("list") == "prefixsearch":
            query = _norm(params["pssearch"]).casefold()
            hits = [t for t in PAGES if t.casefold().startswith(query)]
            return {"query": {"prefixsearch": [{"ns": 0, "title": t, "pageid": PAGES[t]["pageid"]} for t in hits[:10]]}}
        pages, redirects = [], []
        for title in params.get("titles", "").split("|"):
            found = _lookup(title)
            if found is None:
                pages.append({"title": _norm(title), "missing": True})
                continue
            if found in REDIRECTS:
                redirects.append({"from": _norm(title), "to": REDIRECTS[found]})
                found = REDIRECTS[found]
            pages.append(dict(PAGES[found]))
        return {"query": {"pages": pages, "redirects": redirects}}
