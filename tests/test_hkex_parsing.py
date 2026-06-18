from src.scraper.hkex import _clean_stock_code, _is_post_ipo_doc, _is_structured_or_etf


def test_clean_stock_code_normalizes_four_digit_codes():
    assert _clean_stock_code("9988") == "09988"
    assert _clean_stock_code("09988<br/>01234") == "09988"


def test_product_filters_reject_non_ipo_documents():
    assert _is_structured_or_etf("02800", "盈富基金", "上市文件")
    assert _is_post_ipo_doc("首次公開發售後股份獎勵計劃", "")
    assert not _is_structured_or_etf("09988", "示例科技", "招股章程")
