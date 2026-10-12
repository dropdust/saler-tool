"""T199 单元测试：错误分类新增 PARSE（网页端检索特有的解析失败）。"""

from __future__ import annotations

from saler.providers.errors import RETRYABLE_KINDS, ErrorKind, ProviderError


class TestParseKind:
    def test_parse_kind_value(self):
        assert ErrorKind.PARSE == "parse"

    def test_parse_not_retryable(self):
        assert ErrorKind.PARSE not in RETRYABLE_KINDS
        err = ProviderError(ErrorKind.PARSE, "结果容器存在但解析异常", provider="bing_html")
        assert err.retryable is False

    def test_str_kind_coerced_to_enum(self):
        err = ProviderError("parse", "条目结构不可读")
        assert err.kind is ErrorKind.PARSE
