"""匿名真实聊天评测的隐私边界测试。"""
import unittest

from eval_memory_anonymized import redact


class AnonymizedEvalTest(unittest.TestCase):
    def test_sensitive_identifiers_are_redacted(self):
        source = (
            "联系 test.user+demo@example.com，手机 13812345678，"
            "身份证 11010519491231002X，链接 https://example.com/private?q=1"
        )
        result = redact(source)

        self.assertNotIn("test.user", result)
        self.assertNotIn("13812345678", result)
        self.assertNotIn("11010519491231002X", result)
        self.assertNotIn("example.com", result)
        self.assertIn("[邮箱]", result)
        self.assertIn("[手机号]", result)
        self.assertIn("[证件号]", result)
        self.assertIn("[链接]", result)


if __name__ == "__main__":
    unittest.main()
